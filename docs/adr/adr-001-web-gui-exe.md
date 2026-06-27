# ADR-001: Web 前端 + exe 后端的 GUI 架构

**日期：** 2026-06-27
**状态：** 已接受

## 背景

当前 portrait-identifiability Skill 仅为 CLI 工具，用户需要：
- 安装 Python 3.11+ 和所有依赖
- 通过命令行传参使用
- 手动打开 HTML/DOCX 报告

非技术用户（法务、合规、运营人员）无法直接使用。需要提供一个"双击即用"的桌面应用。

## 决策

采用 **Web 前端 + 本地 exe 后端** 架构：
- 后端：FastAPI + uvicorn，打包为单个 `.exe`（PyInstaller）
- 前端：HTML/CSS/JS，后端启动后自动打开系统浏览器
- 用户无需安装 Python，无需命令行操作

## 原因

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **tkinter 原生 GUI** | 零额外依赖，打包小 | 界面朴素、布局难维护、不支持富文本报告内嵌 | ❌ |
| **PySide6/Qt 原生** | 专业控件、功能强 | 打包体积大（~120MB）、许可证复杂、学习成本高 | ❌ |
| **Electron** | 前端生态丰富 | 体积巨大（~200MB+）、启动慢、依赖 Node.js | ❌ |
| **Web 后端 exe** | 界面灵活（HTML/CSS）、报告可内嵌展示、打包可控（~80-120MB 含模型） | 需要打开浏览器、多一个进程 | ✅ 选中 |

**关键理由：**
1. 项目已有完整的 HTML 报告模板，Web 前端可直接复用展示
2. HTML/CSS 做报告渲染远比原生 GUI 灵活
3. FastAPI 生态成熟，打包工具链（PyInstaller）稳定
4. 后端 exe 启动后自动打开浏览器，用户体验接近原生应用

## 影响

- 新增依赖：`fastapi`、`uvicorn`、`pyinstaller`
- 新增文件：`scripts/web_server.py`（后端入口）、`scripts/web_ui/`（前端静态资源）
- 现有 CLI 路径保持不变，Web 后端委托给 `portrait_clearance.py`
- 打包时需将 InsightFace 模型文件（`~/.insightface/models/buffalo_l/`）一并打入 exe
- 后端需处理进程生命周期：关闭浏览器窗口时自动退出

## 不在此决策范围内

- 云端部署 / SaaS 化（本次只做本地桌面应用）
- macOS / Linux 打包（本次只做 Windows `.exe`）
- 多用户并发支持（单用户本地使用）
