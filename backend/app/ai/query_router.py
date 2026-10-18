"""
Query router: decides HOW a question should be answered.

  graph  : the question is about relationships/status (who, which projects, what is open)
           -> lead with structured facts from the knowledge graph, add a few documents
  hybrid : relational AND explanatory ("why did Priya pick vendor B?")
           -> graph facts plus a wider document search
  vector : everything else, or when the graph has nothing relevant
           -> plain semantic retrieval over the document chunks

Rule-based on purpose. A routing call to the local 7B model would add seconds of latency
to every question and be harder to test; entity linking against the graph does the work
that actually matters (knowing WHICH person/project is meant), and the regexes only choose
which kind of fact to fetch. The chosen route is returned to the UI, so it is transparent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.models import User
from app.graph.builder import ensure_graph
from app.graph.queries import (
    decision_facts, entity_facts, find_entities, overview_facts, pending_facts,
)

_RELATIONAL = re.compile(
    r"\b(who|whom|whose|which (?:projects?|people|person|team|teams|clients?)|worked? (?:on|with)|"
    r"working (?:on|with)|works? with|involved|responsible|owner|owns?|collaborat\w*|stakeholders?|"
    r"contacts?|point of contact|in charge|people|projects?|team)\b", re.I)
_REASONING = re.compile(
    r"\b(why|reasons?|rationale|because|how come|what happened|background|history|explain|"
    r"chose|chosen|choose|picked|selected)\b", re.I)
_PENDING = re.compile(
    r"\b(pending|open|unresolved|outstanding|follow[- ]?ups?|to-?dos?|left to do|overdue|stale|blocked|"
    r"action items?|tasks?)\b", re.I)
_DECISIONS = re.compile(r"\b(decisions?|decided|decide)\b", re.I)

MAX_ENTITY_FACTS = 2


@dataclass
class Plan:
    mode: str                                   # "graph" | "hybrid" | "vector"
    vector_k: int
    facts: list[dict] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)


def plan_retrieval(db: Session, user: User, question: str) -> Plan:
    if not ensure_graph(db, user):
        return Plan(mode="vector", vector_k=8)

    entities = find_entities(db, user.id, question)
    relational = bool(_RELATIONAL.search(question))
    reasoning = bool(_REASONING.search(question))
    pending = bool(_PENDING.search(question))
    decisions = bool(_DECISIONS.search(question))
    intents = [n for n, on in (("relational", relational), ("reasoning", reasoning),
                               ("pending", pending), ("decisions", decisions)) if on]

    facts: list[dict] = []
    for ent in entities[:MAX_ENTITY_FACTS]:
        facts += entity_facts(db, user.id, ent)
    if pending and not entities:
        facts += pending_facts(db, user.id)
    if decisions and not entities:
        facts += decision_facts(db, user.id)
    if relational and not entities and not facts:
        facts += overview_facts(db, user.id)

    ent_payload = [{"id": e.id, "name": e.name, "type": e.type} for e in entities]
    if not facts:
        return Plan(mode="vector", vector_k=8, entities=ent_payload, intents=intents)
    if reasoning:
        return Plan(mode="hybrid", vector_k=6, facts=facts, entities=ent_payload, intents=intents)
    return Plan(mode="graph", vector_k=3, facts=facts, entities=ent_payload, intents=intents)
