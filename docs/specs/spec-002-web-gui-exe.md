# Spec-002: Web GUI 桌面应用（后端 exe + 浏览器前端）

**日期：** 2026-06-27
**状态：** 待开发

## 背景

当前 Skill 仅 CLI 可用，非技术用户（法务、合规、运营）无法直接使用。需要提供"双击即用"的桌面应用。

详见 ADR-001。

## 需求边界

**包含：**
- FastAPI 后端，提供完整的撞脸排查 REST API
- Web 前端界面（HTML/CSS/JS），后端启动后自动在浏览器打开
- 单图对比、百度识图候选采集与比对、批量排查
- 配置面板：用户可在界面中写入/修改 API Key（持久化到配置文件）
- HTML 报告在浏览器中内嵌展示
- 全部功能打包为单个 `.exe`（PyInstaller），含 InsightFace 模型

**不包含：**
- 云端部署 / 多用户并发
- macOS / Linux 打包
- 用户登录/权限系统
- Docker 镜像发布

## 验收标准

- [ ] 双击 `.exe` 启动后，自动打开浏览器显示 GUI 首页
- [ ] 首页支持拖拽/选择查询图 + 参照图，点击"开始比对"后显示进度和结果
- [ ] 比对完成后，HTML 报告在页面内嵌展示（而非下载文件）
- [ ] 提供"导出 DOCX"按钮，点击后下载 .docx 文件
- [ ] 百度识图流程：上传图片 → 采集候选 → 自动去重 → 逐一比对 → 生成报告
- [ ] 配置面板可输入 OPENAI_API_KEY / DOUBAO_API_KEY，保存后立即可用
- [ ] 配置面板显示当前检测状态（已配置/未配置/Agent Native）
- [ ] 关闭浏览器窗口后，后端进程自动退出
- [ ] 单 `.exe` 文件可在无 Python 环境的 Windows 10/11 上运行

## 场景描述

### 场景 A：快速单图比对

1. 用户双击 `portrait-clearance.exe`
2. 浏览器自动打开 `http://127.0.0.1:17890`
3. 首页展示「单图比对」卡片
4. 用户拖入查询图和参照图
5. 点击「开始比对」
6. 页面显示进度条，完成后展示 HTML 报告
7. 用户点击「导出 DOCX」下载 Word 文档

### 场景 B：百度识图全流程

1. 用户选择「百度识图排查」
2. 上传待排查图片
3. 系统自动裁剪人脸区域 → 上传百度识图 → 采集候选 URL
4. 下载候选图片 → 去重 → 逐一与查询图比对
5. 实时展示每个候选的比对进度
6. 最终展示汇总 HTML 报告
7. 支持导出 DOCX

### 场景 C：首次使用 - 配置 API Key

1. 用户启动 exe，页面顶部显示黄色提示条：「未配置多模态引擎，部分功能不可用」
2. 用户点击「配置」进入配置面板
3. 选择 provider（OpenAI / 豆包），输入 API Key
4. 点击「保存并检测」
5. 提示条变为绿色：「✅ OpenAI 已配置」
6. 返回首页正常使用

### 场景 D：关闭应用

1. 用户关闭浏览器标签页
2. 后端检测到无活跃连接，5 秒后自动退出
3. 或用户点击界面中的「退出」按钮，后端立即关闭

## API 设计（后端）

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/health` | GET | 健康检查 + provider 状态 |
| `/api/compare` | POST | 单对图片比对（multipart upload） |
| `/api/compare/batch` | POST | 批量比对 |
| `/api/baidu/search` | POST | 百度识图采集 |
| `/api/baidu/candidates` | GET | 查询采集进度/结果 |
| `/api/baidu/compare` | POST | 对采集结果逐一比对 |
| `/api/config` | GET | 获取当前配置状态 |
| `/api/config` | PUT | 更新 API Key 配置 |
| `/api/export/docx` | POST | 导出 DOCX 报告 |
| `/api/shutdown` | POST | 关闭后端服务 |

## 前端页面结构

```
首页 (/)
├── 导航栏（首页 | 批量排查 | 百度识图 | 配置）
├── 状态提示条（配置状态）
├── 单图比对卡片
│   ├── 查询图拖拽区
│   ├── 参照图拖拽区
│   └── 比对按钮
└── 结果展示区（内嵌 HTML 报告）

批量排查 (/batch)
百度识图 (/baidu)
配置 (/config)
```

## 打包要求

- 打包工具：PyInstaller
- 模式：`--onefile`（单 exe）
- 包含内容：
  - Python 3.11+ 运行时
  - 所有 pip 依赖
  - InsightFace `buffalo_l` 模型文件（约 330MB）
  - Playwright Chromium（百度识图采集需要，约 150MB）
  - 前端静态文件（HTML/CSS/JS/图标）
- 预估 exe 体积：500-700MB（含模型 + Chromium）
- 优化方向：如用户不需要百度识图功能，可提供 Lite 版不含 Chromium（约 350MB）

## 相关 ADR

- [adr-001-web-gui-exe.md](adr-001-web-gui-exe.md)
