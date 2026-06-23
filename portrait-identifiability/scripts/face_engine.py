from __future__ import annotations

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=4)
def get_face_app(model_pack: str = "buffalo_l", det_size: int = 640) -> Any:
    from insightface.app import FaceAnalysis

    app = FaceAnalysis(name=model_pack, providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(det_size, det_size))
    return app


def detect_faces(image, model_pack: str = "buffalo_l", det_size: int = 640):
    app = get_face_app(model_pack=model_pack, det_size=det_size)
    return app.get(image)
