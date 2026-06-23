from __future__ import annotations

import base64
import json
import math
import mimetypes
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
import requests


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def read_image(path: str | Path) -> np.ndarray:
    p = Path(path)
    data = np.fromfile(str(p), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"无法读取图片：{p}")
    return image


def write_image(path: str | Path, image: np.ndarray) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    ext = p.suffix or ".png"
    ok, encoded = cv2.imencode(ext, image)
    if not ok:
        raise ValueError(f"无法将图片编码为 {ext}：{p}")
    encoded.tofile(str(p))


def iter_images(folder: str | Path) -> list[Path]:
    p = Path(folder)
    return sorted(x for x in p.iterdir() if x.is_file() and x.suffix.lower() in IMAGE_EXTS)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    return value


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2))


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(to_jsonable(payload), f, ensure_ascii=False, indent=2)


def image_quality(image: np.ndarray) -> dict[str, Any]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    contrast = float(gray.std())
    height, width = gray.shape[:2]
    if sharpness >= 120 and 55 <= brightness <= 205 and contrast >= 35:
        grade = "good"
    elif sharpness >= 50 and 35 <= brightness <= 225 and contrast >= 20:
        grade = "usable"
    else:
        grade = "poor"
    return {
        "width": width,
        "height": height,
        "sharpness": round(sharpness, 2),
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
        "grade": grade,
    }


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def risk_from_face_similarity(similarity: float | None) -> str:
    if similarity is None:
        return "unable_to_determine"
    if similarity >= 0.65:
        return "high"
    if similarity >= 0.50:
        return "medium"
    if similarity >= 0.35:
        return "low_to_medium"
    return "low"


def risk_score(level: str) -> float:
    return {
        "high": 1.0,
        "medium": 0.66,
        "low_to_medium": 0.5,
        "low": 0.2,
        "unable_to_determine": 0.0,
    }.get(level, 0.0)


def risk_label(level: str | None) -> str:
    return {
        "high": "高",
        "medium": "中",
        "low_to_medium": "中低",
        "low": "低",
        "unable_to_determine": "无法判断",
    }.get(level or "", level or "未知")


def data_url_for_image(path: str | Path) -> str:
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    raw = p.read_bytes()
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def download_image(url: str, output_dir: str | Path) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(url.split("?")[0]).suffix.lower()
    if suffix not in IMAGE_EXTS:
        suffix = ".jpg"
    fd, tmp = tempfile.mkstemp(prefix="candidate_", suffix=suffix, dir=str(out_dir))
    os.close(fd)
    r = requests.get(url, timeout=30, headers={"User-Agent": "portrait-identifiability/1.0"})
    r.raise_for_status()
    Path(tmp).write_bytes(r.content)
    return Path(tmp)


def normalize_candidate_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and "candidates" in data:
        data = data["candidates"]
    if not isinstance(data, list):
        raise ValueError("候选 JSON 必须是列表，或包含 'candidates' 列表的对象。")
    out = []
    for i, item in enumerate(data, start=1):
        if isinstance(item, str):
            item = {"image_path": item}
        if not isinstance(item, dict):
            raise ValueError(f"第 {i} 个候选项必须是字符串或对象。")
        item.setdefault("rank", i)
        out.append(item)
    return out


@dataclass
class FaceRecord:
    bbox: list[float]
    det_score: float
    embedding: np.ndarray | None
    area: float


def _face_bbox(face: Any) -> list[float]:
    bbox = getattr(face, "bbox", None)
    if bbox is None and isinstance(face, dict):
        bbox = face.get("bbox")
    if bbox is None:
        return [0.0, 0.0, 0.0, 0.0]
    return [float(x) for x in bbox]


def _face_score(face: Any) -> float:
    score = getattr(face, "det_score", None)
    if score is None and isinstance(face, dict):
        score = face.get("det_score")
    return float(score or 0.0)


def _face_embedding(face: Any) -> np.ndarray | None:
    emb = getattr(face, "normed_embedding", None)
    if emb is None:
        emb = getattr(face, "embedding", None)
    if emb is None and isinstance(face, dict):
        emb = face.get("normed_embedding") or face.get("embedding")
    if emb is None:
        return None
    arr = np.asarray(emb, dtype=np.float32)
    norm = np.linalg.norm(arr)
    return arr / norm if norm else arr


def face_to_record(face: Any) -> FaceRecord:
    bbox = _face_bbox(face)
    w = max(0.0, bbox[2] - bbox[0])
    h = max(0.0, bbox[3] - bbox[1])
    return FaceRecord(
        bbox=bbox,
        det_score=_face_score(face),
        embedding=_face_embedding(face),
        area=w * h,
    )


def select_best_face(faces: Iterable[Any]) -> FaceRecord | None:
    records = [face_to_record(f) for f in faces]
    if not records:
        return None
    return max(records, key=lambda r: (r.det_score, r.area))


def face_area_ratio(face: FaceRecord | None, image: np.ndarray) -> float:
    if face is None:
        return 0.0
    height, width = image.shape[:2]
    image_area = float(height * width)
    return face.area / image_area if image_area else 0.0


def face_compare_reliability_issues(
    image_a: np.ndarray,
    image_b: np.ndarray,
    quality_a: dict[str, Any],
    quality_b: dict[str, Any],
    faces_a_count: int,
    faces_b_count: int,
    selected_face_a: FaceRecord | None,
    selected_face_b: FaceRecord | None,
    min_det_score: float = 0.65,
    min_face_area_ratio: float = 0.02,
) -> list[str]:
    issues: list[str] = []
    if quality_a.get("grade") == "poor":
        issues.append("图片 A 质量过低，模糊、过暗、过曝或对比度不足会导致人脸特征不可靠。")
    if quality_b.get("grade") == "poor":
        issues.append("图片 B 质量过低，模糊、过暗、过曝或对比度不足会导致人脸特征不可靠。")
    if faces_a_count > 1:
        issues.append("图片 A 检测到多张人脸，未指定目标对象，无法可靠判断。")
    if faces_b_count > 1:
        issues.append("图片 B 检测到多张人脸，未指定目标对象，无法可靠判断。")
    if selected_face_a is not None and selected_face_a.det_score < min_det_score:
        issues.append(f"图片 A 人脸检测置信度较低（{selected_face_a.det_score:.4f}），特征提取不稳定。")
    if selected_face_b is not None and selected_face_b.det_score < min_det_score:
        issues.append(f"图片 B 人脸检测置信度较低（{selected_face_b.det_score:.4f}），特征提取不稳定。")
    ratio_a = face_area_ratio(selected_face_a, image_a)
    ratio_b = face_area_ratio(selected_face_b, image_b)
    if selected_face_a is not None and ratio_a < min_face_area_ratio:
        issues.append(f"图片 A 人脸区域占比过小（{ratio_a:.4f}），本地特征比对不可靠。")
    if selected_face_b is not None and ratio_b < min_face_area_ratio:
        issues.append(f"图片 B 人脸区域占比过小（{ratio_b:.4f}），本地特征比对不可靠。")
    return issues


def crop_bbox(image: np.ndarray, bbox: list[float], padding: float = 0.35) -> np.ndarray:
    h, w = image.shape[:2]
    x1, y1, x2, y2 = bbox
    bw = x2 - x1
    bh = y2 - y1
    pad_x = bw * padding
    pad_y = bh * padding
    x1 = int(max(0, math.floor(x1 - pad_x)))
    y1 = int(max(0, math.floor(y1 - pad_y)))
    x2 = int(min(w, math.ceil(x2 + pad_x)))
    y2 = int(min(h, math.ceil(y2 + pad_y)))
    if x2 <= x1 or y2 <= y1:
        return image
    return image[y1:y2, x1:x2].copy()
