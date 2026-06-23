# -*- coding: utf-8 -*-
"""virtual_face_clearance — 虚拟人物脸撞脸排查（兼容包装器）

本模块现已委托给 portrait_clearance 统一流水线。
保留用于向后兼容。
"""
from __future__ import annotations
import argparse, io, sys
from pathlib import Path
from typing import Any

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from common import print_json, risk_label, save_json
from portrait_clearance import run_portrait_clearance
from multimodal_config import detect_provider, print_provider_detection


def run_clearance(
    image,
    candidates_file=None,
    candidate_dir=None,
    output_dir="clearance-output",
    use_openai=False,
    use_multimodal=False,
    vision_provider=None,
    multimodal_config=None,
    model=None,
    model_pack="buffalo_l",
    det_size=640,
    browser_searched="unknown",
):
    """兼容旧接口，委托给 portrait_clearance。"""
    return run_portrait_clearance(
        image,
        candidates_file=candidates_file,
        candidate_dir=candidate_dir,
        output_dir=output_dir,
        use_multimodal=use_multimodal or use_openai,
        vision_provider=vision_provider,
        multimodal_config=multimodal_config,
        model=model,
        model_pack=model_pack,
        det_size=det_size,
    )


def main():
    parser = argparse.ArgumentParser(description="虚拟人物脸撞脸排查。已委托给 portrait_clearance。")
    parser.add_argument("image")
    parser.add_argument("--candidates-file")
    parser.add_argument("--candidate-dir")
    parser.add_argument("--output-dir", default="clearance-output")
    parser.add_argument("--use-openai", action="store_true")
    parser.add_argument("--use-multimodal", action="store_true")
    parser.add_argument("--vision-provider", choices=["auto", "agent_native", "doubao", "openai"])
    parser.add_argument("--multimodal-config")
    parser.add_argument("--model")
    parser.add_argument("--model-pack", default="buffalo_l")
    parser.add_argument("--det-size", type=int, default=640)
    parser.add_argument("--browser-searched", default="unknown")
    args = parser.parse_args()
    if args.use_multimodal or args.use_openai:
        detection = detect_provider(args.vision_provider, args.multimodal_config)
        print_provider_detection(detection)
        print()
    result = run_clearance(args.image, args.candidates_file, args.candidate_dir, args.output_dir, args.use_openai, args.use_multimodal, args.vision_provider, args.multimodal_config, args.model, args.model_pack, args.det_size, args.browser_searched)
    if result["status"] == "error":
        print("错误: " + str(result.get("error")))
        sys.exit(1)
    save_json(Path(args.output_dir) / "clearance-result.json", result)
    print_json(result)


if __name__ == "__main__":
    main()
