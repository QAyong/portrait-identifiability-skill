# ADR-002: API Key 检测与 Skill 自检流程

**日期：** 2026-06-27
**状态：** 已接受

## 背景

当前 SKILL.md 和 `multimodal_config.py` 对 API Key 的检测逻辑分散在 Python 代码中。Codex Agent 读取 SKILL.md 后，不会主动运行 `detect_provider()` 来做自检，导致 Agent 误判"未配置 API Key"，即使用户已经设置了环境变量或配置文件。

核心矛盾：SKILL.md 是给 Agent 读的自然语言指令，但检测逻辑实现在 Python 代码中，Agent 不知道要去执行它。

## 决策

提供一个独立的 `check_config.py` 脚本，输出人类和机器都可读的配置状态报告。SKILL.md 中**强制要求** Agent 在启动时先执行该脚本，根据输出决定后续行为。

## 原因

1. **分离关注点**：SKILL.md 只管"何时运行检测"，`check_config.py` 只管"怎么检测"
2. **确定性输出**：脚本返回结构化 JSON + 人类可读文本，Agent 可以可靠解析
3. **独立可用**：用户也可以手动运行 `python check_config.py` 查看配置状态
4. **与现有逻辑无冲突**：`check_config.py` 复用 `multimodal_config.py` 的 `detect_provider()`，不重复造轮子

检测流程（SKILL.md 中的指令）：

```
Agent 启动 → 运行 python scripts/check_config.py → 解析输出 →
  ├─ 检测到 provider → 继续使用多模态
  ├─ 未检测到 → 提示用户配置 API Key 或设置 PORTRAIT_AGENT_MULTIMODAL=true
  └─ 用户选择跳过 → 降级为仅本地 InsightFace 指标
```

## 影响

- 新增 `scripts/check_config.py`
- SKILL.md 中「多模态自检」一节需重写，加入强制的 `check_config.py` 执行指令
- `check_config.py` 输出格式稳定后不得随意变更（防止 Agent 解析失败）
- 配置文件 `multimodal.json` 和 `check_config.py` 需要联动维护：新增 provider 时两边都要更新

## 不在此决策范围内

- 不改变 `_DEV_KEYS` 硬编码块的存在与否（按用户要求保留）
- 不改变 `multimodal_config.py` 的核心检测逻辑
- 不涉及 GUI 端的 API Key 配置面板（那是 Spec-002 的范围）
