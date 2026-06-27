# Spec-001: check_config.py 配置自检脚本与 SKILL.md 联动

**日期：** 2026-06-27
**状态：** 待开发

## 背景

Codex Agent 读取 SKILL.md 后不会主动运行 Python 检测逻辑，导致误判 API Key 配置状态。需要提供独立自检脚本，并在 SKILL.md 中以强制指令要求 Agent 执行。

详见 ADR-002。

## 需求边界

**包含：**
- 创建 `scripts/check_config.py`，可独立运行
- 输出结构化 JSON（供 Agent 解析）+ 人类可读摘要
- 检测所有 provider 状态（agent_native / openai / doubao）
- 未配置的 provider 输出 API Key 获取地址
- SKILL.md 重写「多模态自检」一节，强制 Agent 先运行 `check_config.py`

**不包含：**
- 修改 `multimodal_config.py` 的核心检测逻辑
- 在 `check_config.py` 中写入/修改 API Key（那是 GUI 配置面板的事）
- 交互式 prompt 让用户输入 key（脚本只读不写）

## 验收标准

- [ ] `python scripts/check_config.py` 可独立运行并输出有效 JSON
- [ ] SKILL.md 中明确指令 Agent："启动后第一步运行 `python scripts/check_config.py`"
- [ ] Agent 在未检测到 provider 时，提示文案同时包含 API Key 配置方式和 `PORTRAIT_AGENT_MULTIMODAL` 环境变量
- [ ] `_DEV_KEYS` 硬编码 key 被检测到时，输出中标注"开发密钥"警告

## 场景描述

**正常流程（已配置 OpenAI Key）：**
1. Agent 或用户运行 `python scripts/check_config.py`
2. 输出 JSON `{"status": "ready", "provider": "openai", "model": "gpt-4.1-mini"}`
3. 显示人类可读：`✅ OpenAI 已配置 (gpt-4.1-mini)`
4. Agent 继续正常流程

**正常流程（Agent Native 模式）：**
1. 环境变量 `PORTRAIT_AGENT_MULTIMODAL=true` 已设置
2. 输出 JSON `{"status": "ready", "provider": "agent_native", "model": null}`
3. Agent 使用自带视觉能力

**异常流程（全部未配置）：**
1. 运行检测，无任何 provider 可用
2. 输出 JSON `{"status": "not_configured", "providers": {...}}`
3. 显示提示：
   ```
   ❌ 未检测到可用的多模态引擎
   配置方式（任选其一）：
   1. 设置环境变量 OPENAI_API_KEY 或 DOUBAO_API_KEY
   2. 设置 PORTRAIT_AGENT_MULTIMODAL=true 使用 Agent 自带能力
   
   API Key 获取地址：
   - OpenAI: https://platform.openai.com/api-keys
   - 豆包: https://console.volcengine.com/ark/...
   ```
4. Agent 向用户展示该提示，询问是否降级为仅本地指标继续

## 相关 ADR

- [adr-002-stable-config-detection.md](adr-002-stable-config-detection.md)
