from __future__ import annotations

import argparse
from pathlib import Path

from common import crop_bbox, image_quality, print_json, read_image, save_json, select_best_face, write_image
from face_engine import detect_faces


def prepare_search_image(
    image_path: str | Path,
    output_path: str | Path,
    model_pack: str = "buffalo_l",
    det_size: int = 640,
    padding: float = 0.35,
) -> dict:
    image = read_image(image_path)
    faces = detect_faces(image, model_pack=model_pack, det_size=det_size)
    best = select_best_face(faces)

    if best is None:
        cropped = image
        status = "no_face_detected"
        note = "未检测到有效人脸，已输出原图作为以图搜图输入。"
        selected = None
    else:
        cropped = crop_bbox(image, best.bbox, padding=padding)
        status = "success"
        note = "已裁剪最大/最可信人脸区域，保留一定发型和脸部上下文。"
        selected = {"bbox": best.bbox, "det_score": round(best.det_score, 4)}

    write_image(output_path, cropped)
    return {
        "mode": "prepare_search_image",
        "status": status,
        "source_image": str(image_path),
        "output_image": str(output_path),
        "faces": len(faces),
        "selected_face": selected,
        "source_quality": image_quality(image),
        "output_quality": image_quality(cropped),
        "note": note,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="为浏览器反向图片搜索裁剪可检索的人脸图。")
    parser.add_argument("image")
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-pack", default="buffalo_l")
    parser.add_argument("--det-size", type=int, default=640)
    parser.add_argument("--padding", type=float, default=0.35)
    parser.add_argument("--json-output")
    args = parser.parse_args()

    result = prepare_search_image(args.image, args.output, args.model_pack, args.det_size, args.padding)
    if args.json_output:
        save_json(args.json_output, result)
    print_json(result)


if __name__ == "__main__":
    main()
