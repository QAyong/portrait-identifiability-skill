# AGENTS.md

## 项目概述

本仓库是一个 Codex Skill 项目：「肖像权可识别性检测」（portrait-identifiability），用于辅助判断 AI 生成的虚拟人脸、数字人、角色形象等是否存在肖像权撞脸风险。

## 目录结构

- `portrait-identifiability/` — Skill 主体（SKILL.md + scripts + references + agents）
- `out/` — 测试输出（百度识图候选结果、图片等）
- `test-*/` — 各测试场景的输出产物
- `reverse-candidates-face1/` — 反向图片搜索候选结果

## 编码规范

- 脚本使用 Python 3.11+，依赖见 `portrait-identifiability/requirements.txt`
- 所有脚本放在 `portrait-identifiability/scripts/` 下
- 主入口为 `portrait-identifiability/scripts/portrait_clearance.py`
- 输出语言默认为中文，措辞审慎合规，不得输出侵权结论
- `portrait-identifiability/references/` 下的文档为 Skill 运行时加载的参考文件

## 运行与测试

安装依赖：
```bash
pip install -r portrait-identifiability/requirements.txt
```

主入口用法：
```bash
# 两张图片直接比对
python portrait-identifiability/scripts/portrait_clearance.py query.png -r ref.png --use-multimodal

# 单张图片 + 百度识图候选
python portrait-identifiability/scripts/portrait_clearance.py virtual_face.png --candidates-file out/candidates.json --use-multimodal
```

## Skill 发布

本 Skill 通过 `portrait-identifiability/SKILL.md` 定义。修改 Skill 行为时：
1. 优先修改 `portrait-identifiability/SKILL.md` 正文
2. 如需更新 agent 元数据，同步修改 `portrait-identifiability/agents/`
3. 参考文件放在 `portrait-identifiability/references/` 下
