# -*- coding: utf-8 -*-
"""统一视觉比对引擎 — 肖像权可识别性检测

分层设计：
  local_precheck:   InsightFace 本地预检（面部检测 + embedding + 质量评估）
  multimodal_compare: 多模态模型统一比对（成分判定 + Path A/B 融合分析）
  compare_images:  编排上述两步，输出完整对比结果
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from skimage.metrics import structural_similarity

# Fix Windows GBK encoding for print
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from common import (
    cosine_similarity,
    data_url_for_image,
    face_compare_reliability_issues,
    image_quality,
    print_json,
    read_image,
    risk_from_face_similarity,
    risk_label,
    save_json,
    select_best_face,
)
from face_engine import detect_faces
from multimodal_config import (
    VisionProvider,
    detect_provider,
    load_multimodal_config,
    resolve_provider,
    save_raw_response_if_debug,
)


# ──────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────

def _resize_gray(image: np.ndarray, size: int = 256) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA)


def _hist_correlation(a: np.ndarray, b: np.ndarray) -> float:
    hsv_a = cv2.cvtColor(a, cv2.COLOR_BGR2HSV)
    hsv_b = cv2.cvtColor(b, cv2.COLOR_BGR2HSV)
    hist_a = cv2.calcHist([hsv_a], [0, 1], None, [50, 60], [0, 180, 0, 256])
    hist_b = cv2.calcHist([hsv_b], [0, 1], None, [50, 60], [0, 180, 0, 256])
    cv2.normalize(hist_a, hist_a)
    cv2.normalize(hist_b, hist_b)
    return float(cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL))


def _local_image_similarity(image_a: np.ndarray, image_b: np.ndarray) -> dict[str, Any]:
    gray_a = _resize_gray(image_a)
    gray_b = _resize_gray(image_b)
    ssim = float(structural_similarity(gray_a, gray_b))
    hist = _hist_correlation(image_a, image_b)
    return {"ssim": round(ssim, 4), "color_hist_correlation": round(hist, 4)}


def _extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            return json.loads(match.group(0))
        raise


# ──────────────────────────────────────────────────────
# Step 1: InsightFace 本地预检
# ──────────────────────────────────────────────────────

def local_precheck(
    image_a: str | Path,
    image_b: str | Path,
    model_pack: str = "buffalo_l",
    det_size: int = 640,
) -> dict[str, Any]:
    """用 InsightFace 对两张图做人脸检测、质量评估、embedding 提取。

    返回:
        faces_a/b: 检测到的人脸数量
        face_similarity: 余弦相似度（仅当双方都有有效 embedding）
        quality_a/b: 图片质量
        reliability_issues: 可靠性问题列表
        can_extract_embedding: 双方是否都能提取有效 embedding
    """
    img_a = read_image(image_a)
    img_b = read_image(image_b)

    quality_a = image_quality(img_a)
    quality_b = image_quality(img_b)

    faces_a = detect_faces(img_a, model_pack=model_pack, det_size=det_size)
    faces_b = detect_faces(img_b, model_pack=model_pack, det_size=det_size)

    best_a = select_best_face(faces_a)
    best_b = select_best_face(faces_b)

    face_similarity = None
    reliability_issues: list[str] = []
    can_extract_embedding = False

    if best_a is not None and best_b is not None and \
       best_a.embedding is not None and best_b.embedding is not None:
        can_extract_embedding = True
        face_similarity = cosine_similarity(best_a.embedding, best_b.embedding)
        reliability_issues = face_compare_reliability_issues(
            img_a, img_b, quality_a, quality_b,
            len(faces_a), len(faces_b), best_a, best_b,
        )

    metrics = _local_image_similarity(img_a, img_b)

    return {
        "image_a": str(image_a),
        "image_b": str(image_b),
        "quality_a": quality_a,
        "quality_b": quality_b,
        "faces_a": len(faces_a),
        "faces_b": len(faces_b),
        "face_similarity": None if face_similarity is None else round(face_similarity, 4),
        "local_image_metrics": metrics,
        "can_extract_embedding": can_extract_embedding,
        "reliability_issues": reliability_issues,
        "best_face_a_det_score": None if best_a is None else round(best_a.det_score, 4),
        "best_face_b_det_score": None if best_b is None else round(best_b.det_score, 4),
    }


# ──────────────────────────────────────────────────────
# Step 2: 统一多模态比对（成分判定 + Path A/B 融合）
# ──────────────────────────────────────────────────────

def _build_unified_prompt(precheck: dict[str, Any]) -> str:
    """构建统一 prompt：先让 AI 判定图片成分，再按 Path A/B 进行对比。

    AI 需自行判断：
      - 两张均为 realistic → Path A：结合 InsightFace 相似度分数做融合判断
      - 任一张为 stylized  → Path B：纯视觉特征比对，InsightFace 数据仅作参考
    """
    fs = precheck.get("face_similarity")
    fi = precheck.get("reliability_issues", [])
    can_embed = precheck.get("can_extract_embedding", False)

    # InsightFace 参考信息
    insightface_note = ""
    if fs is not None:
        insightface_note = (
            f"\n【InsightFace 本地人脸预检结果】\n"
            f"- 图片 A：检测到 {precheck['faces_a']} 张人脸，"
            f"最大置信度 {precheck.get('best_face_a_det_score', 'N/A')}，"
            f"质量 {precheck['quality_a']['grade']}\n"
            f"- 图片 B：检测到 {precheck['faces_b']} 张人脸，"
            f"最大置信度 {precheck.get('best_face_b_det_score', 'N/A')}，"
            f"质量 {precheck['quality_b']['grade']}\n"
            f"- ArcFace 余弦相似度：{fs:.4f}\n"
        )
        if fi:
            insightface_note += f"- ⚠ 可靠性警告：{'；'.join(fi)}\n"
    else:
        face_a_info = f"{precheck['faces_a']} 张人脸" if precheck['faces_a'] > 0 else "未检测到人脸"
        face_b_info = f"{precheck['faces_b']} 张人脸" if precheck['faces_b'] > 0 else "未检测到人脸"
        insightface_note = (
            f"\n【InsightFace 本地人脸预检结果】\n"
            f"- 图片 A：{face_a_info}，质量 {precheck['quality_a']['grade']}\n"
            f"- 图片 B：{face_b_info}，质量 {precheck['quality_b']['grade']}\n"
            f"- ⚠ 无法提取可比对的人脸特征向量（原因：至少一方未检测到有效人脸或置信度不足）\n"
        )

    return f"""你正在辅助中国用户进行肖像权可识别性和撞脸风险审查。

## 任务

请先判断两张图片的成分类型（真实照片/照片级写实AI人脸 或 卡通/漫画/二次元/AI强风格化），然后按照对应路径进行比对：

### Path A（两张均为 realistic）：
结合 InsightFace 余弦相似度分数进行综合判断。分数作为参考，你需要同时进行视觉特征分析来验证和补充。

### Path B（任一张为 stylized）：
忽略 InsightFace 相似度分数（风格化图像的人脸 embedding 不可靠），只进行纯视觉特征比对。分析风格化图中是否保留了真人足以被识别的稳定外部特征。

{insightface_note}

## 判断重点

稳定外部特征（按重要性排序）：脸型与下颌线、五官整体布局、眼型与眉形、鼻型与嘴型、发际线与发型轮廓、痣/疤/胡须/标志性配饰等独特识别点。不要过度依赖发型、妆造、姿势、滤镜或色彩风格。

## 输出要求

只返回 JSON，不要输出 Markdown 或其他文字。JSON 必须包含以下键：

{{
  "image_a_type": "realistic 或 stylized",
  "image_b_type": "realistic 或 stylized",
  "analysis_path": "A 或 B",
  "status": "success 或 unable_to_determine",
  "risk_level": "high / medium / low_to_medium / low / unable_to_determine",
  "overall_similarity": 0.0 到 1.0 的浮点数,
  "feature_comparison": {{
    "face_shape": {{ "similarity": "high/medium/low/none", "note": "中文说明" }},
    "facial_layout": {{ "similarity": "high/medium/low/none", "note": "中文说明" }},
    "eyes_brows": {{ "similarity": "high/medium/low/none", "note": "中文说明" }},
    "nose_mouth": {{ "similarity": "high/medium/low/none", "note": "中文说明" }},
    "hair_hairline": {{ "similarity": "high/medium/low/none", "note": "中文说明" }},
    "distinctive_features": {{ "similarity": "high/medium/low/none", "note": "中文说明" }}
  }},
  "basis": ["中文短句证据数组"],
  "limitations": ["中文局限性说明数组"],
  "modification_suggestions": ["中文修改建议数组"],
  "insightface_fusion_note": "仅在 Path A 时填写：说明 AI 视觉判断与 InsightFace 分数是否一致"
}}

## 表达规范

- 不得识别私人自然人身份
- 不得说"确认侵权"、"确认同一人"、"可以放心商用"、"绝对安全"
- 结论使用"疑似"、"当前比对范围内"、"建议人工复核"等审慎中文表达
- 风险等级展示为：高 / 中 / 中低 / 低 / 无法判断
"""


def multimodal_compare(
    image_a: str | Path,
    image_b: str | Path,
    precheck: dict[str, Any],
    provider: str | None = None,
    model: str | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """统一多模态比对：一次 API 调用完成成分判定 + Path A/B 分析。

    Args:
        image_a, image_b: 图片路径
        precheck: local_precheck() 返回的 InsightFace 预检结果
        provider: 模型提供方 (openai/doubao/agent_native)
        model: 指定模型名
        config_path: 多模态配置文件路径

    Returns:
        结构化对比结果 JSON
    """
    from openai import OpenAI

    vision_provider: VisionProvider = resolve_provider(provider, model=model, config_path=config_path)

    if vision_provider.name == "agent_native":
        raise RuntimeError(
            "agent_native 多模态需要由 Codex skill agent 在脚本外处理。"
            "脚本运行时请使用 --vision-provider openai 或 doubao。"
        )

    client_kwargs: dict[str, Any] = {"api_key": vision_provider.api_key}
    if vision_provider.base_url:
        client_kwargs["base_url"] = vision_provider.base_url
    client = OpenAI(**client_kwargs)

    prompt = _build_unified_prompt(precheck)
    response = client.responses.create(
        model=vision_provider.model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": data_url_for_image(image_a)},
                    {"type": "input_image", "image_url": data_url_for_image(image_b)},
                    {"type": "input_text", "text": prompt},
                ],
            }
        ],
    )
    text = getattr(response, "output_text", None) or str(response)
    raw_response_path = save_raw_response_if_debug(
        vision_provider,
        {
            "provider": vision_provider.name,
            "model": vision_provider.model,
            "response_text": text,
        },
        "unified-compare",
    )
    payload = _extract_json(text)
    payload.setdefault("mode", "unified_compare")
    payload.setdefault("image_a", str(image_a))
    payload.setdefault("image_b", str(image_b))
    payload["vision_provider"] = vision_provider.name
    payload["vision_model"] = vision_provider.model
    if raw_response_path:
        payload["raw_response_path"] = raw_response_path
    return payload


# ──────────────────────────────────────────────────────
# Step 3: 编排函数 — 本地预检 + 多模态比对
# ──────────────────────────────────────────────────────

def compare_images(
    image_a: str | Path,
    image_b: str | Path,
    mode: str = "unified",
    use_multimodal: bool = False,
    use_openai: bool = False,
    vision_provider: str | None = None,
    config_path: str | Path | None = None,
    model: str | None = None,
    model_pack: str = "buffalo_l",
    det_size: int = 640,
) -> dict[str, Any]:
    """编排完整的图片比对流程。

    流程:
        1. local_precheck: InsightFace 本地预检
        2. 如启用多模态: multimodal_compare 统一比对
        3. 合并结果输出

    Args:
        image_a, image_b: 图片路径
        mode: 比对模式 (unified / stylized_identifiability / candidate_compare)
        use_multimodal: 是否启用多模态模型
        use_openai: 兼容旧用法的别名
        vision_provider: 多模态提供方
        其他参数同 local_precheck

    Returns:
        完整比对结果字典，包含 local_precheck 和（可选的）ai_visual_comparison
    """
    precheck = local_precheck(image_a, image_b, model_pack=model_pack, det_size=det_size)

    if not (use_multimodal or use_openai):
        # 仅本地指标
        basis = list(precheck.get("reliability_issues", []))
        if precheck.get("face_similarity") is not None:
            basis.insert(0, f"InsightFace 余弦相似度：{precheck['face_similarity']:.4f}。")
        return {
            "mode": mode,
            "status": "partial" if precheck.get("reliability_issues") else "success",
            "image_a": str(image_a),
            "image_b": str(image_b),
            "analysis_path": "A" if precheck.get("can_extract_embedding") and not precheck.get("reliability_issues") else "unable",
        "overall_similarity": precheck.get("face_similarity") or precheck.get("local_image_metrics", {}).get("ssim"),
        "risk_level": risk_from_face_similarity(precheck.get("face_similarity"))
                          if precheck.get("face_similarity") is not None and not precheck.get("reliability_issues")
                          else "unable_to_determine",
            "basis": basis,
            "local_precheck": precheck,
            "limitations": [
                "未启用多模态 AI 视觉比对，结果仅基于本地人脸特征指标。",
                "本地指标无法可靠判断风格化图像或虚拟人脸的撞脸风险。",
            ],
        }

    if not vision_provider:
        # Auto-detect from env/DEV config
        detected = detect_provider(config_path=config_path)
        if detected.provider:
            vision_provider = detected.provider.name
        elif use_openai:
            vision_provider = "openai"

    ai = multimodal_compare(
        image_a, image_b, precheck,
        provider=vision_provider, model=model, config_path=config_path,
    )

    return {
        "mode": mode,
        "status": ai.get("status", "success"),
        "image_a": str(image_a),
        "image_b": str(image_b),
        "vision_provider": ai.get("vision_provider"),
        "vision_model": ai.get("vision_model"),
        "analysis_path": ai.get("analysis_path", "unknown"),
        "image_a_type": ai.get("image_a_type", "unknown"),
        "image_b_type": ai.get("image_b_type", "unknown"),
        "risk_level": ai.get("risk_level", "unable_to_determine"),
        "overall_similarity": ai.get("overall_similarity"),
        "ai_visual_comparison": ai,
        "local_precheck": precheck,
    }


# ──────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="统一视觉比对：成分判定 + Path A/B 融合分析。"
    )
    parser.add_argument("image_a")
    parser.add_argument("image_b")
    parser.add_argument(
        "--mode", default="unified",
        choices=["unified", "candidate_compare", "stylized_identifiability"],
    )
    parser.add_argument("--use-openai", action="store_true",
                        help="兼容旧用法，等价于 --use-multimodal --vision-provider openai。")
    parser.add_argument("--use-multimodal", action="store_true",
                        help="启用多模态 AI 视觉比对。")
    parser.add_argument("--vision-provider",
                        choices=["auto", "agent_native", "doubao", "openai"])
    parser.add_argument("--multimodal-config")
    parser.add_argument("--model")
    parser.add_argument("--model-pack", default="buffalo_l")
    parser.add_argument("--det-size", type=int, default=640)
    parser.add_argument("--output")
    args = parser.parse_args()

    result = compare_images(
        args.image_a,
        args.image_b,
        mode=args.mode,
        use_openai=args.use_openai,
        use_multimodal=args.use_multimodal,
        vision_provider=args.vision_provider,
        config_path=args.multimodal_config,
        model=args.model,
        model_pack=args.model_pack,
        det_size=args.det_size,
    )
    if args.output:
        save_json(args.output, result)
    print_json(result)


if __name__ == "__main__":
    main()
