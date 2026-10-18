"""
Builds the knowledge graph from what ingestion already stored.

Inputs : `chunks.extracted` (people / projects / decisions / action_items per chunk) and
         `raw_items.participants` (From / To headers).
Output : `graph_nodes` + `graph_edges` rows for one user.

This is a *derived* structure. `rebuild_graph` wipes the user's graph and reconstructs it
deterministically — no model calls, so it is fast (seconds even for thousands of chunks)
and safe to re-run any time (after every sync, or after changing resolution rules).

Edge semantics (weight = number of DISTINCT CHUNKS in which the relationship was seen):
  WORKS_ON            person -> project   co-occur in a chunk (extracted names + email headers)
  COLLABORATES_WITH   person <-> person   co-occur in a chunk (stored once, src < dst)
  ABOUT               decision/action -> project
  INVOLVES            decision -> person  (people named in the chunk + the email's sender)
  OWNS                person -> action

These are co-occurrence-based, not asserted facts; that is why every edge keeps its
evidence chunk ids — the UI and the chat answer can always show the source text.
"""
from __future__ import annotations

from datetime import datetime
from itertools import combinations

from sqlalchemy import delete, select, func
from sqlalchemy.orm import Session

from app.db.models import Chunk, GraphEdge, GraphNode, RawItem, User, gen_uuid
from app.graph.resolution import (
    EntityResolver, Mention, TextIndex, name_from_email, normalize_text, parse_header_people,
    text_key,
)

MAX_EVIDENCE = 25          # evidence chunk ids kept per edge (most recent)
MAX_PEOPLE_PER_CHUNK = 12  # guards against mass-mail cc lists exploding pair edges
MAX_INVOLVED_PER_DECISION = 6
RESOLVED_STATUSES = {"resolved", "done", "closed", "completed", "complete", "cancelled", "canceled"}


def is_open(status: str | None) -> bool:
    return (status or "").strip().lower() not in RESOLVED_STATUSES


# ---------------------------------------------------------------------------- helpers

def _items(extracted: dict, field: str, name_key: str) -> list[dict]:
    """Defensive read of model-produced JSON: accepts list[dict] or list[str], ignores junk."""
    value = (extracted or {}).get(field)
    if not isinstance(value, list):
        return []
    out = []
    for v in value:
        if isinstance(v, dict):
            out.append(v)
        elif isinstance(v, str) and v.strip():
            out.append({name_key: v.strip()})
    return out


def _s(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _min(a: datetime | None, b: datetime | None):
    return b if a is None else a if b is None else min(a, b)


def _max(a: datetime | None, b: datetime | None):
    return b if a is None else a if b is None else max(a, b)


def _person_mention(raw: str, date, role=None) -> Mention | None:
    raw = _s(raw)
    if not raw:
        return None
    if "@" in raw:   # the model sometimes emits an address instead of a name
        email = raw.lower().strip("<>")
        derived = name_from_email(email)
        return Mention(raw=derived, email=email, date=date, role=role) if derived else None
    return Mention(raw=raw, date=date, role=role)


def _unique(seq):
    seen, out = set(), []
    for x in seq:
        if x is not None and x.id not in seen:
            seen.add(x.id)
            out.append(x)
    return out


# ------------------------------------------------------------------------------ build

def rebuild_graph(db: Session, user: User) -> dict:
    db.execute(delete(GraphEdge).where(GraphEdge.user_id == user.id))
    db.execute(delete(GraphNode).where(GraphNode.user_id == user.id))

    rows = db.execute(
        select(Chunk, RawItem).join(RawItem, Chunk.raw_item_id == RawItem.id).where(Chunk.user_id == user.id)
    ).all()
    rows.sort(key=lambda r: (r[1].item_date or datetime.min, r[0].created_at or datetime.min, r[0].id))

    # ---- pass 1: gather every mention, then resolve them in one batch --------------
    person_mentions: list[Mention] = []
    project_mentions: list[Mention] = []
    headers: dict[str, list[dict]] = {}

    for chunk, item in rows:
        ex = chunk.extracted or {}
        for p in _items(ex, "people", "name"):
            m = _person_mention(p.get("name"), item.item_date, _s(p.get("role_or_context")) or None)
            if m:
                person_mentions.append(m)
        for a in _items(ex, "action_items", "description"):
            m = _person_mention(a.get("owner"), item.item_date)
            if m:
                person_mentions.append(m)
        for pr in _items(ex, "projects", "name"):
            name = _s(pr.get("name"))
            if name:
                project_mentions.append(Mention(raw=name, date=item.item_date, role=_s(pr.get("context")) or None))

        if item.id not in headers:
            headers[item.id] = parse_header_people(item.participants)
            for h in headers[item.id]:
                if h["name"]:
                    person_mentions.append(Mention(raw=h["name"], email=h["email"], date=item.item_date))

    people = EntityResolver("person").build(person_mentions)
    projects = EntityResolver("project").build(project_mentions)
    owner_email = (user.email or "").lower()

    # ---- pass 2: nodes' activity + edges --------------------------------------------
    seen: dict[str, dict] = {}                 # node id -> {"chunks": set, "first", "last"}
    edges: dict[tuple, dict] = {}              # (src, dst, rel) -> {"chunks": ordered dict, "first", "last"}
    extra: dict[str, dict] = {}                # decision / action nodes
    decision_idx, action_idx = TextIndex(), TextIndex()

    def touch(node_id: str, chunk_id: str, date):
        st = seen.setdefault(node_id, {"chunks": set(), "first": None, "last": None})
        st["chunks"].add(chunk_id)
        st["first"], st["last"] = _min(st["first"], date), _max(st["last"], date)

    def link(src: str, dst: str, rel: str, chunk_id: str, date):
        if src == dst:
            return
        if rel == "COLLABORATES_WITH" and src > dst:
            src, dst = dst, src
        e = edges.setdefault((src, dst, rel), {"chunks": {}, "first": None, "last": None})
        e["chunks"][chunk_id] = None
        e["first"], e["last"] = _min(e["first"], date), _max(e["last"], date)

    for chunk, item in rows:
        ex, date, cid = chunk.extracted or {}, item.item_date, chunk.id

        extracted_people = _unique(
            people.lookup(_s(p.get("name"))) if "@" not in _s(p.get("name")) else
            people.lookup(None, _s(p.get("name")).lower().strip("<>"))
            for p in _items(ex, "people", "name")
        )
        owner_people = _unique(people.lookup(_s(a.get("owner"))) for a in _items(ex, "action_items", "description")
                               if _s(a.get("owner")) and "@" not in _s(a.get("owner")))
        header_people, sender = [], None
        for h in headers.get(item.id, []):
            ent = people.lookup(h["name"], h["email"])
            if ent:
                header_people.append(ent)
                if h["role"] == "from" and sender is None:
                    sender = ent
        chunk_people = _unique(extracted_people + owner_people + ([sender] if sender else []) + header_people)
        chunk_people = chunk_people[:MAX_PEOPLE_PER_CHUNK]
        chunk_projects = _unique(projects.lookup(_s(p.get("name"))) for p in _items(ex, "projects", "name"))

        for ent in chunk_people + chunk_projects:
            touch(ent.id, cid, date)

        for p in chunk_people:
            for j in chunk_projects:
                link(p.id, j.id, "WORKS_ON", cid, date)
        for a, b in combinations(chunk_people, 2):
            link(a.id, b.id, "COLLABORATES_WITH", cid, date)

        involved = _unique(extracted_people + ([sender] if sender else []))[:MAX_INVOLVED_PER_DECISION]

        for d in _items(ex, "decisions", "decision"):
            text = _s(d.get("decision"))
            if len(text) < 8:
                continue
            node = decision_idx.find(text)
            if node is None:
                node = {"id": gen_uuid(), "type": "decision", "name": text[:140], "key": text_key(text),
                        "attrs": {"decision": text, "reasoning": _s(d.get("reasoning")) or None,
                                  "date": _s(d.get("date")) or None, "chunk_id": cid, "raw_item_id": item.id}}
                extra[node["id"]] = node
                decision_idx.add(text, node)
            elif not node["attrs"].get("reasoning") and _s(d.get("reasoning")):
                node["attrs"]["reasoning"] = _s(d.get("reasoning"))
            touch(node["id"], cid, date)
            for j in chunk_projects:
                link(node["id"], j.id, "ABOUT", cid, date)
            for p in involved:
                link(node["id"], p.id, "INVOLVES", cid, date)

        for a in _items(ex, "action_items", "description"):
            text = _s(a.get("description"))
            if len(text) < 6:
                continue
            owner_raw = _s(a.get("owner"))
            owner = people.lookup(owner_raw) if owner_raw and "@" not in owner_raw else None
            status = _s(a.get("status")).lower() or "open"
            node = action_idx.find(text)
            if node is None:
                node = {"id": gen_uuid(), "type": "action", "name": text[:140], "key": text_key(text),
                        "attrs": {"description": text, "owner": owner.name if owner else None,
                                  "owner_id": owner.id if owner else None, "status": status,
                                  "chunk_id": cid, "raw_item_id": item.id}}
                extra[node["id"]] = node
                action_idx.add(text, node)
            else:                                   # later mention (rows are date-ordered) wins
                node["attrs"]["status"] = status
                if owner:
                    node["attrs"]["owner"], node["attrs"]["owner_id"] = owner.name, owner.id
            touch(node["id"], cid, date)
            for j in chunk_projects:
                link(node["id"], j.id, "ABOUT", cid, date)
            if owner:
                link(owner.id, node["id"], "OWNS", cid, date)

    # ---- persist ------------------------------------------------------------------------
    counts = {"person": 0, "project": 0, "decision": 0, "action": 0}
    for resolver in (people, projects):
        for ent in resolver.entities:
            st = seen.get(ent.id)
            if not st:
                continue
            attrs = ({"roles": ent.roles, "emails": sorted(ent.emails), "name_only": ent.name_only}
                     if ent.kind == "person" else {"contexts": ent.roles})
            db.add(GraphNode(
                id=ent.id, user_id=user.id, type=ent.kind, name=ent.name, key=ent.key,
                aliases=sorted(a for a in ent.aliases if a != ent.name),
                mention_count=len(st["chunks"]), first_seen=st["first"], last_seen=st["last"],
                is_owner=bool(owner_email and owner_email in ent.emails), attrs=attrs,
            ))
            counts[ent.kind] += 1

    for node in extra.values():
        st = seen[node["id"]]
        db.add(GraphNode(
            id=node["id"], user_id=user.id, type=node["type"], name=node["name"], key=node["key"],
            aliases=[], mention_count=len(st["chunks"]), first_seen=st["first"], last_seen=st["last"],
            is_owner=False, attrs=node["attrs"],
        ))
        counts[node["type"]] += 1

    for (src, dst, rel), e in edges.items():
        db.add(GraphEdge(
            user_id=user.id, src_id=src, dst_id=dst, relation=rel, weight=len(e["chunks"]),
            evidence=list(e["chunks"])[-MAX_EVIDENCE:], first_seen=e["first"], last_seen=e["last"],
        ))

    db.commit()
    return {"nodes": sum(counts.values()), "edges": len(edges),
            "people": counts["person"], "projects": counts["project"],
            "decisions": counts["decision"], "actions": counts["action"]}


def graph_exists(db: Session, user_id: str) -> bool:
    return db.execute(select(func.count()).select_from(GraphNode).where(GraphNode.user_id == user_id)).scalar() > 0


def ensure_graph(db: Session, user: User) -> bool:
    """
    Builds the graph on first use for accounts ingested before the graph layer existed
    (or whose graph was never built). Returns True if a graph exists afterwards.
    """
    if graph_exists(db, user.id):
        return True
    has_chunks = db.execute(select(func.count()).select_from(Chunk).where(Chunk.user_id == user.id)).scalar()
    if not has_chunks:
        return False
    rebuild_graph(db, user)
    return graph_exists(db, user.id)
