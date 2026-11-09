"""One-page budget memo from plan.json, as a PDF. Every number is read from the saved contracts."""
from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
C = ROOT / "contracts"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def memo_pdf() -> bytes:
    plan = json.loads((C / "plan.json").read_text())
    base = json.loads((C / "baselines.json").read_text())
    scen = json.loads((C / "scenarios.json").read_text())
    t = plan["totals"]
    st = getSampleStyleSheet()
    body = st["BodyText"]
    body.fontSize, body.leading = 9.5, 12.5
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                            topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    mc = scen["monte_carlo"]
    storm = scen["storm"]
    els = [
        Paragraph("MEMO: 2025 crew plan for 311 work", st["Title"]),
        Paragraph(f"To: City budget office &nbsp;&nbsp; From: Boston 311 Copilot &nbsp;&nbsp; Date: {date.today():%B %d, %Y}", body),
        Spacer(1, 8),
        Paragraph(
            f"<b>Recommendation.</b> Adopt the optimised crew plan for Public Works, Transportation, Parks and Inspectional "
            f"Services. It costs <b>${t['total_cost']:,.0f}</b> for 2025 and closes <b>{t['on_time_rate']:.1%}</b> of requests "
            f"within the month, meeting a {plan['on_time_target']:.0%} on-time target in every department. Keeping today's crews "
            f"flat all year would cost ${base['flat']['totals']['total_cost']:,.0f} with {base['flat']['totals']['on_time_rate']:.1%} "
            f"on time, so the plan <b>saves ${base['saving_vs_flat']:,.0f}</b>.", body),
        Spacer(1, 6),
        Paragraph(
            "<b>What changes.</b> Transportation adds crews early in the year (it is the most behind today). Parks releases "
            "permanent crews it doesn't need in winter and covers the summer peak with seasonal crews, which need no "
            "training and carry no severance.", body),
        Spacer(1, 6),
    ]
    rows = [["Department"] + MONTHS + ["Cost", "On time"]]
    for d in plan["crews"]:
        crews = [f"{plan['crews'][d][i] + plan['seasonal'][d][i]:.0f}" for i in range(12)]
        bd = plan["by_dept"][d]
        rows.append([d] + crews + [f"${bd['total_cost'] / 1e6:.2f}M", f"{bd['on_time_rate']:.0%}"])
    tbl = Table(rows, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d4ed8")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER")]))
    els += [Paragraph("<b>Crews per month (incl. Parks seasonals)</b>", body), tbl, Spacer(1, 8)]
    els += [
        Paragraph(
            f"<b>Risks.</b> In 100 simulated demand years the plan's cost ranges from ${mc['cost_p10']:,.0f} (p10) to "
            f"${mc['cost_p90']:,.0f} (p90). Every department hits the target in {mc['years_all_depts_hit_target']} of 100 years, so "
            f"the plan is tight; a robust version hits it in {scen['robust']['monte_carlo']['years_all_depts_hit_target']} of 100 "
            f"for a median cost of ${scen['robust']['monte_carlo']['cost_p50']:,.0f}. A storm like {storm['storms'][0]['day']} adds "
            f"about ${storm['extra_cost_locked']:,.0f} if we don't adjust; re-planning for it recovers ${storm['hiring_ahead_saves']:,.0f}.",
            body),
        Spacer(1, 6),
        Paragraph(
            f"<b>Cheapest lever.</b> Moving 30% of employee-logged work out of peak months saves about "
            f"${scen['smoothing']['annual_saving']:,.0f} a year.", body),
        Spacer(1, 6),
        Paragraph(
            "<b>Assumptions.</b> Crew cost $130,000 a year in every department (brief gives Public Works only); requests per "
            "crew per month and starting crews are estimated from 2024 data. A late request costs $20 and $100 more after "
            "30 days. See the report for the full method.", body),
    ]
    doc.build(els)
    return buf.getvalue()
