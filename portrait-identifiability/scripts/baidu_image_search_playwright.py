from __future__ import annotations

import argparse
import hashlib
import mimetypes
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from common import print_json, save_json


BAIDU_GRAPH_URL = "https://graph.baidu.com/pcpage/index?tpl_from=pc"
RESULT_IMAGE_PATTERN = re.compile(
    r"(?:^https?:)?//(?:[^/]+\.)?(?:baidu|bdimg)\.com/.*\.(?:jpg|jpeg|png|webp)(?:[?#].*)?$",
    re.IGNORECASE,
)
BAIDU_IMAGE_HINTS = ("mms", "graph", "image", "img", "bdimg")


@dataclass
class CapturedImage:
    url: str
    content_type: str
    body: bytes | None = None


def _safe_suffix(url: str, content_type: str = "") -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        return suffix
    guessed = mimetypes.guess_extension(content_type.split(";")[0].strip()) if content_type else None
    return guessed if guessed in {".jpg", ".jpeg", ".png", ".webp", ".bmp"} else ".jpg"


def _looks_like_result_image(url: str, content_type: str = "") -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if "image" in content_type.lower():
        return any(domain in host for domain in ("baidu.com", "bdimg.com"))
    if RESULT_IMAGE_PATTERN.search(url):
        return True
    return any(hint in host or hint in path for hint in BAIDU_IMAGE_HINTS) and any(
        ext in path for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp")
    )


def _stable_name(index: int, url: str, content_type: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    return f"candidate_{index:03d}_{digest}{_safe_suffix(url, content_type)}"


def _extract_dom_image_urls(page: Any) -> list[str]:
    return page.evaluate(
        """
        () => Array.from(document.images)
          .map(img => img.currentSrc || img.src || img.getAttribute('data-src') || img.getAttribute('data-original'))
          .filter(Boolean)
        """
    )


def _find_file_input(page: Any) -> Any | None:
    input_locator = page.locator("input[type='file']")
    if input_locator.count() > 0:
        return input_locator.first

    for selector in [
        "text=上传图片",
        "text=本地上传",
        "text=选择文件",
        "[class*=camera]",
        "[class*=upload]",
        "[aria-label*=上传]",
        "[title*=上传]",
    ]:
        locator = page.locator(selector)
        if locator.count() > 0:
            try:
                locator.first.click(timeout=2000)
                page.wait_for_timeout(800)
                input_locator = page.locator("input[type='file']")
                if input_locator.count() > 0:
                    return input_locator.first
            except Exception:
                continue
    return None


def _save_candidate_images(
    page: Any,
    captured: dict[str, CapturedImage],
    output_dir: Path,
    max_images: int,
) -> list[dict[str, Any]]:
    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    dom_urls = _extract_dom_image_urls(page)
    for raw_url in dom_urls:
        url = urljoin(page.url, raw_url)
        if _looks_like_result_image(url) and url not in captured:
            captured[url] = CapturedImage(url=url, content_type="")

    candidates: list[dict[str, Any]] = []
    seen_body_hashes: set[str] = set()
    for url, image in list(captured.items()):
        if len(candidates) >= max_images:
            break
        body = image.body
        content_type = image.content_type
        if body is None:
            try:
                response = page.context.request.get(url, headers={"Referer": page.url}, timeout=15000)
                if not response.ok:
                    continue
                content_type = response.headers.get("content-type", content_type)
                if not _looks_like_result_image(url, content_type):
                    continue
                body = response.body()
            except Exception:
                continue
        if not body or len(body) < 1024:
            continue
        body_hash = hashlib.sha1(body).hexdigest()
        if body_hash in seen_body_hashes:
            continue
        seen_body_hashes.add(body_hash)
        filename = _stable_name(len(candidates) + 1, url, content_type)
        path = image_dir / filename
        path.write_bytes(body)
        candidates.append(
            {
                "rank": len(candidates) + 1,
                "image_path": str(path),
                "title": f"百度识图候选 {len(candidates) + 1}",
                "source": page.url,
                "image_url": url,
                "search_engine": "baidu_playwright",
            }
        )
    return candidates


def collect_baidu_candidates(
    image: str | Path,
    output_dir: str | Path,
    max_images: int = 30,
    scrolls: int = 5,
    headless: bool = False,
    user_data_dir: str | Path | None = None,
    browser_channel: str | None = None,
    slow_mo: int = 100,
) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    image_path = Path(image).resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"待检索图片不存在：{image_path}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    captured: dict[str, CapturedImage] = {}

    with sync_playwright() as p:
        launch_kwargs: dict[str, Any] = {"headless": headless, "slow_mo": slow_mo}
        if browser_channel:
            launch_kwargs["channel"] = browser_channel
        if user_data_dir:
            context = p.chromium.launch_persistent_context(
                str(Path(user_data_dir)),
                accept_downloads=True,
                **launch_kwargs,
            )
            page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = p.chromium.launch(**launch_kwargs)
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()

        def on_response(response: Any) -> None:
            try:
                url = response.url
                content_type = response.headers.get("content-type", "")
                if not _looks_like_result_image(url, content_type):
                    return
                body = response.body()
                if body and len(body) >= 1024:
                    captured.setdefault(url, CapturedImage(url=url, content_type=content_type, body=body))
            except Exception:
                return

        page.on("response", on_response)
        page.goto(BAIDU_GRAPH_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1200)

        file_input = _find_file_input(page)
        if file_input is None:
            screenshot = out_dir / "upload-page.png"
            page.screenshot(path=str(screenshot), full_page=True)
            context.close()
            raise RuntimeError(f"未找到百度识图上传控件，已保存页面截图：{screenshot}")

        file_input.set_input_files(str(image_path))
        page.wait_for_load_state("domcontentloaded", timeout=60000)
        page.wait_for_timeout(3500)

        for _ in range(scrolls):
            page.mouse.wheel(0, 2200)
            page.wait_for_timeout(1200)

        candidates = _save_candidate_images(page, captured, out_dir, max_images=max_images)
        manifest = {
            "mode": "baidu_image_search_playwright",
            "status": "success" if candidates else "no_candidates",
            "search_engine": "baidu_playwright",
            "search_url": BAIDU_GRAPH_URL,
            "result_page": page.url,
            "source_image": str(image_path),
            "output_dir": str(out_dir),
            "browser_channel": browser_channel or "playwright_chromium",
            "captured_image_url_count": len(captured),
            "candidate_count": len(candidates),
            "candidates": candidates,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "notes": [
                "候选图来自浏览器实际加载资源和页面 DOM 图片地址。",
                "百度识图网页结构可能变化；如 candidate_count 为 0，请使用默认可见浏览器观察页面，或手动提供候选图。",
            ],
        }
        save_json(out_dir / "manifest.json", manifest)
        save_json(out_dir / "candidates.json", {"candidates": candidates})
        context.close()
        return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="使用 Playwright 打开百度识图并批量导出相似图片候选。")
    parser.add_argument("image")
    parser.add_argument("--output-dir", default="baidu-playwright-candidates")
    parser.add_argument("--max-images", type=int, default=30)
    parser.add_argument("--scrolls", type=int, default=5)
    parser.add_argument("--headless", action="store_true", help="使用无头浏览器。默认使用可见浏览器，便于处理验证码或页面变化。")
    parser.add_argument("--user-data-dir", help="可选：复用本地浏览器用户数据目录，便于保留登录/地区状态。")
    parser.add_argument(
        "--browser-channel",
        choices=["chrome", "msedge", "chromium"],
        help="可选：使用本机 Chrome/Edge 浏览器通道，例如 msedge 或 chrome；不填则使用 Playwright 托管 Chromium。",
    )
    parser.add_argument("--slow-mo", type=int, default=100)
    args = parser.parse_args()

    result = collect_baidu_candidates(
        args.image,
        args.output_dir,
        max_images=args.max_images,
        scrolls=args.scrolls,
        headless=args.headless,
        user_data_dir=args.user_data_dir,
        browser_channel=args.browser_channel,
        slow_mo=args.slow_mo,
    )
    print_json(result)


if __name__ == "__main__":
    main()
