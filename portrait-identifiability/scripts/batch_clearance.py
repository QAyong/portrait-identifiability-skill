# -*- coding: utf-8 -*-
"""batch_clearance — 批量虚拟人物撞脸排查（委托给 portrait_clearance）"""
from __future__ import annotations
import argparse, io, sys
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from common import load_json, risk_label, save_json
from portrait_clearance import run_portrait_clearance
from multimodal_config import detect_provider, print_provider_detection


def run_batch(
    manifest_path,
    output_dir="batch-clearance-output",
    use_openai=False,
    use_multimodal=False,
    vision_provider=None,
    multimodal_config=None,
    model=None,
):
    manifest = load_json(manifest_path)
    items = manifest.get("items", manifest if isinstance(manifest, list) else [])
    if not isinstance(items, list):
        raise ValueError("批量 manifest 必须是列表，或包含 items 列表的对象。")
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for idx, item in enumerate(items, start=1):
        image = item["image"]
        item_id = item.get("id") or "item-" + str(idx)
        item_out = out_dir / item_id
        result = run_portrait_clearance(
            image,
            candidates_file=item.get("candidates_file"),
            candidate_dir=item.get("candidate_dir"),
            output_dir=item_out,
            use_multimodal=use_multimodal or bool(item.get("use_multimodal")),
            use_openai=use_openai or bool(item.get("use_openai")),
            vision_provider=vision_provider or item.get("vision_provider"),
            multimodal_config=multimodal_config or item.get("multimodal_config"),
            model=model or item.get("model"),
        )
        results.append({
            "id": item_id,
            "image": image,
            "risk_level": result.get("risk_level", "unable_to_determine"),
            "candidate_count": result.get("total_pairs_compared", 0),
            "report": str(item_out / "clearance-report.md"),
            "json": str(item_out / "clearance-result.json"),
        })
    summary = {"mode": "batch_clearance", "status": "success", "manifest": str(Path(manifest_path).resolve()), "output_dir": str(out_dir.resolve()), "items": results}
    save_json(out_dir / "batch-summary.json", summary)
    lines = ["# 批量虚拟人物撞脸风险排查汇总", "", "| 编号 | 图片 | 候选数 | 风险等级 | 报告 |", "|---|---|---:|---|---|"]
    for item in results:
        lines.append("| " + item["id"] + " | " + item["image"] + " | " + str(item["candidate_count"]) + " | " + risk_label(item["risk_level"]) + " | " + item["report"] + " |")
    (out_dir / "batch-report.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description="批量虚拟人物撞脸排查。")
    parser.add_argument("manifest")
    parser.add_argument("--output-dir", default="batch-clearance-output")
    parser.add_argument("--use-openai", action="store_true")
    parser.add_argument("--use-multimodal", action="store_true")
    parser.add_argument("--vision-provider", choices=["auto", "agent_native", "doubao", "openai"])
    parser.add_argument("--multimodal-config")
    parser.add_argument("--model")
    args = parser.parse_args()
    if args.use_multimodal or args.use_openai:
        detection = detect_provider(args.vision_provider, args.multimodal_config)
        print_provider_detection(detection)
        print()
    summary = run_batch(args.manifest, args.output_dir, args.use_openai, args.use_multimodal, args.vision_provider, args.multimodal_config, args.model)
    print("批量排查完成。汇总: " + str(Path(args.output_dir).resolve() / "batch-summary.json"))


if __name__ == "__main__":
    main()
