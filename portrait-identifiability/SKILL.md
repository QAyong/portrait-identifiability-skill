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

- portrait_clearance.py     主入口：统一撞脸排查流水线
- visual_compare.py          统一视觉比对引擎
- multimodal_config.py       多模态配置与自检
- face_engine.py             InsightFace 人脸引擎
- common.py                  公共工具
- prepare_search_image.py    为百度识图裁剪人脸图
- collect_reverse_image_candidates.py  百度识图聚合采集器
- baidu_image_search_playwright.py     百度识图 Playwright 采集器
- virtual_face_clearance.py  兼容包装器
- batch_clearance.py         批量排查


## 输出与报告

排查完成后在输出目录生成三份文件：

- `clearance-report.html` — **HTML 页面报告**（图片 base64 内嵌，可导出 PDF，可直接分享）
- `clearance-report.md` — Markdown 文本报告
- `clearance-result.json` — 结构化 JSON 结果

### Agent 行为要求

**脚本执行完成后，Agent 必须自动使用内置浏览器打开 HTML 报告。**

方法：从 stdout 输出中提取 `HTML: <path>` 行，获取报告路径，
然后使用 `browser:control-in-app-browser` skill 打开 `file:///<path>`。

用户无需手动打开文件，报告应直接展示在 Codex 侧边栏浏览器中。

## 外部上传确认

使用百度识图前需确认用户授权。优先一次性确认本次任务:

> 请确认是否允许将本次提供的全部图片上传到百度识图进行测试。

## 安全措辞

推荐: 当前检索范围内未发现高相似候选 / 存在疑似撞脸风险 / 建议人工复核
避免: 确认侵权 / 确认同一人 / 绝对安全 / 可以放心商用

## 参考文件

- references/risk-rubric.md      风险分级与特征比对维度
- references/report-templates.md  中文报告模板
- references/external-search-compliance.md  合规边界
