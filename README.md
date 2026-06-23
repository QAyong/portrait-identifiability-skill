# 肖像权可识别性检测 Skill

面向中国用户的肖像权可识别性与撞脸风险辅助分析工具，适用于 AI 生成虚拟人、数字人、头像、角色形象的撞脸排查。

## 功能模式

| 模式 | 说明 |
|---|---|
| **真人照片比对** (face_compare) | 两张真人照片的面部相似度分析 |
| **风格化可识别性** (stylized_identifiability) | 真人照片与漫改/卡通/AI 风格化图的特征对比 |
| **虚拟人脸排查** (virtual_face_clearance) | 百度识图反向搜索 + AI 候选图比对 |
| **批量审查** (batch_clearance) | 批量虚拟人物风险排查 |

## 快速开始

```bash
pip install -r portrait-identifiability/requirements.txt
```

```bash
# 两张图片比对
python portrait-identifiability/scripts/portrait_clearance.py query.png -r ref.png --use-multimodal

# 虚拟人脸排查（需先通过百度识图获取候选）
python portrait-identifiability/scripts/portrait_clearance.py virtual_face.png --candidates-file out/candidates.json --use-multimodal
```

## Skill 结构

```
portrait-identifiability/
├── SKILL.md              # Skill 定义
├── requirements.txt      # Python 依赖
├── agents/               # Agent 元数据
├── references/           # 风险分级、报告模板、合规边界
└── scripts/              # 核心脚本
```

## 重要说明

- **输出是风险提示，不是司法结论**——不得使用「确认侵权」「绝对安全」等措辞
- 使用百度识图前需确认用户授权
- 详见 `portrait-identifiability/SKILL.md` 和 `portrait-identifiability/references/`
