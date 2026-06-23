from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from common import print_json, save_json


def collect_google_lens_candidates(
    image: str | Path,
    output_dir: str | Path,
    max_images: int = 30,
    scrolls: int = 5,
    headless: bool = False,
    user_data_dir: str | Path | None = None,
    browser_channel: str | None = None,
    cdp_endpoint: str | None = None,
    slow_mo: int = 100,
    timeout_ms: int = 45000,
) -> dict[str, Any]:
    image_path = Path(image).resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"待检索图片不存在：{image_path}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "mode": "google_lens_playwright",
        "status": "disabled",
        "skip_reason": "google_lens_disabled_use_baidu_only",
        "search_engine": "google_lens_playwright",
        "source_image": str(image_path),
        "output_dir": str(out_dir),
        "candidate_count": 0,
        "candidates": [],
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_json(out_dir / "manifest.json", manifest)
    save_json(out_dir / "candidates.json", {"candidates": []})
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Lens 采集器已停用；请使用百度识图采集器。")
    parser.add_argument("image")
    parser.add_argument("--output-dir", default="google-lens-disabled")
    parser.add_argument("--max-images", type=int, default=30)
    parser.add_argument("--scrolls", type=int, default=5)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--user-data-dir")
    parser.add_argument("--browser-channel", choices=["chrome", "msedge", "chromium"])
    parser.add_argument("--cdp-endpoint")
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--timeout-ms", type=int, default=45000)
    result = collect_google_lens_candidates(**vars(parser.parse_args()))
    print_json(result)


if __name__ == "__main__":
    main()
