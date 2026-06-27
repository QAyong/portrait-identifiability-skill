# 架构概览：肖像权可识别性检测 Skill

**更新日期：** 2026-06-27

## 模块关系

```
portrait-identifiability/
├── SKILL.md                 # Skill 入口（Agent 运行时读取）
├── requirements.txt         # Python 依赖
├── agents/
│   ├── multimodal.json      # 多模态 provider 配置
│   └── openai.yaml          # Agent 元数据
├── references/              # 合规措辞、报告模板、风险分级
├── scripts/
│   ├── check_config.py      # [新增] 配置自检脚本
│   ├── web_server.py        # [新增] FastAPI 后端入口
│   ├── web_ui/              # [新增] 前端静态资源
│   ├── portrait_clearance.py # 主比对流水线（CLI + Web 共用）
│   ├── visual_compare.py    # 统一视觉比对引擎
│   ├── multimodal_config.py # 多模态配置与检测
│   ├── face_engine.py       # InsightFace 人脸引擎
│   ├── html_report.py       # HTML 报告生成
│   ├── docx_report.py       # DOCX 报告生成
│   ├── baidu_image_search_playwright.py  # 百度识图采集
│   ├── collect_reverse_image_candidates.py # 聚合采集
│   ├── dedup_candidates.py  # 候选去重
│   ├── batch_clearance.py   # 批量排查
│   └── common.py            # 公共工具
└── docs/                    # [新增] 工程文档
    ├── adr/
    │   ├── adr-001-web-gui-exe.md
    │   └── adr-002-stable-config-detection.md
    ├── specs/
    │   ├── spec-001-check-config.md
    │   └── spec-002-web-gui-exe.md
    └── architecture/
        └── overview.md
```

## 数据流

### CLI 模式（现有）
```
用户命令 → portrait_clearance.py → multimodal_config.py（检测）→ face_engine.py（人脸）
                                   → visual_compare.py（比对）→ html_report.py / docx_report.py
```

### Agent 模式（Skill，现有）
```
SKILL.md → Agent 读取 → 执行 portrait_clearance.py → ... → 内置浏览器打开 HTML
```

### Agent 模式（改进后 - Spec-001）
```
SKILL.md → Agent 读取 → 【强制】执行 check_config.py → 解析配置状态 →
  ├─ 已配置 → 执行 portrait_clearance.py → ...
  └─ 未配置 → 提示用户 → 降级或等待配置
```

### Web GUI 模式（Spec-002）
```
用户双击 exe → web_server.py 启动 → 打开浏览器 →
  ├─ /api/compare → portrait_clearance.py（复用 CLI 流水线）
  ├─ /api/baidu/* → baidu 采集脚本
  ├─ /api/config → 读写 multimodal.json
  └─ 前端展示 HTML 报告 + 导出按钮
```

## 关键设计约束

1. **CLI 与 Web 共用核心流水线**：`portrait_clearance.py` 作为核心引擎，CLI 和 Web API 都调用同一个 `run_portrait_clearance()` 函数
2. **配置文件单点**：API Key 配置统一存储在 `agents/multimodal.json`
3. **报告生成独立**：HTML/DOCX/MD 报告生成器不依赖 CLI 或 Web 上下文
4. **安全措辞不变**：所有输出口径沿用 `references/` 下的合规模板
