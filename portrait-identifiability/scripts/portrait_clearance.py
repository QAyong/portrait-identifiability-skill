# -*- coding: utf-8 -*-
"""portrait_clearance - 肖像权可识别性统一撞脸排查流水线"""
from __future__ import annotations
import argparse, io, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import threading
import time
from typing import Any

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from common import iter_images, image_quality, load_json, normalize_candidate_list, read_image, risk_label, risk_score, save_json
from face_engine import detect_faces
from visual_compare import compare_images
from multimodal_config import detect_provider, print_provider_detection, resolve_provider
from html_report import save_html_report


def _build_pairs(query_image, reference_image=None, candidates_file=None, candidate_dir=None):
    pairs = []
    query = str(Path(query_image).resolve())
    if reference_image:
        pairs.append({"query": query, "reference": str(Path(reference_image).resolve()), "source": "user_upload", "rank": 0, "title": None, "search_engine": None})
    if candidates_file:
        raw = load_json(candidates_file)
        for c in normalize_candidate_list(raw):
            img_path = c.get("image_path") or c.get("resolved_image_path")
            if not img_path: continue
            p = Path(img_path)
            if not p.exists(): continue
            pairs.append({"query": query, "reference": str(p.resolve()), "source": c.get("search_engine") or c.get("source") or "baidu_candidate", "rank": c.get("rank", len(pairs) + 1), "title": c.get("title"), "search_engine": c.get("search_engine")})
    if candidate_dir:
        for idx, img_path in enumerate(iter_images(candidate_dir), start=1):
            p = Path(img_path)
            pairs.append({"query": query, "reference": str(p.resolve()), "source": "candidate_dir", "rank": len(pairs) + idx, "title": p.name, "search_engine": None})
    return pairs


def _collect_unable_reasons(results: list[dict[str, Any]], limit: int = 4) -> list[str]:
    reasons: list[str] = []
    for item in results:
        if item.get("risk_level") != "unable_to_determine":
            continue
        precheck = item.get("local_precheck", {})
        for reason in precheck.get("reliability_issues", []) or []:
            if reason and reason not in reasons:
                reasons.append(str(reason))
        for reason in item.get("limitations", []) or []:
            if reason and reason not in reasons:
                reasons.append(str(reason))
        ai = item.get("ai_visual_comparison", {})
        for reason in ai.get("limitations", []) or []:
            if reason and reason not in reasons:
                reasons.append(str(reason))
        for reason in item.get("basis", []) or []:
            text = str(reason)
            if any(keyword in text for keyword in ["质量", "未检测", "多张人脸", "无法可靠", "比对失败"]):
                if text not in reasons:
                    reasons.append(text)
        if len(reasons) >= limit:
            break
    return reasons[:limit]


def build_markdown_report(query_image: str, results: list[dict[str, Any]], provider_info: str = "无") -> str:
    query_name = Path(query_image).name
    total = len(results)
    risk_counts = {}
    for r in results:
        rl = r.get("risk_level", "unable_to_determine")
        risk_counts[rl] = risk_counts.get(rl, 0) + 1
    highest_risk = "unable_to_determine"
    for rl in ["high", "medium", "low_to_medium", "low"]:
        if risk_counts.get(rl, 0) > 0:
            highest_risk = rl
            break
    lines = ["# 肖像权可识别性撞脸排查报告", "", "## 一、检测结论", "", "查询图: " + query_name, "比对数: " + str(total), "多模态引擎: " + provider_info, "综合风险等级: **" + risk_label(highest_risk) + "**", ""]
    if risk_counts:
        lines.append("风险分布:")
        for rl in ["high", "medium", "low_to_medium", "low", "unable_to_determine"]:
            if risk_counts.get(rl, 0) > 0:
                lines.append("- " + risk_label(rl) + ": " + str(risk_counts[rl]) + " 个")
        lines.append("")
    if highest_risk in ("high", "medium"):
        lines.append("存在较高撞脸风险，建议人工复核。本结果不能替代司法鉴定、律师意见或法院判断。")
    elif highest_risk == "low":
        lines.append("在当前比对范围内未发现高相似候选对象。但这不代表不存在其他肖像权风险。")
    else:
        lines.append("部分或全部比对对象无法可靠判断，建议人工复核。")
    if highest_risk == "unable_to_determine":
        unable_reasons = _collect_unable_reasons(results)
        if unable_reasons:
            lines.extend(["", "无法判断原因:"])
            for reason in unable_reasons:
                lines.append("- " + reason)
    lines.append("")
    lines.extend(["## 二、详细比对结果", "", "| # | 比对图 | 来源 | 分析路径 | 风险等级 | 整体相似度 | 本地指标说明 | 主要依据 |", "|---|---|---|---|---|---|---|---|"])
    for item in results:
        pi = item.get("pair_info", {})
        ref_name = Path(item.get("image_b", "")).name
        source = pi.get("source", "unknown")
        path = item.get("analysis_path", "-")
        risk = risk_label(item.get("risk_level"))
        sim = item.get("overall_similarity")
        sim_str = "{:.2f}".format(sim) if sim is not None else "-"
        basis_items = []
        ai = item.get("ai_visual_comparison", {})
        if ai:
            basis_items = ai.get("basis", [])
        if not basis_items:
            basis_items = item.get("basis", [])
        basis_str = "；".join(basis_items[:2]).replace("\n", " ") or "-"
        precheck = item.get("local_precheck", {})
        face_sim = precheck.get("face_similarity")
        faces_a = precheck.get("faces_a")
        faces_b = precheck.get("faces_b")
        if isinstance(faces_a, int) and faces_a > 1:
            local_note = "目标对象提示：图片 A 检测到多张人脸，建议先裁剪或指定目标人物后重新检测"
        elif isinstance(faces_b, int) and faces_b > 1:
            local_note = "目标对象提示：图片 B 检测到多张人脸，建议先裁剪或指定目标人物后重新检测"
        elif str(path).upper() == "B":
            local_note = "风格化路径：不采用本地人脸 embedding 作为判断依据"
        elif face_sim is not None:
            local_note = "InsightFace 余弦相似度: {:.4f}".format(face_sim)
        else:
            local_note = "-"
        lines.append("| " + str(pi.get("rank", "-")) + " | " + ref_name[:30] + " | " + source + " | " + path + " | " + risk + " | " + sim_str + " | " + local_note + " | " + basis_str[:60] + " |")
    lines.append("")
    lines.extend(["## 三、限制说明", "", "本结果仅表示在当前比对范围内的撞脸风险排查，不代表不存在其他肖像权风险。", "比对结果可能受图片质量、角度、遮挡、风格化程度和候选图来源影响。"])
    if any(str(item.get("analysis_path", "")).upper() == "B" for item in results):
        lines.append("风格化图像场景不采用本地人脸 embedding 作为主要判断依据。")
    if any(
        isinstance(item.get("local_precheck", {}).get("faces_a"), int) and item.get("local_precheck", {}).get("faces_a") > 1
        or isinstance(item.get("local_precheck", {}).get("faces_b"), int) and item.get("local_precheck", {}).get("faces_b") > 1
        for item in results
    ):
        lines.append("多张人脸场景需要先裁剪到单一目标人脸，或明确指定目标人物后重新检测。")
    lines.append("本结果不能替代司法鉴定、律师意见或法院判断。")
    return "\n".join(lines)


def run_portrait_clearance(
    query_image,
    reference_image=None,
    candidates_file=None,
    candidate_dir=None,
    output_dir="clearance-output",
    use_multimodal=False,
    use_openai=False,
    vision_provider=None,
    multimodal_config=None,
    model=None,
    model_pack="buffalo_l",
    det_size=640,
    max_candidates=30,
    concurrency=10,
    fail_fast=False,
    retries=3,
):
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _use_mm = use_multimodal or use_openai
    if use_openai and not vision_provider:
        vision_provider = "openai"
    detection = None
    if _use_mm:
        detection = detect_provider(vision_provider, multimodal_config)
        if detection.provider is None:
            _use_mm = False
    pairs = _build_pairs(query_image, reference_image=reference_image, candidates_file=candidates_file, candidate_dir=candidate_dir)
    if not pairs:
        return {"status": "error", "error": "没有可用的比对对。", "query_image": str(query_image)}
    if max_candidates and len(pairs) > max_candidates:
        pairs = pairs[:max_candidates]
    results: list[dict[str, Any] | None] = [None] * len(pairs)
    print_lock = threading.Lock()

    def _compare_one(idx: int, pair: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            r = compare_images(pair["query"], pair["reference"], mode="unified", use_multimodal=_use_mm, vision_provider=vision_provider, config_path=multimodal_config, model=model, model_pack=model_pack, det_size=det_size, query_cache=query_cache, shared_client=shared_client, retries=retries)
            r["pair_info"] = {"source": pair["source"], "rank": pair["rank"], "title": pair.get("title"), "search_engine": pair.get("search_engine")}
            return idx, r
        except Exception as exc:
            if _use_mm and fail_fast:
                raise
            exc_name = type(exc).__name__
            r = {"mode": "unified", "status": "error", "image_a": pair["query"], "image_b": pair["reference"], "risk_level": "unable_to_determine", "basis": ["比对失败: " + exc_name + ": " + str(exc)], "pair_info": {"source": pair["source"], "rank": pair["rank"], "title": pair.get("title"), "search_engine": pair.get("search_engine")}}
            return idx, r

    # 预计算查询图人脸结果，避免 30 个候选重复检测同一张查询图
    query_cache: dict[str, Any] | None = None
    shared_client = None
    if _use_mm and pairs:
        try:
            q_img = read_image(pairs[0]["query"])
            query_cache = {
                "img": q_img,
                "quality": image_quality(q_img),
                "faces": detect_faces(q_img, model_pack=model_pack, det_size=det_size),
            }
        except Exception:
            query_cache = None
        try:
            from openai import OpenAI as _OpenAI
            _vp = resolve_provider(vision_provider, model=model, config_path=multimodal_config)
            _ck = {"api_key": _vp.api_key}
            if _vp.base_url:
                _ck["base_url"] = _vp.base_url
            shared_client = _OpenAI(**_ck)
        except Exception:
            shared_client = None

    n_pairs = len(pairs)
    if _use_mm and n_pairs > 1:
        workers = max(1, min(concurrency, n_pairs))
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_compare_one, i, pair): i for i, pair in enumerate(pairs)}
            done = 0
            for fut in as_completed(futures):
                try:
                    idx, r = fut.result()
                except Exception:
                    for f in futures:
                        f.cancel()
                    raise
                results[idx] = r
                done += 1
                with print_lock:
                    print("[并行比对] " + str(done) + "/" + str(n_pairs) + " 完成")
        elapsed = time.perf_counter() - t0
        with print_lock:
            print("[并行比对] 全部完成，耗时 " + "{:.1f}".format(elapsed) + "s，并发度 " + str(workers))
    else:
        for i, pair in enumerate(pairs):
            idx, r = _compare_one(i, pair)
            results[i] = r
    results = [r for r in results if r is not None]
    results.sort(key=lambda x: risk_score(x.get("risk_level", "unable_to_determine")), reverse=True)
    provider_info = "无（仅本地 InsightFace 指标）"
    if detection and detection.provider:
        provider_info = detection.provider.name
        if detection.provider.model:
            provider_info += " (" + detection.provider.model + ")"
    report_md = build_markdown_report(str(query_image), results, provider_info)
    report_path = out_dir / "clearance-report.md"
    report_path.write_text(report_md, encoding="utf-8")
    html_path = save_html_report(
        query_image=query_image,
        results=results,
        output_dir=out_dir,
        multimodal_provider=provider_info,
        total_pairs=len(results),
    )
    output = {"mode": "portrait_clearance", "status": "success", "query_image": str(Path(query_image).resolve()), "output_dir": str(out_dir.resolve()), "total_pairs_compared": len(results), "multimodal_enabled": _use_mm, "vision_provider": vision_provider, "multimodal_detection": {"source": detection.source if detection else "not_checked", "message": detection.message if detection else ""}, "results": results, "report_md_path": str(report_path), "report_html_path": str(html_path), "report_json_path": str(out_dir / "clearance-result.json")}
    save_json(out_dir / "clearance-result.json", output)
    return output


def main():
    parser = argparse.ArgumentParser(description="肖像权可识别性统一撞脸排查流水线。")
    parser.add_argument("query_image")
    parser.add_argument("--reference", "-r")
    parser.add_argument("--candidates-file")
    parser.add_argument("--candidate-dir")
    parser.add_argument("--output-dir", "-o", default="clearance-output")
    parser.add_argument("--use-openai", action="store_true")
    parser.add_argument("--use-multimodal", action="store_true")
    parser.add_argument("--vision-provider", choices=["auto", "agent_native", "doubao", "openai"])
    parser.add_argument("--multimodal-config")
    parser.add_argument("--model")
    parser.add_argument("--model-pack", default="buffalo_l")
    parser.add_argument("--det-size", type=int, default=640)
    parser.add_argument("--max-candidates", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=10, help="多模态 API 并发线程数（默认 10）")
    parser.add_argument("--fail-fast", action="store_true", help="启用多模态时任一比对失败立即终止其余任务")
    parser.add_argument("--retries", type=int, default=3, help="单次多模态 API 调用的最大重试次数（429/超时）")
    args = parser.parse_args()
    if args.use_multimodal or args.use_openai:
        detection = detect_provider(args.vision_provider, args.multimodal_config)
        print_provider_detection(detection)
        print()
    result = run_portrait_clearance(args.query_image, reference_image=args.reference, candidates_file=args.candidates_file, candidate_dir=args.candidate_dir, output_dir=args.output_dir, use_multimodal=args.use_multimodal, use_openai=args.use_openai, vision_provider=args.vision_provider, multimodal_config=args.multimodal_config, model=args.model, model_pack=args.model_pack, det_size=args.det_size, max_candidates=args.max_candidates, concurrency=args.concurrency, fail_fast=args.fail_fast, retries=args.retries)
    if result["status"] == "error":
        print("错误: " + str(result.get("error")))
        sys.exit(1)
    print("排查完成")
    print("  比对数: " + str(result["total_pairs_compared"]))
    mm_status = "已启用" if result["multimodal_enabled"] else "仅本地指标"
    print("  多模态: " + mm_status)
    print("  报告: " + str(result["report_md_path"]))
    print("  JSON: " + str(result["report_json_path"]))

    # 输出 HTML 报告路径
    if "report_html_path" in result:
        print("  HTML: " + str(result["report_html_path"]))

if __name__ == "__main__":
    main()
