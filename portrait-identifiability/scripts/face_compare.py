from __future__ import annotations

import argparse
from pathlib import Path

from common import (
    cosine_similarity,
    face_compare_reliability_issues,
    image_quality,
    print_json,
    read_image,
    risk_from_face_similarity,
    save_json,
    select_best_face,
)
from face_engine import detect_faces


def compare_faces(
    image_a: str | Path,
    image_b: str | Path,
    model_pack: str = "buffalo_l",
    det_size: int = 640,
) -> dict:
    img_a = read_image(image_a)
    img_b = read_image(image_b)
    faces_a = detect_faces(img_a, model_pack=model_pack, det_size=det_size)
    faces_b = detect_faces(img_b, model_pack=model_pack, det_size=det_size)
    best_a = select_best_face(faces_a)
    best_b = select_best_face(faces_b)

    quality_a = image_quality(img_a)
    quality_b = image_quality(img_b)
    result = {
        "mode": "face_compare",
        "status": "success",
        "image_a": str(image_a),
        "image_b": str(image_b),
        "quality_a": quality_a,
        "quality_b": quality_b,
        "faces_a": len(faces_a),
        "faces_b": len(faces_b),
        "selected_face_a": None,
        "selected_face_b": None,
        "similarity": None,
        "risk_level": "unable_to_determine",
        "basis": [],
        "limitations": [],
    }

    if best_a is None or best_b is None:
        result["status"] = "unable_to_determine"
        result["limitations"].append("未在一张或两张图片中检测到有效人脸。")
        return result
    if best_a.embedding is None or best_b.embedding is None:
        result["status"] = "unable_to_determine"
        result["limitations"].append("检测到人脸，但未能提取可比对的人脸特征向量。")
        return result

    result.update(
        {
            "selected_face_a": {
                "bbox": best_a.bbox,
                "det_score": round(best_a.det_score, 4),
                "area": round(best_a.area, 2),
            },
            "selected_face_b": {
                "bbox": best_b.bbox,
                "det_score": round(best_b.det_score, 4),
                "area": round(best_b.area, 2),
            },
        }
    )

    reliability_issues = face_compare_reliability_issues(
        img_a,
        img_b,
        quality_a,
        quality_b,
        len(faces_a),
        len(faces_b),
        best_a,
        best_b,
    )

    similarity = cosine_similarity(best_a.embedding, best_b.embedding)
    risk = risk_from_face_similarity(similarity)
    result["similarity"] = round(similarity, 4)
    result["basis"].append(f"ArcFace/InsightFace 余弦相似度：{similarity:.4f}。")
    if reliability_issues:
        result["status"] = "unable_to_determine"
        result["risk_level"] = "unable_to_determine"
        result["limitations"].extend(reliability_issues)
        result["limitations"].append("已计算相似度，但由于输入可靠性不足，不输出明确风险分档。")
        result["limitations"].append("相似度分数仅是技术辅助，不等同于身份确认或法律结论。")
        return result

    result["risk_level"] = risk
    if len(faces_a) > 1:
        result["limitations"].append("图片 A 存在多张人脸，默认选择检测置信度和面积综合最高的人脸。")
    if len(faces_b) > 1:
        result["limitations"].append("图片 B 存在多张人脸，默认选择检测置信度和面积综合最高的人脸。")
    result["limitations"].append("相似度分数仅是技术辅助，不等同于身份确认或法律结论。")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="使用 InsightFace 比对两张真人照片的面部相似度。")
    parser.add_argument("image_a")
    parser.add_argument("image_b")
    parser.add_argument("--model-pack", default="buffalo_l")
    parser.add_argument("--det-size", type=int, default=640)
    parser.add_argument("--output")
    args = parser.parse_args()

    result = compare_faces(args.image_a, args.image_b, args.model_pack, args.det_size)
    if args.output:
        save_json(args.output, result)
    print_json(result)


if __name__ == "__main__":
    main()
