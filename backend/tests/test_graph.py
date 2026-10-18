from sqlalchemy import select

from app.db.models import Chunk, GraphEdge, GraphNode
from app.graph.builder import rebuild_graph, ensure_graph, graph_exists
from app.graph.insights import attention_report, key_people, timeline
from app.graph.queries import (
    entity_facts, find_entities, get_graph_view, get_node_detail, pending_facts,
)
from conftest import NOW, seed_mailbox


def node(db, user, type_, name):
    return db.execute(select(GraphNode).where(GraphNode.user_id == user.id, GraphNode.type == type_,
                                              GraphNode.name == name)).scalar_one()


def edge(db, user, src, dst, rel):
    a, b = (src.id, dst.id)
    if rel == "COLLABORATES_WITH" and a > b:
        a, b = b, a
    return db.execute(select(GraphEdge).where(GraphEdge.user_id == user.id, GraphEdge.src_id == a,
                                              GraphEdge.dst_id == b, GraphEdge.relation == rel)).scalar_one_or_none()


# ------------------------------------------------------------------------ building

def test_node_counts_after_resolution(db, seeded):
    user, stats = seeded
    assert stats["people"] == 6      # Predecessor, Rahul, Priya, Sam Lee, Sam Patel, bare "Sam"
    assert stats["projects"] == 4    # Atlas migration, Billing revamp, Legacy cleanup, Archive migration
    assert stats["decisions"] == 2   # the near-duplicate phased-rollout decision was collapsed
    assert stats["actions"] == 3     # the repeated staging-environment action was collapsed
    names = {n.name for n in db.execute(select(GraphNode).where(GraphNode.type == "person")).scalars()}
    assert "Noreply" not in names and "No-Reply" not in names      # system sender excluded
    assert len(names) == 6


def test_name_variants_became_one_person_with_aliases(db, seeded):
    user, _ = seeded
    priya = node(db, user, "person", "Priya Sharma")
    assert "priya.sharma@acme.com" in priya.attrs["emails"]
    assert "infra lead" in priya.attrs["roles"]
    atlas = node(db, user, "project", "Atlas migration")
    assert {"Atlas", "Project Atlas"} <= set(atlas.aliases)


def test_ambiguous_sam_stays_separate_and_is_marked(db, seeded):
    user, _ = seeded
    assert node(db, user, "person", "Sam").attrs["name_only"] is True
    assert node(db, user, "person", "Sam Lee").attrs["name_only"] is False


def test_mailbox_owner_is_flagged_exactly_once(db, seeded):
    user, _ = seeded
    owners = db.execute(select(GraphNode).where(GraphNode.is_owner.is_(True))).scalars().all()
    assert [o.name for o in owners] == ["Predecessor"]


def test_edge_weights_count_distinct_chunks(db, seeded):
    user, _ = seeded
    priya, rahul, pred = (node(db, user, "person", n) for n in ("Priya Sharma", "Rahul Verma", "Predecessor"))
    atlas = node(db, user, "project", "Atlas migration")
    assert edge(db, user, priya, atlas, "WORKS_ON").weight == 3      # m1, m2, m3
    assert edge(db, user, rahul, atlas, "WORKS_ON").weight == 2      # m1, m2
    assert edge(db, user, priya, rahul, "COLLABORATES_WITH").weight == 2
    assert edge(db, user, priya, pred, "COLLABORATES_WITH").weight == 5   # m1,m2,m3,m5,m6


def test_collaboration_edges_are_stored_once(db, seeded):
    user, _ = seeded
    pairs = db.execute(select(GraphEdge.src_id, GraphEdge.dst_id).where(GraphEdge.relation == "COLLABORATES_WITH")).all()
    assert len(pairs) == len({tuple(sorted(p)) for p in pairs})
    assert all(a < b for a, b in pairs)


def test_decision_and_action_links(db, seeded):
    user, _ = seeded
    atlas = node(db, user, "project", "Atlas migration")
    rahul = node(db, user, "person", "Rahul Verma")
    decision = db.execute(select(GraphNode).where(GraphNode.type == "decision",
                                                  GraphNode.name.like("Move forward%"))).scalar_one()
    assert decision.attrs["reasoning"] == "allows per-service rollback"      # kept from the first mention
    assert edge(db, user, decision, atlas, "ABOUT").weight == 2
    action = db.execute(select(GraphNode).where(GraphNode.type == "action", GraphNode.name.like("Set up the staging%"))).scalar_one()
    assert action.attrs["owner"] == "Rahul Verma"
    assert edge(db, user, rahul, action, "OWNS").weight == 2
    assert action.last_seen.day == 12                                        # latest mention (m2)


def test_every_edge_evidence_id_is_a_real_chunk(db, seeded):
    user, _ = seeded
    chunk_ids = set(db.execute(select(Chunk.id)).scalars())
    for e in db.execute(select(GraphEdge)).scalars():
        assert e.evidence and set(e.evidence) <= chunk_ids


def test_rebuild_is_idempotent(db, seeded):
    user, first = seeded
    second = rebuild_graph(db, user)
    assert first == second
    assert db.execute(select(GraphNode)).scalars().all().__len__() == first["nodes"]


def test_ensure_graph_builds_lazily_for_existing_accounts(db):
    user = seed_mailbox(db)
    assert not graph_exists(db, user.id)
    assert ensure_graph(db, user) is True
    assert graph_exists(db, user.id)


def test_malformed_model_output_does_not_crash_the_build(db):
    from conftest import add_item
    from app.db.models import User
    user = User(id="u9", email="x@y.com")
    db.add(user)
    db.flush()
    add_item(db, user, "bad1", "Weird", NOW, "A B <a@b.com>", [], [
        {"people": "not a list", "projects": [None, 5, {"name": ""}, "Zephyr"], "decisions": [{"decision": 12}],
         "action_items": [{"description": "Review the Zephyr design", "owner": "a@b.com"}]},
        {"people": [{"name": None}, "Dana Roe"], "_parse_error": True},
    ])
    db.commit()
    stats = rebuild_graph(db, user)
    assert stats["projects"] == 1 and stats["actions"] == 1


# --------------------------------------------------------------------------- queries

def test_graph_view_filters(db, seeded):
    user, _ = seeded
    full = get_graph_view(db, user.id)
    assert {n["type"] for n in full["nodes"]} == {"person", "project"}
    assert any(n["is_owner"] for n in full["nodes"])
    no_owner = get_graph_view(db, user.id, hide_owner=True)
    assert not any(n["is_owner"] for n in no_owner["nodes"])
    ids = {n["id"] for n in no_owner["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in no_owner["edges"])
    heavy = get_graph_view(db, user.id, min_weight=3)
    assert all(e["weight"] >= 3 for e in heavy["edges"])
    assert len(heavy["nodes"]) < len(full["nodes"])
    only_people = get_graph_view(db, user.id, types=("person",))
    assert {e["relation"] for e in only_people["edges"]} == {"COLLABORATES_WITH"}
    limited = get_graph_view(db, user.id, limit=3)
    assert len(limited["nodes"]) <= 3


def test_graph_view_always_includes_a_focused_node(db, seeded):
    user, _ = seeded
    bill = node(db, user, "project", "Billing revamp")
    view = get_graph_view(db, user.id, limit=1, focus_id=bill.id)
    assert bill.id in {n["id"] for n in view["nodes"]}


def test_node_detail_has_neighbors_and_linkable_evidence(db, seeded):
    user, _ = seeded
    atlas = node(db, user, "project", "Atlas migration")
    d = get_node_detail(db, user.id, atlas.id)
    assert d["people"][0]["name"] in {"Predecessor", "Priya Sharma"}
    assert any(p["name"] == "Priya Sharma" for p in d["people"])
    assert any(x["decision"].startswith("Choose Vendor B") for x in d["decisions"])
    assert any(a["description"].startswith("Send the vendor contract") for a in d["actions"])
    assert d["evidence"] and d["evidence"][0]["url"].startswith("https://mail.google.com/")


def test_node_detail_is_isolated_per_user(db, seeded):
    user, _ = seeded
    atlas = node(db, user, "project", "Atlas migration")
    assert get_node_detail(db, "someone-else", atlas.id) is None


def test_find_entities(db, seeded):
    user, _ = seeded
    assert [n.name for n in find_entities(db, user.id, "Who worked on Atlas?")] == ["Atlas migration"]
    assert [n.name for n in find_entities(db, user.id, "Tell me about priya sharma")] == ["Priya Sharma"]
    assert [n.name for n in find_entities(db, user.id, "What projects did he work on?")] == ["Predecessor"]
    assert find_entities(db, user.id, "What is the weather today?") == []
    both = find_entities(db, user.id, "Did Priya work on Billing revamp?")
    assert {n.name for n in both} == {"Priya Sharma", "Billing revamp"}


def test_pronoun_does_not_override_a_named_person(db, seeded):
    user, _ = seeded
    got = find_entities(db, user.id, "What is Priya doing and what is her role?")
    assert [n.name for n in got] == ["Priya Sharma"]


def test_entity_facts_carry_names_and_evidence(db, seeded):
    user, _ = seeded
    facts = entity_facts(db, user.id, node(db, user, "project", "Atlas migration"))
    text = " ".join(f["text"] for f in facts)
    assert "Priya Sharma" in text and "Rahul Verma" in text
    assert "Choose Vendor B" in text and "Send the vendor contract" in text
    assert all(f["chunk_ids"] for f in facts if "Open action" in f["text"] or "People connected" in f["text"])
    owner_facts = entity_facts(db, user.id, node(db, user, "person", "Predecessor"))
    assert "mailbox owner" in owner_facts[0]["text"]


def test_pending_facts_list_open_items(db, seeded):
    user, _ = seeded
    facts = pending_facts(db, user.id)
    assert len(facts) == 3 and all(f["chunk_ids"][0] for f in facts)


# -------------------------------------------------------------------------- insights

def test_attention_report(db, seeded):
    user, _ = seeded
    r = attention_report(db, user.id, stale_days=14, dormant_days=60, now=NOW)
    assert r["counts"]["open_actions"] == 3
    assert r["counts"]["stale_actions"] == 3
    assert r["stale_actions"][0]["age_days"] >= r["stale_actions"][-1]["age_days"]
    assert [a["description"] for a in r["unowned_actions"]] == ["Send the vendor contract to legal for review"]
    reasons = {c["name"]: c["reason"] for c in r["concentrated_projects"]}
    assert reasons["Legacy cleanup"] == "one_person"
    assert reasons["Archive migration"] == "only_predecessor"
    assert "Atlas migration" not in reasons                      # two other people know Atlas
    assert "Atlas migration" in {d["name"] for d in r["dormant_projects"]}
    assert r["stale_actions"][0]["source"]["url"]


def test_attention_thresholds_are_respected(db, seeded):
    user, _ = seeded
    assert attention_report(db, user.id, stale_days=400, now=NOW)["counts"]["stale_actions"] == 0


def test_key_people_excludes_owner_and_ranks_by_connection(db, seeded):
    user, _ = seeded
    kp = key_people(db, user.id)
    assert kp["owner"]["name"] == "Predecessor"
    assert kp["people"][0]["name"] == "Priya Sharma"
    assert all(p["name"] != "Predecessor" for p in kp["people"])
    assert kp["people"][0]["projects"][0]["name"] == "Atlas migration"


def test_timeline_is_newest_first_with_sources(db, seeded):
    user, _ = seeded
    ev = timeline(db, user.id)["events"]
    assert [e["date"] for e in ev] == sorted((e["date"] for e in ev), reverse=True)
    assert {e["type"] for e in ev} == {"decision", "action"}
    assert all(e["source"] and e["source"]["subject"] for e in ev)
