import re

import pytest
from sqlalchemy import select

from app.ai import chat as chat_module
from app.ai.query_router import plan_retrieval
from app.ai.rag_pipeline import load_chunks
from app.db.models import Chunk, User
from conftest import seed_mailbox


@pytest.mark.parametrize("question,mode,entity", [
    ("Who worked on Atlas?", "graph", "Atlas migration"),
    ("What projects did he work on?", "graph", "Predecessor"),
    ("Why did we choose Vendor B for Atlas?", "hybrid", "Atlas migration"),
    ("What is still pending?", "graph", None),
    ("What decisions were made?", "graph", None),
    ("Who should I talk to first?", "graph", None),
    ("What is the capital of France?", "vector", None),
    ("Explain the background of everything", "vector", None),
])
def test_routing_decisions(db, seeded, question, mode, entity):
    user, _ = seeded
    plan = plan_retrieval(db, user, question)
    assert plan.mode == mode, (question, plan.mode, plan.intents)
    assert plan.vector_k == {"graph": 3, "hybrid": 6, "vector": 8}[plan.mode]
    if entity:
        assert entity in [e["name"] for e in plan.entities]
    if plan.mode == "vector":
        assert plan.facts == []


def test_account_without_data_falls_back_to_vector(db):
    user = User(id="empty", email="e@x.com")
    db.add(user)
    db.commit()
    assert plan_retrieval(db, user, "Who worked on Atlas?").mode == "vector"


def test_router_builds_graph_lazily_for_pre_graph_accounts(db):
    user = seed_mailbox(db)                      # chunks exist, graph does not (old install)
    plan = plan_retrieval(db, user, "Who worked on Atlas?")
    assert plan.mode == "graph" and plan.facts


def test_load_chunks_refuses_other_users_data(db, seeded):
    user, _ = seeded
    ids = list(db.execute(select(Chunk.id)).scalars())
    assert len(load_chunks(db, user.id, ids)) == len(ids)
    assert load_chunks(db, "intruder", ids) == []


@pytest.fixture()
def stubs(monkeypatch, db):
    captured = {}

    def fake_llm(prompt, max_tokens=800, force_json=False):
        captured["prompt"] = prompt
        return "stubbed answer"

    def fake_retrieve(db_, user_id, question, top_k=8):
        rows = db_.execute(select(Chunk).where(Chunk.user_id == user_id).order_by(Chunk.id)).scalars().all()
        captured["top_k"] = top_k
        return rows[:top_k]

    monkeypatch.setattr(chat_module, "chat_completion", fake_llm)
    monkeypatch.setattr(chat_module, "retrieve_context", fake_retrieve)
    return captured


def test_chat_turn_merges_graph_and_vector_context_with_consistent_citations(db, seeded, stubs):
    user, _ = seeded
    out = chat_module.answer_question(db, user, "Who worked on Atlas?")
    assert out["answer"] == "stubbed answer"
    assert out["route"]["mode"] == "graph" and out["route"]["graph_facts"] >= 2
    assert out["route"]["entities"][0]["name"] == "Atlas migration"
    assert stubs["top_k"] == 3

    prompt = stubs["prompt"]
    assert "RELATIONSHIP FACTS:" in prompt and "Priya Sharma" in prompt and "Rahul Verma" in prompt

    n_sources = len(out["sources"])
    cited = {int(n) for n in re.findall(r"\[source: (\d+)\]", prompt)}
    assert cited and max(cited) <= n_sources                      # every citation points at a real source
    assert [s["index"] for s in out["sources"]] == list(range(1, n_sources + 1))
    assert len({s["chunk_id"] for s in out["sources"]}) == n_sources   # no duplicates
    first = out["sources"][0]
    assert first["subject"] and first["url"].startswith("https://mail.google.com/") and first["date"]
    assert n_sources <= chat_module.MAX_CONTEXT_CHUNKS


def test_graph_evidence_comes_first_in_the_context(db, seeded, stubs):
    user, _ = seeded
    out = chat_module.answer_question(db, user, "Who worked on Atlas?")
    first_fact_cites = re.findall(r"\[source: (\d+)\]", stubs["prompt"].split("SOURCE DOCUMENTS:")[0])
    assert first_fact_cites and min(map(int, first_fact_cites)) == 1


def test_vector_route_has_no_graph_block_noise(db, seeded, stubs):
    user, _ = seeded
    out = chat_module.answer_question(db, user, "What is the capital of France?")
    assert out["route"]["mode"] == "vector" and stubs["top_k"] == 8
    assert "(no relationship facts matched this question)" in stubs["prompt"]


def test_nothing_ingested_returns_friendly_message(db, monkeypatch):
    user = User(id="blank", email="b@x.com")
    db.add(user)
    db.commit()
    monkeypatch.setattr(chat_module, "retrieve_context", lambda *a, **k: [])
    monkeypatch.setattr(chat_module, "chat_completion", lambda *a, **k: pytest.fail("LLM must not be called"))
    out = chat_module.answer_question(db, user, "anything")
    assert "don't have any ingested data" in out["answer"] and out["sources"] == []
