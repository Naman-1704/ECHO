"""
Insights derived from the graph: who to talk to first, what needs attention, and a dated
timeline. All deterministic (no model calls) so results are explainable and testable.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GraphEdge, GraphNode
from app.graph.builder import is_open
from app.graph.queries import _fmt, source_info


def _all_nodes(db: Session, user_id: str, type_: str) -> list[GraphNode]:
    return list(db.execute(select(GraphNode).where(GraphNode.user_id == user_id, GraphNode.type == type_)).scalars())


def _edges(db: Session, user_id: str, relations: set[str]) -> list[GraphEdge]:
    return list(db.execute(select(GraphEdge).where(GraphEdge.user_id == user_id, GraphEdge.relation.in_(relations))).scalars())


def _project_names_by_node(db: Session, user_id: str) -> dict[str, list[str]]:
    """decision/action id -> project names, via ABOUT edges."""
    projects = {n.id: n.name for n in _all_nodes(db, user_id, "project")}
    out: dict[str, list[str]] = {}
    for e in _edges(db, user_id, {"ABOUT"}):
        if e.dst_id in projects:
            out.setdefault(e.src_id, []).append(projects[e.dst_id])
    return out


# --------------------------------------------------------------------- key people

def key_people(db: Session, user_id: str, limit: int = 6) -> dict:
    """
    Ranks people (excluding the mailbox owner) by weighted degree: the sum of the weights
    of their WORKS_ON and COLLABORATES_WITH edges. A person who co-occurs with many
    projects and colleagues across many threads is the one a successor should meet first.
    """
    people = {n.id: n for n in _all_nodes(db, user_id, "person")}
    projects = {n.id: n for n in _all_nodes(db, user_id, "project")}
    wdeg: dict[str, int] = {}
    proj_links: dict[str, list[tuple[int, str]]] = {}
    evidence: dict[str, list[str]] = {}
    for e in _edges(db, user_id, {"WORKS_ON", "COLLABORATES_WITH"}):
        for nid in (e.src_id, e.dst_id):
            if nid in people:
                wdeg[nid] = wdeg.get(nid, 0) + e.weight
                evidence.setdefault(nid, []).extend(list(reversed(e.evidence or []))[:1])
        if e.relation == "WORKS_ON" and e.src_id in people and e.dst_id in projects:
            proj_links.setdefault(e.src_id, []).append((e.weight, e.dst_id))

    def card(n: GraphNode) -> dict:
        links = sorted(proj_links.get(n.id, []), reverse=True)
        return {"id": n.id, "name": n.name, "weighted_degree": wdeg.get(n.id, 0), "mention_count": n.mention_count,
                "last_seen": _fmt(n.last_seen), "emails": (n.attrs or {}).get("emails", []),
                "roles": (n.attrs or {}).get("roles", []),
                "projects": [{"id": pid, "name": projects[pid].name, "weight": w} for w, pid in links[:4]],
                "chunk_ids": evidence.get(n.id, [])[:2]}

    ranked = sorted((n for n in people.values() if not n.is_owner and wdeg.get(n.id)),
                    key=lambda n: (-wdeg[n.id], -n.mention_count, n.name.lower()))
    owner = next((n for n in people.values() if n.is_owner), None)
    return {"owner": card(owner) if owner else None, "people": [card(n) for n in ranked[:limit]]}


# ------------------------------------------------------------------------ attention

def attention_report(db: Session, user_id: str, stale_days: int = 14, dormant_days: int = 60,
                     now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    by_node_projects = _project_names_by_node(db, user_id)
    actions = [a for a in _all_nodes(db, user_id, "action") if is_open(a.attrs.get("status"))]

    def action_card(a: GraphNode) -> dict:
        at = a.attrs or {}
        return {"id": a.id, "description": at.get("description"), "owner": at.get("owner"),
                "status": at.get("status"), "last_seen": _fmt(a.last_seen),
                "age_days": (now - a.last_seen).days if a.last_seen else None,
                "projects": by_node_projects.get(a.id, []),
                "chunk_id": at.get("chunk_id"), "raw_item_id": at.get("raw_item_id")}

    cards = [action_card(a) for a in actions]
    stale = sorted((c for c in cards if c["age_days"] is not None and c["age_days"] >= stale_days),
                   key=lambda c: -c["age_days"])
    unowned = sorted((c for c in cards if not c["owner"]), key=lambda c: -(c["age_days"] or 0))

    # Knowledge concentration: projects whose only trace is the predecessor, or one other person.
    people = {n.id: n for n in _all_nodes(db, user_id, "person")}
    projects = _all_nodes(db, user_id, "project")
    linked: dict[str, set[str]] = {}
    for e in _edges(db, user_id, {"WORKS_ON"}):
        if e.src_id in people:
            linked.setdefault(e.dst_id, set()).add(e.src_id)
    concentrated = []
    for p in projects:
        if p.mention_count < 2:
            continue
        others = [people[i] for i in linked.get(p.id, set()) if not people[i].is_owner]
        if len(others) == 0:
            concentrated.append({"id": p.id, "name": p.name, "reason": "only_predecessor", "person": None,
                                 "mentions": p.mention_count, "last_seen": _fmt(p.last_seen)})
        elif len(others) == 1:
            concentrated.append({"id": p.id, "name": p.name, "reason": "one_person", "person": others[0].name,
                                 "mentions": p.mention_count, "last_seen": _fmt(p.last_seen)})
    concentrated.sort(key=lambda c: (c["reason"] != "only_predecessor", -c["mentions"]))

    open_by_project: dict[str, int] = {}
    for a in actions:
        for name in by_node_projects.get(a.id, []):
            open_by_project[name] = open_by_project.get(name, 0) + 1
    dormant = [{"id": p.id, "name": p.name, "last_seen": _fmt(p.last_seen),
                "days_quiet": (now - p.last_seen).days, "open_actions": open_by_project[p.name]}
               for p in projects if p.last_seen and (now - p.last_seen).days >= dormant_days
               and open_by_project.get(p.name)]
    dormant.sort(key=lambda d: -d["days_quiet"])

    info = source_info(db, [c["chunk_id"] for c in stale[:25] + unowned[:25] if c["chunk_id"]])
    for c in stale[:25] + unowned[:25]:
        c["source"] = info.get(c["chunk_id"])

    return {"thresholds": {"stale_days": stale_days, "dormant_days": dormant_days},
            "counts": {"open_actions": len(cards), "stale_actions": len(stale), "unowned_actions": len(unowned),
                       "concentrated_projects": len(concentrated), "dormant_projects": len(dormant)},
            "stale_actions": stale[:25], "unowned_actions": unowned[:25],
            "concentrated_projects": concentrated[:15], "dormant_projects": dormant[:15]}


# -------------------------------------------------------------------------- timeline

def timeline(db: Session, user_id: str, limit: int = 300) -> dict:
    by_node_projects = _project_names_by_node(db, user_id)
    nodes = [n for t in ("decision", "action") for n in _all_nodes(db, user_id, t) if n.first_seen]
    nodes.sort(key=lambda n: n.first_seen, reverse=True)
    nodes = nodes[:limit]
    info = source_info(db, [n.attrs.get("chunk_id") for n in nodes if n.attrs.get("chunk_id")])
    events = []
    for n in nodes:
        at = n.attrs or {}
        events.append({
            "id": n.id, "type": n.type, "date": _fmt(n.first_seen), "last_seen": _fmt(n.last_seen),
            "text": at.get("decision") if n.type == "decision" else at.get("description"),
            "reasoning": at.get("reasoning"), "owner": at.get("owner"),
            "status": at.get("status"), "open": is_open(at.get("status")) if n.type == "action" else None,
            "projects": by_node_projects.get(n.id, []), "source": info.get(at.get("chunk_id")),
        })
    return {"events": events}
