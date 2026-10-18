import subprocess
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.routes import create_session_token
from app.db.models import AuditLog, Chunk, GraphNode, RawItem, User
from app.db.session import get_db
from app.ingestion import jobs
from app.ingestion.drive_connector import fetch_files
from app.main import app
from app.reports.handover import build_report_data, render_markdown, render_pdf
from conftest import NOW, seed_mailbox


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def auth(user_id):
    return {"Authorization": f"Bearer {create_session_token(user_id)}"}


# ----------------------------------------------------------------------------- routes

def test_graph_routes_require_login(client):
    for path in ("/graph/network", "/insights/attention", "/insights/timeline", "/reports/handover"):
        assert client.get(path).status_code == 422 or client.get(path).status_code == 401


def test_network_and_node_detail(client, seeded):
    user, _ = seeded
    r = client.get("/graph/network?types=person,project", headers=auth(user.id))
    assert r.status_code == 200
    body = r.json()
    names = {n["name"] for n in body["nodes"]}
    assert "Atlas migration" in names and body["edges"]
    atlas = next(n for n in body["nodes"] if n["name"] == "Atlas migration")
    d = client.get(f"/graph/node/{atlas['id']}", headers=auth(user.id))
    assert d.status_code == 200 and d.json()["node"]["name"] == "Atlas migration"


def test_node_detail_is_user_scoped(client, db, seeded):
    user, _ = seeded
    node = db.execute(select(GraphNode).where(GraphNode.user_id == user.id)).scalars().first()
    db.add(User(id="other", email="o@x.com"))
    db.commit()
    assert client.get(f"/graph/node/{node.id}", headers=auth("other")).status_code == 404
    assert client.get("/graph/node/nope", headers=auth(user.id)).status_code == 404


def test_network_empty_account(client, db):
    db.add(User(id="blank", email="b@x.com"))
    db.commit()
    r = client.get("/graph/network", headers=auth("blank"))
    assert r.status_code == 200 and r.json()["nodes"] == []


def test_insight_routes(client, seeded):
    user, _ = seeded
    h = auth(user.id)
    att = client.get("/insights/attention", headers=h).json()
    assert att["unowned_actions"] and "concentrated_projects" in att
    assert client.get("/insights/key-people?limit=3", headers=h).json()["people"]
    assert client.get("/insights/timeline", headers=h).status_code == 200
    assert client.post("/graph/rebuild", headers=h).json()["projects"] >= 3


def test_dashboard_summary_dedupes_people(client, seeded):
    user, _ = seeded
    s = client.get("/dashboard/summary", headers=auth(user.id)).json()
    priyas = [p for p in s["people"] if "priya" in p["name"].lower()]
    assert len(priyas) == 1
    assert s["stats"]["unique_projects"] >= 3 and s["decisions"] and s["pending_actions"]


# ----------------------------------------------------------------------------- report

def test_report_data_and_markdown(db, seeded):
    user, _ = seeded
    data = build_report_data(db, user, now=NOW)
    assert data["counts"]["projects"] >= 3 and data["decisions"]
    assert any(a["text"].startswith("Send the vendor contract") for a in data["attention"]["unowned_actions"])
    md = render_markdown(data)
    assert md.startswith("# ECHO handover report") and "Atlas migration" in md
    assert "https://mail.google.com/" in md


def test_report_pdf_is_valid_and_has_links(db, seeded):
    user, _ = seeded
    pdf = render_pdf(build_report_data(db, user, now=NOW))
    assert pdf[:5] == b"%PDF-" and len(pdf) > 3000
    assert b"/URI" in pdf and b"mail.google.com" in pdf


def test_report_pdf_handles_unicode_and_empty(db):
    user = User(id="uni", email="u@x.com")
    db.add(user)
    db.commit()
    assert render_pdf(build_report_data(db, user))[:5] == b"%PDF-"     # empty account
    data = build_report_data(db, seed_mailbox(db, email="p@acme.com", user_id="u2"))
    data["key_people"][0]["name"] = "Zoë Łukasz <b>&</b>"
    assert render_pdf(data)[:5] == b"%PDF-"                             # markup chars are escaped


def test_report_endpoint(client, db, seeded):
    user, _ = seeded
    r = client.get("/reports/handover?format=pdf", headers=auth(user.id))
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
    assert "echo-handover-report.pdf" in r.headers["content-disposition"]
    m = client.get("/reports/handover?format=md", headers=auth(user.id))
    assert m.status_code == 200 and "Atlas" in m.text
    assert client.get("/reports/handover?format=docx", headers=auth(user.id)).status_code == 422
    assert db.execute(select(AuditLog).where(AuditLog.action == "report_exported")).scalars().all()


# ------------------------------------------------------------------------------ drive

class _Exec:
    def __init__(self, v): self.v = v
    def execute(self):
        if isinstance(self.v, Exception):
            raise self.v
        return self.v


class FakeDrive:
    def __init__(self, files, contents):
        self.files_, self.contents = files, contents
    def files(self): return self
    def list(self, **kw): return _Exec({"files": self.files_, "nextPageToken": "NP"})
    def export(self, fileId, mimeType): return _Exec(self.contents[fileId])
    def get_media(self, fileId): return _Exec(self.contents[fileId])


def test_drive_fetch_maps_files_to_items():
    files = [
        {"id": "d1", "name": "Atlas runbook", "mimeType": "application/vnd.google-apps.document",
         "modifiedTime": "2026-02-01T10:00:00.000Z",
         "owners": [{"displayName": "Priya Sharma", "emailAddress": "priya.sharma@acme.com"}],
         "lastModifyingUser": {"displayName": "Rahul Verma", "emailAddress": "rahul@acme.com"}},
        {"id": "d2", "name": "broken", "mimeType": "text/plain"},
        {"id": "d3", "name": "empty", "mimeType": "text/plain"},
    ]
    svc = FakeDrive(files, {"d1": b"\xef\xbb\xbfRunbook text", "d2": RuntimeError("403"), "d3": b"  "})
    items, nxt = fetch_files("a", "r", service=svc)
    assert nxt == "NP" and len(items) == 1
    it = items[0]
    assert it["source_id"] == "d1" and it["raw_text"] == "Runbook text"
    assert it["participants"]["from"].startswith("Priya Sharma") and "rahul@acme.com" in it["participants"]["to"][0]
    assert it["item_date"] == datetime(2026, 2, 1, 10, 0) and it["item_date"].tzinfo is None


# -------------------------------------------------------------------------- ingestion

@pytest.fixture()
def pipeline(monkeypatch):
    calls = {"embed": 0}
    monkeypatch.setattr(jobs, "embed_batch", lambda pieces: calls.__setitem__("embed", calls["embed"] + len(pieces)) or [[0.0] * 384 for _ in pieces])
    monkeypatch.setattr(jobs, "add_chunk_embedding", lambda **k: None)
    monkeypatch.setattr(jobs, "extract_structured_facts", lambda text: {
        "people": [{"name": "Priya Sharma", "role_or_context": ""}], "projects": [{"name": "Atlas", "context": ""}],
        "decisions": [], "action_items": []})
    return calls


def _item(sid, subject="Atlas notes", text="Atlas planning with Priya."):
    return {"source_id": sid, "subject_or_title": subject, "participants": {"from": "Priya Sharma <priya.sharma@acme.com>", "to": []},
            "raw_text": text, "item_date": datetime(2026, 4, 1)}


def test_run_ingestion_all_sources_dedupes_filters_and_rebuilds(db, monkeypatch, pipeline):
    user = User(id="u9", email="me@acme.com", google_access_token="a", google_refresh_token="r")
    db.add(user)
    db.commit()
    monkeypatch.setattr(jobs, "fetch_messages", lambda *a, **k: ([_item("g1"), _item("g2", "Salary revision", "details")], "TOK"))
    monkeypatch.setattr(jobs, "fetch_files", lambda *a, **k: ([_item("g1", "Doc with same id as a mail")], None))
    s = jobs.run_ingestion(db, user, source="all")
    assert s["by_source"] == {"gmail": 1, "drive": 1}          # same source_id in a different source is NOT a duplicate
    assert s["excluded"] == 1 and s["next_page_token"] == "TOK" and s["errors"] == []
    assert s["graph"]["projects"] >= 1
    assert {r.source for r in db.execute(select(RawItem)).scalars()} == {"gmail", "drive"}
    s2 = jobs.run_ingestion(db, user, source="all")
    assert s2["skipped_existing"] == 2 and s2["chunks_created"] == 0 and "graph" not in s2


def test_one_failing_source_does_not_lose_the_other(db, monkeypatch, pipeline):
    user = User(id="u8", email="me@acme.com", google_access_token="a", google_refresh_token="r")
    db.add(user)
    db.commit()
    def boom(*a, **k): raise RuntimeError("drive api disabled")
    monkeypatch.setattr(jobs, "fetch_messages", lambda *a, **k: ([_item("g1")], None))
    monkeypatch.setattr(jobs, "fetch_files", boom)
    s = jobs.run_ingestion(db, user, source="all")
    assert s["by_source"]["gmail"] == 1 and any("drive" in e for e in s["errors"])


def test_sync_endpoint_502_when_everything_fails_and_validates_source(client, db, monkeypatch):
    user = User(id="u7", email="me@acme.com")
    db.add(user)
    db.commit()
    def boom(*a, **k): raise RuntimeError("no token")
    monkeypatch.setattr(jobs, "fetch_messages", boom)
    r = client.post("/ingestion/sync?source=gmail", headers=auth("u7"))
    assert r.status_code == 502 and "no token" in r.json()["detail"]
    assert client.post("/ingestion/sync?source=slack", headers=auth("u7")).status_code == 422
