# -*- coding: utf-8 -*-
"""multimodal_config - 多模态模型配置与启动自检"""
from __future__ import annotations
import io, json, os, sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from common import save_json

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "agents" / "multimodal.json"

# -- DEV ONLY -- 打包发布前必须删除此块 ------------------------------------
_DEV_KEYS = {
    "doubao": {
        "api_key": "93f5d86c-83f0-460c-a2de-28af2d5b846c",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "doubao-seed-2-0-pro-260215",
    },
}
# -- END DEV ONLY ---------------------------------------------------------


@dataclass(frozen=True)
class VisionProvider:
    name: str
    model: str | None
    api_key: str | None
    base_url: str | None
    save_raw_response: bool
    raw_response_dir: Path


@dataclass
class ProviderDetection:
    provider: VisionProvider | None
    source: str
    message: str
    recommendations: list[str] = field(default_factory=list)


def load_multimodal_config(config_path=None):
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError("Multimodal config not found: " + str(path))
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("multimodal", data)


def agent_native_available(config=None):
    if config is None:
        try:
            config = load_multimodal_config()
        except FileNotFoundError:
            return False
    detection = config.get("startup_detection", {})
    env_name = detection.get("agent_capability_env", "PORTRAIT_AGENT_MULTIMODAL")
    return os.environ.get(env_name, "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_credential(env_key, cfg_value, dev_provider, dev_field):
    val = os.environ.get(env_key, "") if env_key else ""
    if not val and cfg_value:
        val = cfg_value
    if not val and dev_provider:
        val = _DEV_KEYS.get(dev_provider, {}).get(dev_field, "")
    return val


def detect_provider(requested_provider=None, config_path=None):
    try:
        config = load_multimodal_config(config_path)
    except FileNotFoundError:
        return ProviderDetection(
            provider=None, source="none",
            message="未找到多模态配置文件 multimodal.json。",
            recommendations=["请创建 portrait-identifiability/agents/multimodal.json 配置文件。"],
        )

    if agent_native_available(config):
        debug = config.get("debug", {})
        raw_dir = Path(debug.get("raw_response_dir") or "portrait-identifiability/debug/multimodal")
        return ProviderDetection(
            provider=VisionProvider(
                name="agent_native", model=None, api_key=None, base_url=None,
                save_raw_response=bool(debug.get("save_raw_response", False)),
                raw_response_dir=raw_dir,
            ),
            source="agent_native",
            message="检测到 agent 自带多模态能力（PORTRAIT_AGENT_MULTIMODAL=true）。",
        )

    providers_config = config.get("providers", {})
    debug = config.get("debug", {})
    raw_dir = Path(debug.get("raw_response_dir") or "portrait-identifiability/debug/multimodal")
    save_raw = bool(debug.get("save_raw_response", False))

    for pname in ["openai", "doubao"]:
        pcfg = providers_config.get(pname, {})
        if not pcfg.get("enabled", True):
            continue
        key_env = pcfg.get("api_key_env", "")
        key = _resolve_credential(key_env, None, pname, "api_key")
        if key:
            model_env = pcfg.get("model_env", "")
            model = _resolve_credential(model_env, pcfg.get("model", ""), pname, "model")
            base_url = _resolve_credential(pcfg.get("base_url_env", ""), pcfg.get("base_url"), pname, "base_url")
            return ProviderDetection(
                provider=VisionProvider(
                    name=pname, model=model, api_key=key, base_url=base_url,
                    save_raw_response=save_raw, raw_response_dir=raw_dir,
                ),
                source="env_var",
                message="检测到 " + pname + " 已配置，使用模型：" + str(model) + "。",
            )

    default_provider = config.get("provider", "openai")
    def_cfg = providers_config.get(default_provider, {})
    def_api_env = def_cfg.get("api_key_env", default_provider.upper() + "_API_KEY")
    return ProviderDetection(
        provider=None, source="config_default",
        message="未检测到可用的多模态模型密钥。默认提供方：" + default_provider + "。",
        recommendations=["设置 " + def_api_env + " 环境变量。", "或 set PORTRAIT_AGENT_MULTIMODAL=true 使用 agent 自带能力。"],
    )


def resolve_provider(requested_provider=None, model=None, config_path=None):
    config = load_multimodal_config(config_path)
    provider_name = requested_provider or config.get("provider") or "openai"
    if provider_name == "auto":
        detection = detect_provider(config_path=config_path)
        if detection.provider:
            return detection.provider
        raise RuntimeError("无法自动检测多模态提供方。请设置 OPENAI_API_KEY 或 DOUBAO_API_KEY。")
    if provider_name == "agent_native":
        raise RuntimeError("agent_native 需要由 Codex skill agent 在脚本外处理。")
    providers = config.get("providers", {})
    pcfg = providers.get(provider_name)
    if not pcfg:
        raise ValueError("Unknown multimodal provider: " + provider_name)
    if not pcfg.get("enabled", True):
        raise ValueError("Multimodal provider is disabled: " + provider_name)
    debug = config.get("debug", {})
    raw_dir = Path(debug.get("raw_response_dir") or "portrait-identifiability/debug/multimodal")
    api_key = _resolve_credential(pcfg.get("api_key_env", ""), None, provider_name, "api_key")
    resolved_model = model or _resolve_credential(pcfg.get("model_env", ""), pcfg.get("model"), provider_name, "model")
    base_url = _resolve_credential(pcfg.get("base_url_env", ""), pcfg.get("base_url"), provider_name, "base_url")
    if not api_key:
        raise ValueError(provider_name + " API key is not configured.")
    if not resolved_model:
        raise ValueError(provider_name + " vision model is not configured.")
    return VisionProvider(
        name=provider_name, model=resolved_model, api_key=api_key, base_url=base_url,
        save_raw_response=bool(debug.get("save_raw_response", False)),
        raw_response_dir=raw_dir,
    )


def save_raw_response_if_debug(provider, payload, prefix):
    if not provider.save_raw_response:
        return None
    provider.raw_response_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(provider.raw_response_dir.glob(prefix + "-*.json"))
    path = provider.raw_response_dir / (prefix + "-" + str(len(existing) + 1).zfill(4) + ".json")
    save_json(path, payload)
    return str(path)


def print_provider_detection(detection):
    print("[多模态检测] " + detection.message)
    for rec in detection.recommendations:
        print("  -> " + rec)


if __name__ == "__main__":
    d = detect_provider()
    print_provider_detection(d)
    if d.provider:
        print("")
        print("可用提供方: " + d.provider.name)
        model_label = d.provider.model or "(agent native)"
        print("  模型: " + model_label)
    else:
        print("")
        print("未检测到可用多模态提供方。")
        sys.exit(1)
