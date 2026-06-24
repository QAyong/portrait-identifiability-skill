from __future__ import annotations

import threading
from typing import Any

_FACE_APP_LOCK = threading.Lock()
_FACE_APP_CACHE: dict[tuple[str, int], Any] = {}


def get_face_app(model_pack: str = "buffalo_l", det_size: int = 640) -> Any:
    """返回线程安全的单例 FaceAnalysis。

    用锁保证多线程并发首次调用时模型只加载一次（lru_cache 在并发下会重复初始化）。
    """
    key = (model_pack, det_size)
    if key in _FACE_APP_CACHE:
        return _FACE_APP_CACHE[key]
    with _FACE_APP_LOCK:
        if key in _FACE_APP_CACHE:
            return _FACE_APP_CACHE[key]
        from insightface.app import FaceAnalysis

        app = FaceAnalysis(name=model_pack, providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(det_size, det_size))
        _FACE_APP_CACHE[key] = app
        return app


def detect_faces(image, model_pack: str = "buffalo_l", det_size: int = 640):
    app = get_face_app(model_pack=model_pack, det_size=det_size)
    return app.get(image)
