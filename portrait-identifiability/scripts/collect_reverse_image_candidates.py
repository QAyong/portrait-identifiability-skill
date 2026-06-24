from __future__ import annotations

import argparse
import hashlib
import shutil
import time
from pathlib import Path
from typing import Any

from baidu_image_search_playwright import collect_baidu_candidates
from common import print_json, save_json
from dedup_candidates import dedup_candidates


def _copy_merged_candidates(candidates: list[dict[str, Any]], output_dir: Path) -> list[dict[str, Any]]:
    merged_dir = output_dir / "merged-images"
    merged_dir.mkdir(parents=True, exist_ok=True)
    merged: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    for item in candidates:
        src = Path(item.get("image_path", ""))
        if not src.exists() or not src.is_file():
            continue
        body = src.read_bytes()
        digest = hashlib.sha1(body).hexdigest()
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        ext = src.suffix or ".jpg"
        dst = merged_dir / f"candidate_{len(merged) + 1:03d}_{digest[:12]}{ext}"
        shutil.copyfile(src, dst)
        merged_item = dict(item)
        merged_item["rank"] = len(merged) + 1
        merged_item["image_path"] = str(dst)
        merged.append(merged_item)
    return merged


def collect_all_candidates(
    image: str | Path,
    output_dir: str | Path,
    max_images_per_source: int = 30,
    scrolls: int = 5,
    headless: bool = False,
    user_data_dir: str | Path | None = None,
    browser_channel: str | None = None,
    google_cdp_endpoint: str | None = None,
    slow_mo: int = 100,
    google_timeout_ms: int = 20000,
    skip_google: bool = False,
    use_face_dedup: bool = False,
) -> dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sources: dict[str, Any] = {}
    all_candidates: list[dict[str, Any]] = []
    dedup_stats: dict[str, Any] = {}

    baidu_manifest = collect_baidu_candidates(
        image,
        out_dir / "baidu",
        max_images=max_images_per_source,
        scrolls=scrolls,
        headless=headless,
        user_data_dir=user_data_dir,
        browser_channel=browser_channel,
        slow_mo=slow_mo,
    )
    sources["baidu"] = {
        "status": baidu_manifest.get("status"),
        "candidate_count": baidu_manifest.get("candidate_count", 0),
        "output_dir": baidu_manifest.get("output_dir"),
    }
    all_candidates.extend(baidu_manifest.get("candidates", []))

    # 前置去重：字节级 + pHash 视觉近似（默认快速）；use_face_dedup=True 时启用 ArcFace 双条件
    dedup_result = dedup_candidates(all_candidates, use_face=use_face_dedup)
    all_candidates = dedup_result["deduped"]
    dedup_stats = dedup_result["stats"]

    if google_cdp_endpoint or google_timeout_ms != 20000 or skip_google:
        sources["google_lens"] = {
            "status": "disabled",
            "skip_reason": "google_lens_disabled_use_baidu_only",
            "candidate_count": 0,
        }

    merged = _copy_merged_candidates(all_candidates, out_dir)
    manifest = {
        "mode": "reverse_image_candidates",
        "status": "success" if merged else "no_candidates",
        "source_image": str(Path(image).resolve()),
        "output_dir": str(out_dir),
        "sources": sources,
        "candidate_count": len(merged),
        "candidates": merged,
        "dedup_stats": dedup_stats,
        "dedup_notice": "已对候选图执行前置去重：同一张照片的缩略图/压缩/格式变体只保留最清晰一张，撞脸的不同照片保留不动。当前模式见 dedup_stats.use_face（False=pHash 快速模式，True=ArcFace 双条件模式）。",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_json(out_dir / "manifest.json", manifest)
    save_json(out_dir / "candidates.json", {"candidates": merged})
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="使用百度识图采集并合并相似图片候选。")
    parser.add_argument("image")
    parser.add_argument("--output-dir", default="reverse-image-candidates")
    parser.add_argument("--max-images-per-source", type=int, default=30)
    parser.add_argument("--scrolls", type=int, default=5)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--user-data-dir")
    parser.add_argument("--browser-channel", choices=["chrome", "msedge", "chromium"])
    parser.add_argument("--google-cdp-endpoint", help="已停用，仅保留兼容旧命令；本脚本不会访问 Google Lens。")
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--google-timeout-ms", type=int, default=20000, help="已停用，仅保留兼容旧命令。")
    parser.add_argument("--skip-google", action="store_true", help="已停用，仅保留兼容旧命令；当前始终只使用百度识图。")
    parser.add_argument("--use-face-dedup", action="store_true", help="去重时启用 ArcFace 双条件（更稳但慢，需 InsightFace）；默认纯 pHash 快速模式")
    args = parser.parse_args()

    result = collect_all_candidates(
        args.image,
        args.output_dir,
        max_images_per_source=args.max_images_per_source,
        scrolls=args.scrolls,
        headless=args.headless,
        user_data_dir=args.user_data_dir,
        browser_channel=args.browser_channel,
        google_cdp_endpoint=args.google_cdp_endpoint,
        slow_mo=args.slow_mo,
        google_timeout_ms=args.google_timeout_ms,
        skip_google=args.skip_google,
        use_face_dedup=args.use_face_dedup,
    )
    print_json(result)


if __name__ == "__main__":
    main()
