"""
Handover report: the whole record, condensed into a document a successor can read in
ten minutes and keep. Built only from the knowledge graph (no model calls), so it is
fast, reproducible, and every statement links back to a source email or document.

  build_report_data(db, user)  ->  plain dict (also what the tests assert against)
  render_markdown(data)        ->  str
  render_pdf(data)             ->  bytes
"""
from __future__ import annotations

import io
import os
from datetime import datetime
from xml.sax.saxutils import escape

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import GraphNode, RawItem, User
from app.graph.builder import ensure_graph, is_open
from app.graph.insights import attention_report, key_people
from app.graph.queries import _brief, _fmt, _rank, collect_edges, source_info

MAX_PROJECTS = 25
MAX_DECISIONS = 60
MAX_ACTIONS = 60


# ------------------------------------------------------------------------------ data

def _src(info: dict, chunk_id: str | None) -> dict | None:
    s = info.get(chunk_id) if chunk_id else None
    return {"subject": s["subject"], "date": s["date"], "url": s["url"], "source": s["source"]} if s else None


def build_report_data(db: Session, user: User, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    ensure_graph(db, user)

    def nodes(t):
        return list(db.execute(select(GraphNode).where(GraphNode.user_id == user.id, GraphNode.type == t)).scalars())

    people, projects = nodes("person"), nodes("project")
    decisions, actions = nodes("decision"), nodes("action")
    owner = next((p for p in people if p.is_owner), None)
    item_count = db.execute(select(func.count()).select_from(RawItem).where(RawItem.user_id == user.id)).scalar()
    first = db.execute(select(func.min(RawItem.item_date)).where(RawItem.user_id == user.id)).scalar()
    last = db.execute(select(func.max(RawItem.item_date)).where(RawItem.user_id == user.id)).scalar()

    decisions.sort(key=lambda n: n.first_seen.timestamp() if n.first_seen else 0, reverse=True)
    open_actions = [a for a in actions if is_open(a.attrs.get("status"))]
    open_actions.sort(key=lambda n: n.last_seen.timestamp() if n.last_seen else 0)       # oldest first
    projects.sort(key=lambda n: (-n.mention_count, n.name.lower()))

    all_chunk_ids = [n.attrs.get("chunk_id") for n in decisions[:MAX_DECISIONS] + open_actions[:MAX_ACTIONS]]
    info = source_info(db, [c for c in all_chunk_ids if c])

    project_cards = []
    for p in projects[:MAX_PROJECTS]:
        edges = collect_edges(db, user.id, p.id)
        ppl = [_brief(e) for e in _rank([e for e in edges if e["other"].type == "person" and not e["other"].is_owner])]
        decs = [e for e in edges if e["other"].type == "decision"]
        acts = [e for e in edges if e["other"].type == "action" and is_open(e["other"].attrs.get("status"))]
        pinfo = source_info(db, [e["other"].attrs.get("chunk_id") for e in decs + acts if e["other"].attrs.get("chunk_id")])
        project_cards.append({
            "name": p.name, "aliases": p.aliases or [], "mentions": p.mention_count,
            "first_seen": _fmt(p.first_seen), "last_seen": _fmt(p.last_seen),
            "context": ((p.attrs or {}).get("contexts") or [None])[0],
            "people": [{"name": x["name"], "weight": x["weight"]} for x in ppl[:6]],
            "decisions": [{"text": e["other"].attrs.get("decision"), "reasoning": e["other"].attrs.get("reasoning"),
                           "date": e["other"].attrs.get("date") or _fmt(e["other"].first_seen),
                           "source": _src(pinfo, e["other"].attrs.get("chunk_id"))} for e in _rank(decs)[:5]],
            "open_actions": [{"text": e["other"].attrs.get("description"), "owner": e["other"].attrs.get("owner"),
                              "last_seen": _fmt(e["other"].last_seen),
                              "source": _src(pinfo, e["other"].attrs.get("chunk_id"))} for e in _rank(acts)[:5]],
        })

    att = attention_report(db, user.id, now=now)
    kp = key_people(db, user.id, limit=8)
    return {
        "generated": now.strftime("%Y-%m-%d"),
        "owner": {"name": owner.name if owner else user.email, "email": user.email},
        "scope": {"items": item_count, "from": _fmt(first), "to": _fmt(last)},
        "counts": {"people": len([p for p in people if not p.is_owner]), "projects": len(projects),
                   "decisions": len(decisions), "open_actions": len(open_actions)},
        "key_people": [{"name": p["name"], "connections": p["weighted_degree"], "last_seen": p["last_seen"],
                        "emails": p["emails"], "roles": p["roles"],
                        "projects": [x["name"] for x in p["projects"]]} for p in kp["people"]],
        "attention": {
            "stale_days": att["thresholds"]["stale_days"], "dormant_days": att["thresholds"]["dormant_days"],
            "stale_actions": [{"text": a["description"], "owner": a["owner"], "age_days": a["age_days"],
                               "source": a.get("source") and {"subject": a["source"]["subject"], "date": a["source"]["date"],
                                                               "url": a["source"]["url"], "source": a["source"]["source"]}}
                              for a in att["stale_actions"][:15]],
            "unowned_actions": [{"text": a["description"], "age_days": a["age_days"]} for a in att["unowned_actions"][:15]],
            "concentrated_projects": att["concentrated_projects"][:12],
            "dormant_projects": att["dormant_projects"][:12],
        },
        "projects": project_cards,
        "decisions": [{"text": n.attrs.get("decision"), "reasoning": n.attrs.get("reasoning"),
                       "date": n.attrs.get("date") or _fmt(n.first_seen),
                       "source": _src(info, n.attrs.get("chunk_id"))} for n in decisions[:MAX_DECISIONS]],
        "open_actions": [{"text": n.attrs.get("description"), "owner": n.attrs.get("owner"),
                          "last_seen": _fmt(n.last_seen), "source": _src(info, n.attrs.get("chunk_id"))}
                         for n in open_actions[:MAX_ACTIONS]],
    }


# -------------------------------------------------------------------------- markdown

def _md_src(s: dict | None) -> str:
    if not s:
        return ""
    label = f"{s['subject']}, {s['date']}" if s.get("date") else s["subject"]
    return f" — [{label}]({s['url']})" if s.get("url") else f" — {label}"


def render_markdown(d: dict) -> str:
    o, c, s = d["owner"], d["counts"], d["scope"]
    L = [f"# ECHO handover report", "",
         f"**Mailbox of:** {o['name']} ({o['email']})  ",
         f"**Generated:** {d['generated']}  ",
         f"**Based on:** {s['items']} emails and documents"
         + (f", {s['from']} to {s['to']}" if s["from"] else ""), "",
         "This report is generated from the extracted record. Connections between people and projects "
         "mean they appeared together in the same message; they do not prove ownership. "
         "Check the linked source before acting on anything important.", "",
         "## At a glance", "",
         f"- {c['projects']} projects, {c['people']} other people, {c['decisions']} decisions, "
         f"{c['open_actions']} open action items", ""]

    L += ["## Who to talk to first", ""]
    if d["key_people"]:
        for p in d["key_people"]:
            bits = [f"works with {', '.join(p['projects'][:3])}" if p["projects"] else None,
                    p["emails"][0] if p["emails"] else None, f"last seen {p['last_seen']}" if p["last_seen"] else None]
            L.append(f"- **{p['name']}** ({p['connections']} connections)" + (f" — {'; '.join(b for b in bits if b)}" if any(bits) else ""))
    else:
        L.append("No other people were identified.")

    a = d["attention"]
    L += ["", "## Needs attention", ""]
    if a["unowned_actions"]:
        L.append(f"**Open items with no named owner ({len(a['unowned_actions'])})**")
        L += [f"- {x['text']}" + (f" (open {x['age_days']} days)" if x["age_days"] is not None else "") for x in a["unowned_actions"]]
        L.append("")
    if a["stale_actions"]:
        L.append(f"**Open for {a['stale_days']}+ days ({len(a['stale_actions'])})**")
        L += [f"- {x['text']}" + (f" — owner: {x['owner']}" if x["owner"] else "") + f" (last mentioned {x['age_days']} days ago)"
              + _md_src(x["source"]) for x in a["stale_actions"]]
        L.append("")
    if a["concentrated_projects"]:
        L.append("**Knowledge concentrated in very few people**")
        for p in a["concentrated_projects"]:
            who = "only the predecessor appears with it" if p["reason"] == "only_predecessor" else f"only {p['person']} appears with it besides the predecessor"
            L.append(f"- {p['name']} — {who}")
        L.append("")
    if a["dormant_projects"]:
        L.append(f"**Quiet for {a['dormant_days']}+ days but with open actions**")
        L += [f"- {p['name']} — last mentioned {p['last_seen']}, {p['open_actions']} open action(s)" for p in a["dormant_projects"]]
        L.append("")
    if not any((a["unowned_actions"], a["stale_actions"], a["concentrated_projects"], a["dormant_projects"])):
        L.append("Nothing was flagged.")
        L.append("")

    L += ["## Projects", ""]
    for p in d["projects"]:
        L.append(f"### {p['name']}")
        L.append(f"Mentioned in {p['mentions']} places, {p['first_seen'] or '?'} to {p['last_seen'] or '?'}."
                 + (f" {p['context']}" if p["context"] else ""))
        if p["people"]:
            L.append(f"- **People:** " + ", ".join(x["name"] for x in p["people"]))
        for x in p["decisions"]:
            L.append(f"- **Decision:** {x['text']}" + (f" (reason: {x['reasoning']})" if x["reasoning"] else "") + _md_src(x["source"]))
        for x in p["open_actions"]:
            L.append(f"- **Open:** {x['text']}" + (f" — {x['owner']}" if x["owner"] else " — no owner named") + _md_src(x["source"]))
        L.append("")

    L += ["## Decision log", ""]
    L += [f"- {x['date'] or 'undated'} — {x['text']}" + (f" *Reason: {x['reasoning']}*" if x["reasoning"] else "") + _md_src(x["source"])
          for x in d["decisions"]] or ["No decisions were extracted."]
    L += ["", "## Open action items", ""]
    L += [f"- {x['text']} — " + (x["owner"] or "no owner named") + (f", last mentioned {x['last_seen']}" if x["last_seen"] else "")
          + _md_src(x["source"]) for x in d["open_actions"]] or ["No open action items."]
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------------------- pdf

_FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
]


def _register_fonts() -> tuple[str, str]:
    """Prefers a Unicode TrueType font (names with accents or non-Latin scripts), else Helvetica."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for regular, bold in _FONT_CANDIDATES:
        if os.path.exists(regular) and os.path.exists(bold):
            try:
                pdfmetrics.registerFont(TTFont("EchoSans", regular))
                pdfmetrics.registerFont(TTFont("EchoSans-Bold", bold))
                return "EchoSans", "EchoSans-Bold"
            except Exception:
                continue
    return "Helvetica", "Helvetica-Bold"


def render_pdf(d: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)

    regular, bold = _register_fonts()
    INK, STONE, OXBLOOD, LINE = colors.HexColor("#1B2430"), colors.HexColor("#6B6560"), colors.HexColor("#8A2E22"), colors.HexColor("#D8D4C9")
    st = {
        "title": ParagraphStyle("t", fontName=bold, fontSize=24, leading=28, textColor=INK, spaceAfter=4),
        "meta": ParagraphStyle("m", fontName=regular, fontSize=9.5, leading=14, textColor=STONE),
        "h1": ParagraphStyle("h1", fontName=bold, fontSize=14, leading=18, textColor=INK, spaceBefore=16, spaceAfter=6, keepWithNext=1),
        "h2": ParagraphStyle("h2", fontName=bold, fontSize=11, leading=14, textColor=OXBLOOD, spaceBefore=10, spaceAfter=3, keepWithNext=1),
        "body": ParagraphStyle("b", fontName=regular, fontSize=9.5, leading=13.5, textColor=INK, alignment=TA_LEFT),
        "small": ParagraphStyle("s", fontName=regular, fontSize=8.5, leading=12, textColor=STONE),
        "note": ParagraphStyle("n", fontName=regular, fontSize=8.5, leading=12, textColor=STONE, spaceBefore=6, spaceAfter=4),
    }

    def P(text, style="body"):
        return Paragraph(text, st[style])

    def link(s):
        if not s:
            return ""
        label = escape(f"{s['subject']}, {s['date']}" if s.get("date") else s["subject"])
        return (f' <font color="#6B6560">— </font><link href="{escape(s["url"], {chr(34): "&quot;"})}" color="#8A2E22">{label}</link>'
                if s.get("url") else f' <font color="#6B6560">— {label}</font>')

    def bullets(rows):
        if not rows:
            return []
        return [ListFlowable([ListItem(P(r), leftIndent=10) for r in rows], bulletType="bullet", start="•",
                             leftIndent=12, bulletFontName=regular, bulletFontSize=8)]

    o, c, s, a = d["owner"], d["counts"], d["scope"], d["attention"]
    flow = [P("ECHO handover report", "title"),
            P(escape(f"Mailbox of {o['name']} ({o['email']})"), "meta"),
            P(escape(f"Generated {d['generated']}  ·  based on {s['items']} emails and documents"
                     + (f", {s['from']} to {s['to']}" if s["from"] else "")), "meta"), Spacer(1, 6)]

    stats = Table([[str(c["projects"]), str(c["people"]), str(c["decisions"]), str(c["open_actions"])],
                   ["projects", "other people", "decisions", "open actions"]], colWidths=[41 * mm] * 4)
    stats.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), bold, 20), ("TEXTCOLOR", (0, 0), (-1, 0), INK),
        ("FONT", (0, 1), (-1, 1), regular, 8.5), ("TEXTCOLOR", (0, 1), (-1, 1), STONE),
        ("LINEBEFORE", (0, 0), (-1, -1), 1.5, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 2), ("BOTTOMPADDING", (0, 1), (-1, 1), 2),
    ]))
    flow += [stats, P("Connections between people and projects mean they appeared together in the same message; "
                      "they do not prove ownership. Check the linked source before acting on anything important.", "note")]

    flow.append(P("Who to talk to first", "h1"))
    if d["key_people"]:
        rows = []
        for p in d["key_people"]:
            extra = "; ".join(x for x in [("works with " + ", ".join(p["projects"][:3])) if p["projects"] else "",
                                          p["emails"][0] if p["emails"] else ""] if x)
            rows.append(f"<b>{escape(p['name'])}</b> ({p['connections']} connections)" + (f" — {escape(extra)}" if extra else ""))
        flow += bullets(rows)
    else:
        flow.append(P("No other people were identified.", "small"))

    flow.append(P("Needs attention", "h1"))
    shown = False
    if a["unowned_actions"]:
        shown = True
        flow += [P(f"Open items with no named owner ({len(a['unowned_actions'])})", "h2")]
        flow += bullets([escape(x["text"]) + (f" <font color='#6B6560'>(open {x['age_days']} days)</font>" if x["age_days"] is not None else "")
                         for x in a["unowned_actions"]])
    if a["stale_actions"]:
        shown = True
        flow += [P(f"Open for {a['stale_days']}+ days ({len(a['stale_actions'])})", "h2")]
        flow += bullets([escape(x["text"]) + (f" <font color='#6B6560'>owner: {escape(x['owner'])}</font>" if x["owner"] else "")
                         + f" <font color='#6B6560'>({x['age_days']} days ago)</font>" + link(x["source"]) for x in a["stale_actions"]])
    if a["concentrated_projects"]:
        shown = True
        flow += [P("Knowledge concentrated in very few people", "h2")]
        flow += bullets([f"<b>{escape(p['name'])}</b> — " + ("only the predecessor appears with it" if p["reason"] == "only_predecessor"
                                                              else f"only {escape(p['person'])} appears with it besides the predecessor")
                         for p in a["concentrated_projects"]])
    if a["dormant_projects"]:
        shown = True
        flow += [P(f"Quiet for {a['dormant_days']}+ days but with open actions", "h2")]
        flow += bullets([f"<b>{escape(p['name'])}</b> — last mentioned {p['last_seen']}, {p['open_actions']} open action(s)"
                         for p in a["dormant_projects"]])
    if not shown:
        flow.append(P("Nothing was flagged.", "small"))

    flow.append(P("Projects", "h1"))
    for p in d["projects"]:
        block = [P(escape(p["name"]), "h2"),
                 P(escape(f"Mentioned in {p['mentions']} places, {p['first_seen'] or '?'} to {p['last_seen'] or '?'}."
                          + (f" {p['context']}" if p["context"] else "")), "small")]
        rows = []
        if p["people"]:
            rows.append("<b>People:</b> " + escape(", ".join(x["name"] for x in p["people"])))
        rows += ["<b>Decision:</b> " + escape(x["text"]) + (f" <font color='#6B6560'>(reason: {escape(x['reasoning'])})</font>" if x["reasoning"] else "")
                 + link(x["source"]) for x in p["decisions"]]
        rows += ["<b>Open:</b> " + escape(x["text"]) + (f" <font color='#6B6560'>— {escape(x['owner'])}</font>" if x["owner"]
                                                          else " <font color='#8A2E22'>— no owner named</font>") + link(x["source"])
                 for x in p["open_actions"]]
        flow.append(KeepTogether(block + bullets(rows)))

    flow.append(P("Decision log", "h1"))
    flow += bullets([f"<font color='#6B6560'>{escape(x['date'] or 'undated')}</font> — {escape(x['text'])}"
                     + (f" <i>Reason: {escape(x['reasoning'])}</i>" if x["reasoning"] else "") + link(x["source"])
                     for x in d["decisions"]]) or [P("No decisions were extracted.", "small")]
    flow.append(P("Open action items", "h1"))
    flow += bullets([escape(x["text"]) + (f" <font color='#6B6560'>— {escape(x['owner'])}</font>" if x["owner"]
                                           else " <font color='#8A2E22'>— no owner named</font>")
                     + (f" <font color='#6B6560'>last mentioned {x['last_seen']}</font>" if x["last_seen"] else "") + link(x["source"])
                     for x in d["open_actions"]]) or [P("No open action items.", "small")]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(regular, 8)
        canvas.setFillColor(STONE)
        canvas.drawString(20 * mm, 12 * mm, "ECHO — Employee Context & Handoff Orchestrator")
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=20 * mm,
                      title=f"ECHO handover report — {o['name']}", author="ECHO").build(flow, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
