---
name: portrait-identifiability
description: 面向中国用户的肖像权可识别性与撞脸风险辅助分析 skill。适用于 AI 生成虚拟人/数字人/头像/角色形象的撞脸排查。默认使用中文输出，结合百度识图检索路径，使用审慎合规表达。
---

# 肖像权可识别性检测

本 skill 用于辅助判断 AI 生成的虚拟人脸、数字人、AI 角色等形象是否存在肖像权撞脸风险。输出应作为合规审查和人工复核材料，不得写成司法鉴定、律师意见或法院结论。

## 核心架构：统一流水线

输入归一化: 用户上传 1 张或 2 张图片，统一构建为 (query, reference) 比对对。

每个比对对执行:
1. InsightFace 本地预检（人脸检测 + embedding + 质量评估）
2. 多模态 AI 统一比对（成分判定 + Path A/B 分析，单次 API 调用）
3. 合并输出风险等级 + 依据 + 报告

Path A (双方 realistic): AI 结合 InsightFace 余弦相似度做融合判断
Path B (任一方 stylized): AI 纯视觉特征比对，InsightFace 数据仅作参考

## 多模态自检

Skill 启动时自动检测多模态能力，按以下优先级:

1. PORTRAIT_AGENT_MULTIMODAL=true - 使用 agent 自带视觉能力
2. OPENAI_API_KEY 或 DOUBAO_API_KEY 已设置 - 使用对应 API
3. 都没有 - 降级为仅本地 InsightFace 指标，提示用户配置

### API Key 获取地址

- **豆包 (Doubao)**: https://console.volcengine.com/ark/region:ark+cn-beijing/model/detail?Id=doubao-seed-2-0-pro
- **OpenAI**: https://platform.openai.com/api-keys

## 主入口: portrait_clearance

用法示例:

```
# 2 张图片直接比对
python portrait-identifiability/scripts/portrait_clearance.py query.png -r ref.png --use-multimodal

# 1 张图片 + 百度识图候选
python portrait-identifiability/scripts/portrait_clearance.py virtual_face.png --candidates-file out/candidates.json --use-multimodal

# 指定多模态提供方
python portrait-identifiability/scripts/portrait_clearance.py query.png -r ref.png --use-multimodal --vision-provider doubao
```

## 辅助脚本

*公共模块：*
- `common.py` — 公共工具（图片读写、相似度计算、JSON 序列化）
- `face_engine.py` — InsightFace 人脸引擎（线程安全单例）
- `multimodal_config.py` — 多模态配置与自检（API Key 检测、提供方解析）

*核心流水线：*
- `portrait_clearance.py` — 主入口：统一撞脸排查流水线
- `visual_compare.py` — 统一视觉比对引擎（InsightFace 预检 + 多模态 AI 比对）
- `batch_clearance.py` — 批量排查（委托给 portrait_clearance）
- `virtual_face_clearance.py` — 兼容包装器（委托给 portrait_clearance）

*报告生成：*
- `html_report.py` — HTML 页面报告生成器（base64 内嵌图片，纯展示）
- `docx_report.py` — DOCX 文档报告生成器（A4 排版，紧凑表格）

*检索采集：*
- `baidu_image_search_playwright.py` — 百度识图 Playwright 采集器
- `collect_reverse_image_candidates.py` — 百度识图聚合采集器
- `prepare_search_image.py` — 为外部检索裁剪人脸图

*候选图处理：*
- `dedup_candidates.py` — 候选图前置去重（字节 + pHash 可选 ArcFace 双条件）

## 输出与报告

排查完成后在输出目录生成四份文件：

- `clearance-report.html` — **HTML 页面报告**（图片 base64 内嵌，纯净展示，无按钮/脚本）
- `clearance-report.docx` — **DOCX 文档报告**（A4 排版，紧凑表格，适合存档与分发）
- `clearance-report.md` — Markdown 文本报告
- `clearance-result.json` — 结构化 JSON 结果

### Agent 行为要求

**脚本执行完成后，Agent 必须自动使用内置浏览器打开 HTML 报告，并将 DOCX 文件提供给用户。**

方法：从 stdout 输出中提取 `HTML: <path>` 和 `DOCX: <path>` 行，获取报告路径，
然后使用 `browser:control-in-app-browser` skill 打开 `file:///<path>` 展示 HTML 报告，
同时告知用户 DOCX 文件路径供下载/打开。

脚本本身不再调用系统浏览器（已移除 `webbrowser.open`），Agent 不要改用 `os.startfile` / `Start-Process` / `webbrowser` 等方式打开外部浏览器，必须通过内置浏览器 skill 展示报告。

用户无需手动打开文件，HTML 报告应直接展示在 Codex 侧边栏浏览器中，DOCX 文件路径应明确告知。

## 百度识图候选去重

使用 `collect_reverse_image_candidates.py` 采集百度识图候选后，会对候选图做前置去重，去掉同一张照片的重复变体（缩略图/压缩/格式变体），只保留最清晰一张；撞脸的不同照片不会误并。去重结果写入 `manifest.json` 的 `dedup_stats`（含去重前后数量、被丢弃项及原因）和 `dedup_notice`。

去重提供两种视觉模式，执行百度识图采集前 Agent 应向用户说明区别并由用户选择：

| 模式 | 速度 | 原理 | 适用场景 |
|------|------|------|--------|
| **pHash 快速模式**（默认） | 30~40 张约 1 秒 | 感知哈希衡量整图相似度，同图变体距离 0~2、撞脸不同照 24+ | 绝大多数场景，推荐优先使用 |
| **ArcFace 双条件模式**（`--use-face-dedup`） | 30~40 张约 90 秒 | pHash 基础上叠加人脸 embedding 确认（需 InsightFace，CPU 每张约 2.4 秒） | 对去重精度有更高要求、不介意等待时选择 |

两种模式第一层字节去重（完全相同文件）相同，区别仅在第二层视觉去重。Agent 提示示例：「百度识图候选支持两种去重模式——pHash 快速模式约 1 秒，ArcFace 双条件模式约 90 秒但更稳，默认用快速模式，需要更稳的请说明。」

## 百度识图上传约定

本 Skill 的百度识图、反向图片搜索、外部候选采集和相关测试用例默认包含外部上传动作。用户触发这些能力时，视为已授权上传任务所需图片；不要再将上传确认作为阻塞步骤。

执行时直接说明将使用外部检索链路并继续操作。若外部服务失败、验证码阻断、网络不可用或页面结构变化，再报告失败原因并给出替代方案。

## 安全措辞

推荐: 当前检索范围内未发现高相似候选 / 存在疑似撞脸风险 / 建议人工复核
避免: 确认侵权 / 确认同一人 / 绝对安全 / 可以放心商用

## 参考文件

- references/risk-rubric.md      风险分级与特征比对维度
- references/report-templates.md  中文报告模板
- references/external-search-compliance.md  合规边界
