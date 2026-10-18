"""
Read-side helpers for the knowledge graph: the network view, node detail, entity
detection inside a question, and the compact "graph facts" handed to the chat model.
"""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chunk, GraphEdge, GraphNode, RawItem
from app.graph.builder import is_open
from app.graph.resolution import normalize_text
from app.utils.links import source_url

PEOPLE_PROJECT_RELATIONS = {"WORKS_ON", "COLLABORATES_WITH"}
ALL_RELATIONS = PEOPLE_PROJECT_RELATIONS | {"ABOUT", "INVOLVES", "OWNS"}
_OWNER_WORDS = re.compile(
    r"\b(he|his|him|himself|she|her|hers|herself|predecessor|previous (?:owner|incumbent|holder)|"
    r"former (?:owner|holder|incumbent))\b", re.I)


def _fmt(d: datetime | None) -> str | None:
    return d.strftime("%Y-%m-%d") if d else None


def _batches(seq, n=400):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


# ------------------------------------------------------------------------ sources

def source_info(db: Session, chunk_ids: list[str]) -> dict[str, dict]:
    """chunk id -> {subject, date, url, source, raw_item_id, preview} for citations."""
    out: dict[str, dict] = {}
    for batch in _batches(set(chunk_ids)):
        rows = db.execute(
            select(Chunk, RawItem).join(RawItem, Chunk.raw_item_id == RawItem.id).where(Chunk.id.in_(batch))
        ).all()
        for chunk, item in rows:
            out[chunk.id] = {
                "chunk_id": chunk.id, "raw_item_id": item.id, "source": item.source,
                "subject": item.subject_or_title or "(untitled)", "date": _fmt(item.item_date),
                "url": source_url(item.source, item.source_id), "preview": chunk.text[:240],
            }
    return out


# --------------------------------------------------------------------- edge helpers

def collect_edges(db: Session, user_id: str, node_id: str) -> list[dict]:
    """All edges touching a node, with the node at the other end resolved."""
    edges = db.execute(
        select(GraphEdge).where(GraphEdge.user_id == user_id,
                                (GraphEdge.src_id == node_id) | (GraphEdge.dst_id == node_id))
    ).scalars().all()
    other_ids = {e.dst_id if e.src_id == node_id else e.src_id for e in edges}
    others = {}
    for batch in _batches(other_ids):
        for n in db.execute(select(GraphNode).where(GraphNode.id.in_(batch))).scalars():
            others[n.id] = n
    out = []
    for e in edges:
        oid = e.dst_id if e.src_id == node_id else e.src_id
        if oid in others:
            out.append({"other": others[oid], "relation": e.relation,
                        "direction": "out" if e.src_id == node_id else "in",
                        "weight": e.weight, "evidence": e.evidence or [], "last_seen": e.last_seen})
    return out


def _rank(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda x: (-x["weight"], -(x["last_seen"].timestamp() if x["last_seen"] else 0)))


def _brief(e: dict) -> dict:
    n: GraphNode = e["other"]
    d = {"id": n.id, "type": n.type, "name": n.name, "relation": e["relation"], "weight": e["weight"],
         "last_seen": _fmt(e["last_seen"]), "is_owner": n.is_owner}
    if n.type == "decision":
        d.update(decision=n.attrs.get("decision"), reasoning=n.attrs.get("reasoning"), date=n.attrs.get("date"))
    if n.type == "action":
        d.update(description=n.attrs.get("description"), owner=n.attrs.get("owner"),
                 status=n.attrs.get("status"), open=is_open(n.attrs.get("status")))
    return d


# ---------------------------------------------------------------------- network view

def get_graph_view(db: Session, user_id: str, types: tuple[str, ...] = ("person", "project"),
                   min_weight: int = 1, hide_owner: bool = False, limit: int = 80,
                   focus_id: str | None = None) -> dict:
    nodes = db.execute(select(GraphNode).where(GraphNode.user_id == user_id, GraphNode.type.in_(types))).scalars().all()
    if hide_owner:
        nodes = [n for n in nodes if not n.is_owner]
    by_id = {n.id: n for n in nodes}
    relations = ALL_RELATIONS if any(t in ("decision", "action") for t in types) else PEOPLE_PROJECT_RELATIONS

    all_edges = db.execute(
        select(GraphEdge).where(GraphEdge.user_id == user_id, GraphEdge.relation.in_(relations))
    ).scalars().all()
    edges = [e for e in all_edges if e.src_id in by_id and e.dst_id in by_id and e.weight >= min_weight]

    degree: dict[str, int] = {}
    wdegree: dict[str, int] = {}
    for e in edges:
        for nid in (e.src_id, e.dst_id):
            degree[nid] = degree.get(nid, 0) + 1
            wdegree[nid] = wdegree.get(nid, 0) + e.weight

    connected = [n for n in nodes if degree.get(n.id)]
    connected.sort(key=lambda n: (-wdegree[n.id], -n.mention_count, n.name.lower()))
    keep_ids = {n.id for n in connected[:limit]}

    if focus_id and focus_id in by_id and focus_id not in keep_ids:       # always show a requested node
        keep_ids.add(focus_id)
        for e in edges:
            if e.src_id == focus_id:
                keep_ids.add(e.dst_id)
            elif e.dst_id == focus_id:
                keep_ids.add(e.src_id)

    out_nodes = [{
        "id": n.id, "type": n.type, "name": n.name, "mention_count": n.mention_count,
        "degree": degree.get(n.id, 0), "weighted_degree": wdegree.get(n.id, 0),
        "is_owner": n.is_owner, "last_seen": _fmt(n.last_seen),
    } for n in connected if n.id in keep_ids or n.id == focus_id]
    shown = {n["id"] for n in out_nodes}
    out_edges = [{"source": e.src_id, "target": e.dst_id, "relation": e.relation, "weight": e.weight}
                 for e in edges if e.src_id in shown and e.dst_id in shown]
    return {"nodes": out_nodes, "edges": out_edges,
            "stats": {"total_nodes": len(nodes), "total_edges": len(edges),
                      "shown_nodes": len(out_nodes), "shown_edges": len(out_edges),
                      "hidden_isolated": len(nodes) - len(connected)}}


# ------------------------------------------------------------------------ node detail

def get_node_detail(db: Session, user_id: str, node_id: str) -> dict | None:
    node = db.get(GraphNode, node_id)
    if node is None or node.user_id != user_id:
        return None
    edges = collect_edges(db, user_id, node_id)

    def pick(types, relations=None, cap=12):
        sel = [e for e in edges if e["other"].type in types and (relations is None or e["relation"] in relations)]
        return [_brief(e) for e in _rank(sel)[:cap]]

    evidence_ids: list[str] = []
    for e in _rank(edges):
        for cid in reversed(e["evidence"]):
            if cid not in evidence_ids:
                evidence_ids.append(cid)
        if len(evidence_ids) >= 12:
            break
    if node.type in ("decision", "action") and node.attrs.get("chunk_id") not in evidence_ids:
        evidence_ids.insert(0, node.attrs.get("chunk_id"))
    info = source_info(db, [c for c in evidence_ids if c][:8])
    evidence = [info[c] for c in evidence_ids if c in info][:6]

    return {
        "node": {"id": node.id, "type": node.type, "name": node.name, "aliases": node.aliases or [],
                 "mention_count": node.mention_count, "first_seen": _fmt(node.first_seen),
                 "last_seen": _fmt(node.last_seen), "is_owner": node.is_owner, "attrs": node.attrs or {}},
        "people": pick({"person"}),
        "projects": pick({"project"}),
        "decisions": pick({"decision"}, cap=10),
        "actions": pick({"action"}, cap=10),
        "evidence": evidence,
    }


# ----------------------------------------------------------- entity detection in text

def find_entities(db: Session, user_id: str, text: str, limit: int = 3) -> list[GraphNode]:
    """
    Finds person/project nodes named in a question (matching canonical names and aliases
    on word boundaries). Longer matches win, and a match contained inside a longer matched
    name is dropped ("atlas" inside "atlas migration"). If the question uses a pronoun
    ("what did he work on?") and names no person, it refers to the mailbox owner.
    """
    q = f" {normalize_text(text)} "
    nodes = db.execute(
        select(GraphNode).where(GraphNode.user_id == user_id, GraphNode.type.in_(("person", "project")))
    ).scalars().all()

    matches: list[tuple[str, GraphNode]] = []
    for n in nodes:
        for form in {normalize_text(n.name), *(normalize_text(a) for a in (n.aliases or []))}:
            if len(form) >= 3 and f" {form} " in q:
                matches.append((form, n))
                break
    matches.sort(key=lambda m: -len(m[0]))
    kept: list[tuple[str, GraphNode]] = []
    for form, n in matches:
        if any(form != k and form in k for k, _ in kept):
            continue
        kept.append((form, n))
    found = [n for _, n in kept][:limit]

    if not any(n.type == "person" for n in found) and _OWNER_WORDS.search(text or ""):
        owner = next((n for n in nodes if n.type == "person" and n.is_owner), None)
        if owner and owner.id not in {n.id for n in found}:
            found.insert(0, owner)
    return found[:limit]


# ----------------------------------------------------------------------- graph facts

def _names(items: list[dict], cap: int) -> str:
    return ", ".join(f"{i['name']} ({i['weight']})" for i in items[:cap])


def _recent_chunks(edges: list[dict], per_edge: int = 1, cap: int = 3) -> list[str]:
    ids: list[str] = []
    for e in _rank(edges):
        for cid in list(reversed(e["evidence"]))[:per_edge]:
            if cid not in ids:
                ids.append(cid)
        if len(ids) >= cap:
            break
    return ids[:cap]


def _action_line(n: GraphNode) -> str:
    a = n.attrs or {}
    owner = f", owner: {a['owner']}" if a.get("owner") else ", no owner named"
    seen = f", last mentioned {_fmt(n.last_seen)}" if n.last_seen else ""
    return f"{a.get('description')} [{a.get('status', 'open')}{owner}{seen}]"


def _brief_list(edges: list[dict]) -> list[dict]:
    return [_brief(e) for e in _rank(edges)]


def _decision_line(n: GraphNode) -> str:
    a = n.attrs or {}
    why = f" (reason: {a['reasoning']})" if a.get("reasoning") else " (no reason stated)"
    when = f" [{a['date']}]" if a.get("date") else (f" [{_fmt(n.first_seen)}]" if n.first_seen else "")
    return f"{a.get('decision')}{why}{when}"


def entity_facts(db: Session, user_id: str, node: GraphNode) -> list[dict]:
    """Compact, citable facts about one person/project: [{text, chunk_ids}]."""
    edges = collect_edges(db, user_id, node.id)
    facts: list[dict] = []
    who = node.name + (" (the mailbox owner, i.e. the predecessor)" if node.is_owner else "")

    if node.type == "person":
        proj = [e for e in edges if e["other"].type == "project"]
        peers = [e for e in edges if e["other"].type == "person"]
        acts = [e for e in edges if e["other"].type == "action" and is_open(e["other"].attrs.get("status"))]
        decs = [e for e in edges if e["other"].type == "decision"]
        if proj:
            facts.append({"text": f"{who} is connected to these projects (number of source chunks): "
                                  f"{_names(_brief_list(proj), 8)}.", "chunk_ids": _recent_chunks(proj)})
        else:
            facts.append({"text": f"No projects are linked to {who} in the record.", "chunk_ids": []})
        if peers:
            facts.append({"text": f"{node.name} appears together with: {_names(_brief_list(peers), 8)}.",
                          "chunk_ids": _recent_chunks(peers)})
        if acts:
            lines = "; ".join(_action_line(e["other"]) for e in _rank(acts)[:5])
            facts.append({"text": f"Open action items owned by {node.name}: {lines}.",
                          "chunk_ids": _recent_chunks(acts)})
        if decs:
            lines = "; ".join(_decision_line(e["other"]) for e in _rank(decs)[:4])
            facts.append({"text": f"Decisions {node.name} was involved in: {lines}.", "chunk_ids": _recent_chunks(decs)})

    elif node.type == "project":
        ppl = [e for e in edges if e["other"].type == "person" and not e["other"].is_owner]
        owner = [e for e in edges if e["other"].type == "person" and e["other"].is_owner]
        acts = [e for e in edges if e["other"].type == "action" and is_open(e["other"].attrs.get("status"))]
        decs = [e for e in edges if e["other"].type == "decision"]
        if ppl:
            facts.append({"text": f"People connected to project {node.name} (number of source chunks): "
                                  f"{_names(_brief_list(ppl), 8)}.", "chunk_ids": _recent_chunks(ppl)})
        else:
            facts.append({"text": f"No people other than the mailbox owner are linked to project {node.name}.",
                          "chunk_ids": _recent_chunks(owner)})
        if owner:
            facts.append({"text": f"The mailbox owner (predecessor) {owner[0]['other'].name} was involved in "
                                  f"{node.name} in {owner[0]['weight']} source chunk(s).",
                          "chunk_ids": _recent_chunks(owner)})
        if decs:
            lines = "; ".join(_decision_line(e["other"]) for e in _rank(decs)[:4])
            facts.append({"text": f"Decisions about {node.name}: {lines}.", "chunk_ids": _recent_chunks(decs)})
        if acts:
            lines = "; ".join(_action_line(e["other"]) for e in _rank(acts)[:5])
            facts.append({"text": f"Open action items for {node.name}: {lines}.", "chunk_ids": _recent_chunks(acts)})
        if node.last_seen:
            facts.append({"text": f"Project {node.name} was last mentioned on {_fmt(node.last_seen)}.", "chunk_ids": []})
    return facts


def pending_facts(db: Session, user_id: str, limit: int = 8) -> list[dict]:
    actions = db.execute(select(GraphNode).where(GraphNode.user_id == user_id, GraphNode.type == "action")).scalars().all()
    open_ = [a for a in actions if is_open(a.attrs.get("status"))]
    open_.sort(key=lambda n: n.last_seen or datetime.min, reverse=True)
    facts = []
    for n in open_[:limit]:
        facts.append({"text": f"Open action item: {_action_line(n)}.", "chunk_ids": [n.attrs.get("chunk_id")]})
    if not open_:
        facts.append({"text": "No open action items are recorded.", "chunk_ids": []})
    return facts


def decision_facts(db: Session, user_id: str, limit: int = 6) -> list[dict]:
    """Most recent decisions with their stated reasoning, for 'what was decided?' questions."""
    decisions = db.execute(select(GraphNode).where(GraphNode.user_id == user_id, GraphNode.type == "decision")).scalars().all()
    decisions.sort(key=lambda n: n.first_seen or datetime.min, reverse=True)
    facts = [{"text": f"Decision: {_decision_line(n)}.", "chunk_ids": [n.attrs.get("chunk_id")]} for n in decisions[:limit]]
    if not decisions:
        facts.append({"text": "No decisions have been extracted from the record.", "chunk_ids": []})
    return facts


def overview_facts(db: Session, user_id: str) -> list[dict]:
    """Used for broad relational questions with no named entity ('who should I talk to first?')."""
    from app.graph.insights import key_people          # local import: insights imports this module
    kp = key_people(db, user_id, limit=5)
    facts = []
    if kp["people"]:
        names = "; ".join(f"{p['name']} ({p['weighted_degree']} connections, projects: "
                          f"{', '.join(x['name'] for x in p['projects'][:3]) or 'none'})" for p in kp["people"])
        cids = [c for person in kp["people"] for c in person["chunk_ids"]][:4]
        facts.append({"text": f"The people most connected in the record, besides the mailbox owner: {names}.",
                      "chunk_ids": cids})
    projects = db.execute(
        select(GraphNode).where(GraphNode.user_id == user_id, GraphNode.type == "project")
        .order_by(GraphNode.mention_count.desc()).limit(6)).scalars().all()
    if projects:
        facts.append({"text": "The most discussed projects: " + ", ".join(
            f"{p.name} ({p.mention_count} chunks, last {_fmt(p.last_seen)})" for p in projects) + ".",
            "chunk_ids": []})
    return facts
