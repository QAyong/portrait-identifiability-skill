# -*- coding: utf-8 -*-
"""HTML 报告生成器 — 肖像权可识别性检测

生成自包含的 HTML 页面报告，图片以 base64 内嵌，支持：
- 浏览器直接打开查看
- 一键导出 PDF（window.print）
- 一键下载 HTML 文件
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from common import data_url_for_image, risk_label, risk_score

_CSS = """
:root {
  --bg: #fafaf9;
  --card-bg: #ffffff;
  --text: #1c1917;
  --text-secondary: #57534e;
  --border: #e7e5e4;
  --accent: #2563eb;
  --risk-high: #dc2626;
  --risk-high-bg: #fef2f2;
  --risk-medium: #d97706;
  --risk-medium-bg: #fffbeb;
  --risk-lowmid: #ca8a04;
  --risk-lowmid-bg: #fefce8;
  --risk-low: #16a34a;
  --risk-low-bg: #f0fdf4;
  --risk-undetermined: #78716c;
  --risk-undetermined-bg: #fafaf9;
  --radius: 8px;
  --shadow: 0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Microsoft YaHei", "Helvetica Neue", sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}

/* ── Toolbar ── */
.toolbar {
  position: sticky; top: 0; z-index: 10;
  display: flex; gap: 8px; justify-content: flex-end;
  padding: 10px 24px;
  background: rgba(255,255,255,.85);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
}
.toolbar button {
  padding: 6px 16px; border-radius: 6px; border: 1px solid var(--border);
  background: var(--card-bg); color: var(--text);
  font-size: 13px; cursor: pointer;
  transition: all .15s;
}
.toolbar button:hover { border-color: var(--accent); color: var(--accent); }
.toolbar button.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.toolbar button.primary:hover { opacity: .85; }

/* ── Container ── */
.container { max-width: 960px; margin: 0 auto; padding: 32px 24px 64px; }

/* ── Header ── */
.report-header { margin-bottom: 40px; }
.report-header h1 { font-size: 28px; font-weight: 700; margin-bottom: 8px; }
.report-header .meta { color: var(--text-secondary); font-size: 14px; }

/* ── Summary card ── */
.summary-card {
  display: flex; gap: 24px; align-items: flex-start;
  background: var(--card-bg); border-radius: var(--radius);
  box-shadow: var(--shadow); padding: 24px; margin-bottom: 32px;
}
.summary-card .query-img { flex: 0 0 240px; }
.summary-card .query-img img {
  width: 100%; border-radius: var(--radius);
  border: 2px solid var(--border);
}
.summary-card .query-img .label {
  text-align: center; font-size: 12px; color: var(--text-secondary);
  margin-top: 6px;
}
.summary-card .summary-info { flex: 1; }
.summary-card .summary-info h2 { font-size: 18px; margin-bottom: 12px; }
.summary-card .summary-info .stat-row {
  display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 12px;
}
.summary-card .summary-info .stat-item { font-size: 14px; }
.summary-card .summary-info .stat-item strong { font-weight: 600; }
.summary-card .summary-info .verdict {
  padding: 12px 16px; border-radius: 6px; font-size: 14px; line-height: 1.5;
}
.summary-card .summary-info .verdict.high { background: var(--risk-high-bg); color: var(--risk-high); }
.summary-card .summary-info .verdict.medium { background: var(--risk-medium-bg); color: var(--risk-medium); }
.summary-card .summary-info .verdict.low { background: var(--risk-low-bg); color: var(--risk-low); }
.summary-card .summary-info .verdict.low_to_medium { background: var(--risk-lowmid-bg); color: var(--risk-lowmid); }
.summary-card .summary-info .verdict.unable_to_determine { background: var(--risk-undetermined-bg); color: var(--risk-undetermined); }
.summary-card .summary-info .verdict-reasons {
  margin-top: 10px;
  padding: 10px 14px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}
.summary-card .summary-info .verdict-reasons strong { color: var(--text); }
.summary-card .summary-info .verdict-reasons ul {
  margin-top: 4px;
  padding-left: 18px;
}

/* ── Risk distribution ── */
.risk-dist { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.risk-dist .badge {
  padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600;
}
.badge.high { background: var(--risk-high-bg); color: var(--risk-high); }
.badge.medium { background: var(--risk-medium-bg); color: var(--risk-medium); }
.badge.low_to_medium { background: var(--risk-lowmid-bg); color: var(--risk-lowmid); }
.badge.low { background: var(--risk-low-bg); color: var(--risk-low); }
.badge.unable_to_determine { background: var(--risk-undetermined-bg); color: var(--risk-undetermined); }

/* ── Section headers ── */
.section { margin-bottom: 40px; }
.section h2 {
  font-size: 20px; font-weight: 700; margin-bottom: 16px;
  padding-bottom: 8px; border-bottom: 2px solid var(--border);
}

/* ── Comparison cards ── */
.comp-card {
  background: var(--card-bg); border-radius: var(--radius);
  box-shadow: var(--shadow); padding: 20px; margin-bottom: 16px;
}
.comp-card .comp-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px; flex-wrap: wrap; gap: 8px;
}
.comp-card .comp-header .comp-title { font-weight: 600; font-size: 15px; }
.comp-card .comp-images {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}
.comp-card .comp-images .img-box {
  min-width: 0;
}
.comp-card .comp-images .img-box img {
  width: 100%;
  aspect-ratio: 4 / 5;
  height: auto;
  max-height: 520px;
  object-fit: contain;
  background: #f5f5f4;
  border-radius: var(--radius);
  border: 1px solid var(--border);
}
.comp-card .comp-images .img-box .img-label {
  font-size: 12px; color: var(--text-secondary); margin-top: 4px;
  text-align: center;
}
.comp-card .comp-details {
  font-size: 13px; color: var(--text-secondary);
  display: flex; gap: 16px; flex-wrap: wrap;
}
.comp-card .comp-details .detail-item strong { color: var(--text); }
.comp-card .comp-basis {
  margin-top: 12px; font-size: 13px; color: var(--text-secondary);
  padding: 10px 14px; background: #f5f5f4; border-radius: 6px;
  border-left: 3px solid var(--border);
}

/* ── Feature comparison table ── */
.feature-section {
  margin-top: 16px;
}
.feature-section h4 {
  font-size: 15px;
  margin-bottom: 8px;
}
.feature-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 13px;
  color: var(--text);
  border: 1px solid var(--border);
}
.feature-table th,
.feature-table td {
  border: 1px solid var(--border);
  padding: 8px 10px;
  vertical-align: top;
  text-align: left;
}
.feature-table th {
  background: #f5f5f4;
  font-weight: 600;
}
.feature-table th:nth-child(1),
.feature-table td:nth-child(1) {
  width: 22%;
}
.feature-table th:nth-child(2),
.feature-table td:nth-child(2) {
  width: 18%;
}
.fsim-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.fsim-badge.high { background: var(--risk-high-bg); color: var(--risk-high); }
.fsim-badge.medium { background: var(--risk-medium-bg); color: var(--risk-medium); }
.fsim-badge.low { background: var(--risk-lowmid-bg); color: var(--risk-lowmid); }
.fsim-badge.none { background: var(--risk-undetermined-bg); color: var(--risk-undetermined); }
.fusion-note {
  margin-top: 12px;
  font-size: 13px;
  color: var(--text-secondary);
  padding: 10px 14px;
  background: #f5f5f4;
  border-radius: 6px;
}
.target-warning {
  margin-top: 12px;
  padding: 10px 14px;
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-left: 3px solid #f97316;
  border-radius: 6px;
  color: #9a3412;
  font-size: 13px;
  line-height: 1.6;
}

/* ── Limitations ── */
.limitation-text {
  font-size: 13px; color: var(--text-secondary); line-height: 1.7;
}

/* ── Print styles ── */
@media print {
  .toolbar { display: none; }
  body { background: #fff; }
  .container { max-width: 100%; padding: 0; }
  .comp-card, .summary-card { box-shadow: none; break-inside: avoid; }
  @page { margin: 16mm; }
}

/* ── Responsive ── */
@media (max-width: 640px) {
  .summary-card { flex-direction: column; }
  .summary-card .query-img { flex: 0 0 auto; max-width: 200px; }
  .comp-card .comp-images { grid-template-columns: 1fr; }
}
"""


def _risk_badge_html(level: str) -> str:
    cls = level if level in ("high", "medium", "low_to_medium", "low", "unable_to_determine") else "unable_to_determine"
    return f'<span class="badge {cls}">{risk_label(level)}</span>'


def _feature_similarity_label(sim: str) -> str:
    """特征相似度标签"""
    return {"high": "高度相似", "medium": "中等相似", "low": "低度相似", "none": "无明显相似"}.get(sim, sim or "-")

def _feature_similarity_class(sim: str) -> str:
    """特征相似度 CSS 类"""
    return sim if sim in ("high", "medium", "low", "none") else "none"


def _collect_unable_reasons(results: list[dict[str, Any]], limit: int = 4) -> list[str]:
    reasons: list[str] = []
    for item in results:
        if item.get("risk_level") != "unable_to_determine":
            continue
        precheck = item.get("local_precheck", {})
        for reason in precheck.get("reliability_issues", []) or []:
            if reason and reason not in reasons:
                reasons.append(str(reason))
        for reason in item.get("limitations", []) or []:
            if reason and reason not in reasons:
                reasons.append(str(reason))
        ai = item.get("ai_visual_comparison", {})
        for reason in ai.get("limitations", []) or []:
            if reason and reason not in reasons:
                reasons.append(str(reason))
        for reason in item.get("basis", []) or []:
            text = str(reason)
            if any(keyword in text for keyword in ["质量", "未检测", "多张人脸", "无法可靠", "比对失败"]):
                if text not in reasons:
                    reasons.append(text)
        if len(reasons) >= limit:
            break
    return reasons[:limit]


def _build_feature_table(feature_comparison: dict[str, Any]) -> str:
    """构建结构化特征对比表格 HTML。"""
    if not feature_comparison:
        return ""
    feature_labels = {
        "face_shape": "脸型与下颌线",
        "facial_layout": "五官整体布局",
        "eyes_brows": "眼型与眉形",
        "nose_mouth": "鼻型与嘴型",
        "hair_hairline": "发型与发际线",
        "distinctive_features": "标志性特征",
    }
    rows = []
    for key, label in feature_labels.items():
        item = feature_comparison.get(key)
        if not item or not isinstance(item, dict):
            continue
        sim = item.get("similarity", "-")
        note = item.get("note", "-")
        sim_label = _feature_similarity_label(sim)
        sim_cls = _feature_similarity_class(sim)
        rows.append(f'<tr><td>{label}</td><td><span class="fsim-badge {sim_cls}">{sim_label}</span></td><td>{note}</td></tr>')
    if not rows:
        return ""
    return '<div class="feature-section"><h4>多模态面部特征分析</h4><table class="feature-table"><thead><tr><th>特征维度</th><th>相似度</th><th>分析说明</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>'


def generate_html_report(
    query_image: str,
    results: list[dict[str, Any]],
    output_dir: str,
    multimodal_provider: str = "无",
    total_pairs: int = 0,
) -> str:
    """生成自包含 HTML 报告，返回 HTML 字符串。"""

    query_name = Path(query_image).name
    query_data_uri = data_url_for_image(query_image)

    # ── 统计风险分布 ──
    risk_counts: dict[str, int] = {}
    for r in results:
        rl = r.get("risk_level", "unable_to_determine")
        risk_counts[rl] = risk_counts.get(rl, 0) + 1

    highest_risk = "unable_to_determine"
    for rl in ["high", "medium", "low_to_medium", "low"]:
        if risk_counts.get(rl, 0) > 0:
            highest_risk = rl
            break

    # ── 综合结论 ──
    verdict_map = {
        "high": "存在较高撞脸风险，建议人工复核。本结果不能替代司法鉴定、律师意见或法院判断。",
        "medium": "存在一定撞脸风险，建议人工复核。本结果不能替代司法鉴定、律师意见或法院判断。",
        "low_to_medium": "在比对范围内存在局部相似，公开传播或商业使用前建议人工确认。",
        "low": "在当前比对范围内未发现高相似候选对象。但这不代表不存在其他肖像权风险。",
        "unable_to_determine": "部分或全部比对对象无法可靠判断，建议人工复核。",
    }
    verdict = verdict_map.get(highest_risk, verdict_map["unable_to_determine"])
    unable_reasons_html = ""
    if highest_risk == "unable_to_determine":
        unable_reasons = _collect_unable_reasons(results)
        if unable_reasons:
            items = "".join(f"<li>{reason}</li>" for reason in unable_reasons)
            unable_reasons_html = f'<div class="verdict-reasons"><strong>无法判断原因：</strong><ul>{items}</ul></div>'

    # ── 风险分布 badges ──
    risk_badges_html = ""
    for rl in ["high", "medium", "low_to_medium", "low", "unable_to_determine"]:
        if risk_counts.get(rl, 0) > 0:
            risk_badges_html += f'<span class="badge {rl}">{risk_label(rl)}：{risk_counts[rl]} 个</span>\n'

    # ── 比对卡片 ──
    comp_cards_html = ""
    for item in results:
        pi = item.get("pair_info", {})
        ref_path = item.get("image_b", "")
        ref_name = Path(ref_path).name if ref_path else "-"
        ref_data_uri = data_url_for_image(ref_path) if ref_path else ""
        rank = pi.get("rank", "-")
        source = pi.get("source", "unknown")
        path_label = item.get("analysis_path", "-")
        risk_lvl = item.get("risk_level", "unable_to_determine")
        overall_sim = item.get("overall_similarity")
        sim_str = f"{overall_sim:.2f}" if overall_sim is not None else "-"

        # 依据
        basis_items: list[str] = []
        ai = item.get("ai_visual_comparison", {})
        if ai:
            basis_items = ai.get("basis", [])
        if not basis_items:
            basis_items = item.get("basis", [])
        basis_html = "<br>".join(basis_items) if basis_items else "无"

        # 本地预检信息
        precheck = item.get("local_precheck", {})
        face_sim = precheck.get("face_similarity")
        is_path_b = str(item.get("analysis_path", "")).upper() == "B"
        face_sim_str = f"InsightFace 余弦相似度: {face_sim:.4f}" if face_sim is not None and not is_path_b else ""
        embedding_note = "风格化路径：不采用本地人脸 embedding 作为判断依据" if is_path_b else ""
        faces_a = precheck.get("faces_a", "?")
        faces_b = precheck.get("faces_b", "?")
        quality_a = precheck.get("quality_a", {}).get("grade", "?")
        quality_b = precheck.get("quality_b", {}).get("grade", "?")
        target_warning_html = ""
        if isinstance(faces_a, int) and faces_a > 1:
            target_warning_html = '<div class="target-warning"><strong>目标对象提示：</strong>图片 A 检测到多张人脸，当前结果无法确认比对目标。建议先裁剪到单一目标人脸，或指定需要排查的具体人物后重新检测。</div>'
        elif isinstance(faces_b, int) and faces_b > 1:
            target_warning_html = '<div class="target-warning"><strong>目标对象提示：</strong>图片 B 检测到多张人脸，当前结果无法确认比对目标。建议先裁剪到单一目标人脸，或指定需要排查的具体人物后重新检测。</div>'

        # ── 多模态特征对比 ──
        feature_html = ""
        fusion_note_html = ""
        if ai:
            fc = ai.get("feature_comparison")
            if fc:
                feature_html = _build_feature_table(fc)
            # Path A 融合说明
            fusion = ai.get("insightface_fusion_note", "")
            if fusion:
                fusion_note_html = f'<div class="fusion-note">{fusion}</div>'

        comp_cards_html += f"""
<div class="comp-card">
  <div class="comp-header">
    <span class="comp-title">#{rank} — {ref_name[:60]}</span>
    {_risk_badge_html(risk_lvl)}
  </div>
  <div class="comp-images">
    <div class="img-box">
      <img src="{query_data_uri}" alt="查询图" loading="lazy" />
      <div class="img-label">查询图：{query_name}</div>
    </div>
    <div class="img-box">
      <img src="{ref_data_uri}" alt="候选图" loading="lazy" />
      <div class="img-label">候选图：{ref_name}</div>
    </div>
  </div>
  <div class="comp-details">
    <span class="detail-item"><strong>来源：</strong>{source}</span>
    <span class="detail-item"><strong>分析路径：</strong>{path_label}</span>
    <span class="detail-item"><strong>整体相似度：</strong>{sim_str}</span>
    <span class="detail-item"><strong>人脸数：</strong>A{faces_a} / B{faces_b}</span>
    <span class="detail-item"><strong>画质：</strong>A-{quality_a} / B-{quality_b}</span>
    {f'<span class="detail-item"><strong>{face_sim_str}</strong></span>' if face_sim_str else ''}
    {f'<span class="detail-item"><strong>{embedding_note}</strong></span>' if embedding_note else ''}
  </div>
  {target_warning_html}
  {feature_html}
  {fusion_note_html}
  <div class="comp-basis">{basis_html}</div>
</div>"""

    # ── 组装完整 HTML ──
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>肖像权可识别性撞脸排查报告 — {query_name}</title>
<style>{_CSS}</style>
</head>
<body>

<div class="toolbar">
  <button onclick="downloadHTML()">下载 HTML</button>
  <button class="primary" onclick="window.print()">导出 PDF</button>
</div>

<div class="container">

  <div class="report-header">
    <h1>肖像权可识别性撞脸排查报告</h1>
    <p class="meta">查询图：{query_name} &nbsp;|&nbsp; 比对数：{total_pairs} &nbsp;|&nbsp; 多模态引擎：{multimodal_provider}</p>
  </div>

  <div class="summary-card">
    <div class="query-img">
      <img src="{query_data_uri}" alt="查询图" />
      <div class="label">查询图</div>
    </div>
    <div class="summary-info">
      <h2>综合风险等级：{_risk_badge_html(highest_risk)}</h2>
      <div class="risk-dist">{risk_badges_html}</div>
      <div class="verdict {highest_risk}">{verdict}</div>
      {unable_reasons_html}
    </div>
  </div>

  <div class="section">
    <h2>详细比对结果</h2>
    {comp_cards_html}
  </div>

  <div class="section">
    <h2>限制说明</h2>
    <p class="limitation-text">
      本结果仅表示在当前比对范围内的撞脸风险排查，不代表不存在其他肖像权风险。<br>
      比对结果可能受图片质量、角度、遮挡、风格化程度和候选图来源影响。<br>
      本结果不能替代司法鉴定、律师意见或法院判断。
    </p>
  </div>

</div>

<script>
function downloadHTML() {{
  var html = document.documentElement.outerHTML;
  var blob = new Blob(['<!DOCTYPE html>\n' + html], {{type: 'text/html'}});
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'portrait-clearance-report.html';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}}
</script>

</body>
</html>"""

    return html


def save_html_report(
    query_image: str,
    results: list[dict[str, Any]],
    output_dir: str | Path,
    multimodal_provider: str = "无",
    total_pairs: int = 0,
) -> str:
    """生成并保存 HTML 报告，返回文件路径。"""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    html = generate_html_report(
        query_image=query_image,
        results=results,
        output_dir=str(out_dir),
        multimodal_provider=multimodal_provider,
        total_pairs=total_pairs,
    )

    report_path = out_dir / "clearance-report.html"
    report_path.write_text(html, encoding="utf-8")
    return str(report_path)
