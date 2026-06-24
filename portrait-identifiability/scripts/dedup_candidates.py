from __future__ import annotations

"""候选图去重模块。

在百度识图批量下载完成后、送入多模态比对之前，对候选图做前置去重，
避免同一张照片的不同尺寸/压缩/格式变体重复占用多模态 API 调用。

三层去重流水线：
1. 字节级精确去重（sha1）—— 删完全相同的文件
2. 视觉近似去重（pHash 感知哈希 + ArcFace embedding 双条件）
   —— 同一张照片的缩放/压缩/格式变体；撞脸的不同照片不会被误并
3. 保留策略 —— 同组内保留文件体积最大的一张

默认模式（快速，纯 pHash）：仅用 pHash 汉明距离判定，30~40 张图 1 秒内完成。
双条件模式（--use-face）：pHash 汉明距离 ≤ 阈值 且 ArcFace 余弦相似度 ≥ 阈值，
  更稳但需加载 InsightFace 逐张提取 embedding（CPU 上每张约 2.4 秒）。

判定逻辑：
  - 默认：pHash 汉明距离 ≤ PHASH_HAMMING_THRESHOLD 即判为同一张照片的变体
  - --use-face：pHash ≤ 阈值 且 ArcFace ≥ 阈值（双条件缺一不可）

为什么需要双条件：
- 百度识图返回的候选本质是"撞脸照片"，不同照片的人脸 ArcFace 相似度也可能
  ≥ 0.92（实测 0.92~0.98），单靠人脸 embedding 会把撞脸候选误并为同一张图。
- pHash 衡量整体图像相似度：同一张照片的缩放/压缩变体 pHash 距离 0~2，
  撞脸的不同照片（不同构图/背景/光线）pHash 距离 24+，区分度极大。
- 两者结合：pHash 保证"整张图几乎一样"，ArcFace 保证"人脸也一致"，
  能精准锁定"同一张照片的变体"而不误伤"撞脸的不同照片"。

最快实现：
- 每张图只跑一次 detect_faces + 一次 pHash，缓存到内存
- ArcFace embedding 堆成 (M, 512) 矩阵一次性算两两相似度
- pHash 两两汉明距离用矩阵化位运算
- 并查集归并满足双条件的图，每组保留 max(file_size)
"""

import argparse
import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from common import read_image, save_json, select_best_face
from face_engine import detect_faces

# 双条件阈值
# pHash：同一张照片变体距离 0~2，撞脸不同照 24+，阈值 5 留足安全边际
PHASH_HAMMING_THRESHOLD = 5
# ArcFace：同一张照片变体 0.93+，撞脸不同照也可能 0.92+，作为辅助确认条件
DEDUP_SIMILARITY_THRESHOLD = 0.90

PHASH_SIZE = 32       # DCT 计算尺寸
PHASH_HASH_SIZE = 8   # 最终哈希位数 8x8=64


@dataclass
class _Item:
    """去重流水线中的一个候选项。"""
    index: int
    image_path: Path
    file_size: int
    body_hash: str
    embedding: np.ndarray | None = None
    has_face: bool = False
    phash: np.ndarray | None = None
    # 并查集父指针（指向组内保留项的 index）
    kept_by: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class _UnionFind:
    """并查集，用于把满足双条件的图归为一组。"""

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _compute_phash(image_path: Path) -> np.ndarray | None:
    """计算 pHash（DCT-based 感知哈希），返回 64 位二值向量。"""
    try:
        img = cv2.imdecode(np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        img = cv2.resize(img, (PHASH_SIZE, PHASH_SIZE))
        dct = cv2.dct(np.float32(img))
        dct_low = dct[:PHASH_HASH_SIZE, :PHASH_HASH_SIZE]
        med = np.median(dct_low)
        return (dct_low > med).flatten().astype(np.uint8)
    except Exception:
        return None


def _build_items(candidates: list[dict[str, Any]]) -> list[_Item]:
    items: list[_Item] = []
    for i, item in enumerate(candidates):
        p = Path(item.get("image_path", ""))
        if not p.exists() or not p.is_file():
            continue
        body = p.read_bytes()
        items.append(
            _Item(
                index=i,
                image_path=p,
                file_size=p.stat().st_size,
                body_hash=hashlib.sha1(body).hexdigest(),
                meta=dict(item),
            )
        )
    return items


def _extract_features(items: list[_Item], model_pack: str, det_size: int, use_face: bool = False) -> None:
    """对每张图只跑一次：pHash 始终提取；ArcFace embedding 仅在 use_face 时提取。"""
    for item in items:
        # pHash（轻量，纯 opencv，不依赖人脸，始终执行）
        item.phash = _compute_phash(item.image_path)
        if not use_face:
            continue
        # ArcFace embedding（复用 InsightFace 单例，仅 --use-face 时执行）
        try:
            img = read_image(item.image_path)
            faces = detect_faces(img, model_pack=model_pack, det_size=det_size)
            best = select_best_face(faces)
            if best is not None and best.embedding is not None:
                item.embedding = np.asarray(best.embedding, dtype=np.float32)
                item.has_face = True
        except Exception:
            item.embedding = None
            item.has_face = False


def _dedup_by_bytes(items: list[_Item]) -> int:
    """第一层：字节级精确去重。同 body_hash 组内保留文件最大的一张。

    返回被去重的数量。
    """
    groups: dict[str, list[int]] = {}
    for idx, it in enumerate(items):
        groups.setdefault(it.body_hash, []).append(idx)
    removed = 0
    for _hash, idxs in groups.items():
        if len(idxs) <= 1:
            continue
        keeper = max(idxs, key=lambda i: items[i].file_size)
        for i in idxs:
            if i != keeper:
                items[i].kept_by = keeper
                removed += 1
    return removed


def _dedup_by_visual(
    items: list[_Item],
    phash_threshold: int = PHASH_HAMMING_THRESHOLD,
    face_threshold: float = DEDUP_SIMILARITY_THRESHOLD,
) -> int:
    """第二层：视觉近似去重（pHash + ArcFace 双条件）。

    对未被字节去重的活跃项，矩阵化计算两两 pHash 汉明距离与 ArcFace 余弦相似度，
    双条件同时满足（pHash 距离 ≤ 阈值 且 人脸相似度 ≥ 阈值）才并查集归并。
    每组保留文件最大的一张。无人脸或无 pHash 的项不参与视觉去重，保留。
    返回被去重的数量。
    """
    active = [i for i, it in enumerate(items) if it.kept_by is None and it.phash is not None]
    if len(active) <= 1:
        return 0

    # pHash 汉明距离矩阵（M, M）
    phash_mat = np.stack([items[i].phash for i in active]).astype(np.uint8)  # (M, 64)
    # 两两汉明距离 = popcount(a XOR b)
    xor_mat = phash_mat[:, None, :] ^ phash_mat[None, :, :]  # (M, M, 64)
    hamming_mat = xor_mat.sum(axis=2)  # (M, M)

    # ArcFace 余弦相似度矩阵（M, M），仅对有 embedding 的项有效
    emb_ok = [items[i].embedding is not None for i in active]
    sim_matrix = np.full((len(active), len(active)), -1.0, dtype=np.float32)
    if any(emb_ok):
        emb_list = []
        emb_local_idx = []
        for li, gi in enumerate(active):
            if items[gi].embedding is not None:
                e = items[gi].embedding.astype(np.float32)
                e = e / np.linalg.norm(e)
                emb_list.append(e)
                emb_local_idx.append(li)
        if emb_list:
            emb_mat = np.stack(emb_list)  # (K, 512)
            emb_sim = emb_mat @ emb_mat.T  # (K, K)
            for ai, li_a in enumerate(emb_local_idx):
                for bi, li_b in enumerate(emb_local_idx):
                    sim_matrix[li_a, li_b] = emb_sim[ai, bi]

    uf = _UnionFind(len(active))
    for a in range(len(active)):
        for b in range(a + 1, len(active)):
            phash_ok = hamming_mat[a, b] <= phash_threshold
            # 人脸相似度条件：两边都有 embedding 且 ≥ 阈值；
            # 若任一边无人脸，则仅凭 pHash 判定（pHash 已足够区分）
            if emb_ok[a] and emb_ok[b]:
                face_ok = sim_matrix[a, b] >= face_threshold
            else:
                face_ok = True
            if phash_ok and face_ok:
                uf.union(a, b)

    groups: dict[int, list[int]] = {}
    for local_idx, global_idx in enumerate(active):
        root = uf.find(local_idx)
        groups.setdefault(root, []).append(global_idx)

    removed = 0
    for members in groups.values():
        if len(members) <= 1:
            continue
        keeper = max(members, key=lambda i: items[i].file_size)
        for i in members:
            if i != keeper:
                items[i].kept_by = keeper
                removed += 1
    return removed


def dedup_candidates(
    candidates: list[dict[str, Any]],
    phash_threshold: int = PHASH_HAMMING_THRESHOLD,
    face_threshold: float = DEDUP_SIMILARITY_THRESHOLD,
    model_pack: str = "buffalo_l",
    det_size: int = 640,
    use_face: bool = False,
) -> dict[str, Any]:
    """对候选图列表执行三层去重，返回去重后的候选列表与统计信息。

    返回:
        {
            "deduped": [...],          # 去重后保留的候选列表
            "stats": {
                "input_count", "output_count",
                "byte_deduped", "visual_deduped", "total_deduped",
                "phash_threshold", "face_threshold", "elapsed_seconds",
                "dropped": [...]        # 被丢弃项的 rank/image_url/原因/保留项
            }
        }
    """
    t0 = time.perf_counter()
    items = _build_items(candidates)

    # 提取特征：pHash + ArcFace embedding（每张图只跑一次）
    _extract_features(items, model_pack=model_pack, det_size=det_size, use_face=use_face)

    byte_removed = _dedup_by_bytes(items)
    visual_removed = _dedup_by_visual(items, phash_threshold=phash_threshold, face_threshold=face_threshold)

    kept_items = [it for it in items if it.kept_by is None]
    kept_items.sort(key=lambda it: it.meta.get("rank", it.index))

    deduped: list[dict[str, Any]] = []
    for new_rank, it in enumerate(kept_items, start=1):
        out = dict(it.meta)
        out["rank"] = new_rank
        deduped.append(out)

    dropped: list[dict[str, Any]] = []
    for it in items:
        if it.kept_by is not None:
            keeper = items[it.kept_by]
            reason = "byte_duplicate" if it.body_hash == keeper.body_hash else "visual_duplicate"
            dropped.append(
                {
                    "dropped_rank": it.meta.get("rank"),
                    "dropped_image_path": str(it.image_path),
                    "dropped_image_url": it.meta.get("image_url"),
                    "kept_image_path": str(keeper.image_path),
                    "kept_image_url": keeper.meta.get("image_url"),
                    "reason": reason,
                    "file_size": it.file_size,
                    "kept_file_size": keeper.file_size,
                }
            )

    elapsed = time.perf_counter() - t0
    return {
        "deduped": deduped,
        "stats": {
            "input_count": len(candidates),
            "output_count": len(deduped),
            "byte_deduped": byte_removed,
            "visual_deduped": visual_removed,
            "total_deduped": byte_removed + visual_removed,
            "phash_threshold": phash_threshold,
            "face_threshold": face_threshold,
            "use_face": use_face,
            "elapsed_seconds": round(elapsed, 3),
            "dropped": dropped,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="对百度识图候选图做前置去重（字节 + pHash/ArcFace 双条件视觉近似）。")
    parser.add_argument("candidates_json", help="候选 JSON 路径（含 candidates 列表或 {candidates: [...]}）")
    parser.add_argument("--output", help="去重后 JSON 输出路径；不填则打印到 stdout")
    parser.add_argument("--phash-threshold", type=int, default=PHASH_HAMMING_THRESHOLD, help="pHash 汉明距离去重阈值，默认 5")
    parser.add_argument("--face-threshold", type=float, default=DEDUP_SIMILARITY_THRESHOLD, help="ArcFace 余弦相似度去重阈值，默认 0.90（仅 --use-face 时生效）")
    parser.add_argument("--use-face", action="store_true", help="启用 ArcFace 双条件模式（更稳但慢，需 InsightFace）；默认纯 pHash 快速模式")
    parser.add_argument("--model-pack", default="buffalo_l")
    parser.add_argument("--det-size", type=int, default=640)
    args = parser.parse_args()

    from common import load_json, print_json

    raw = load_json(args.candidates_json)
    if isinstance(raw, dict) and "candidates" in raw:
        cand_list = raw["candidates"]
    elif isinstance(raw, list):
        cand_list = raw
    else:
        raise ValueError("候选 JSON 必须是列表，或包含 candidates 列表的对象。")

    result = dedup_candidates(
        cand_list,
        phash_threshold=args.phash_threshold,
        face_threshold=args.face_threshold,
        model_pack=args.model_pack,
        det_size=args.det_size,
        use_face=args.use_face,
    )
    payload = {"candidates": result["deduped"], "dedup_stats": result["stats"]}
    if args.output:
        save_json(args.output, payload)
    print_json(payload)


if __name__ == "__main__":
    main()
