"""
Shared fixtures. Environment variables are forced BEFORE any app import so tests can
never touch a developer's real database, vector store, or Google credentials.
"""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="echo_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["CHROMA_PERSIST_DIR"] = f"{_TMP}/chroma"
os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
os.environ["GOOGLE_CLIENT_SECRET"] = "test-client-secret"
os.environ["SECRET_KEY"] = "test-secret-key"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models import Base, Chunk, RawItem, User  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402

NOW = datetime(2026, 5, 1, 12, 0)   # fixed "today" for age calculations


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def add_item(db, user, source_id, subject, date, sender, to, extracted_list, source="gmail"):
    item = RawItem(user_id=user.id, source=source, source_id=source_id, subject_or_title=subject,
                   participants={"from": sender, "to": to}, raw_text=subject, item_date=date)
    db.add(item)
    db.flush()
    ids = []
    for ex in extracted_list:
        chunk = Chunk(raw_item_id=item.id, user_id=user.id, text=f"{subject}: {json.dumps(ex)[:160]}", extracted=ex)
        db.add(chunk)
        db.flush()
        ids.append(chunk.id)
    return item, ids


PRED = "Predecessor <predecessor@acme.com>"
PRIYA = "Priya Sharma <priya.sharma@acme.com>"
RAHUL = "Rahul Verma <rahul@acme.com>"


def seed_mailbox(db, email="predecessor@acme.com", user_id="u1") -> User:
    """A small but deliberately messy mailbox. See comments for what each item exercises."""
    user = User(id=user_id, email=email)
    db.add(user)
    db.flush()
    d = lambda m, day: datetime(2026, m, day, 9, 0)

    # m1: bare first name "Priya", "Project Atlas", a decision with reasoning, an owned action
    add_item(db, user, "m1", "Atlas migration kickoff", d(1, 10), RAHUL, [PRED, " " + PRIYA], [{
        "people": [{"name": "Priya", "role_or_context": "infra lead"}, {"name": "Rahul Verma", "role_or_context": "engineer"}],
        "projects": [{"name": "Project Atlas", "context": "cloud migration"}],
        "decisions": [{"decision": "Move forward with the phased rollout instead of a big-bang cutover",
                       "reasoning": "allows per-service rollback", "date": "2026-01-10"}],
        "action_items": [{"description": "Set up the staging environment for Atlas", "owner": "Rahul", "status": "open"}],
    }])
    # m2: near-duplicate decision (overlapping-chunk style) + the same action again
    add_item(db, user, "m2", "Re: Atlas migration kickoff", d(1, 12), PRIYA, [RAHUL, " " + PRED], [{
        "people": [{"name": "Priya Sharma", "role_or_context": ""}],
        "projects": [{"name": "Atlas", "context": ""}],
        "decisions": [{"decision": "Move forward with the phased rollout instead of a big-bang cutover for Atlas",
                       "reasoning": None, "date": None}],
        "action_items": [{"description": "Set up the staging environment for Atlas", "owner": "Rahul Verma", "status": "open"}],
    }])
    # m3: quoted "Sharma, Priya" header, "Atlas migration", an UNOWNED action
    add_item(db, user, "m3", "Atlas vendor selection", d(1, 20), '"Sharma, Priya" <priya.sharma@acme.com>', [PRED], [{
        "people": [{"name": "Sharma, Priya", "role_or_context": ""}],
        "projects": [{"name": "Atlas migration", "context": "vendor choice"}],
        "decisions": [{"decision": "Choose Vendor B for the logging pipeline", "reasoning": "lower cost and better SLA", "date": None}],
        "action_items": [{"description": "Send the vendor contract to legal for review", "owner": None, "status": "open"}],
    }])
    # m4: two different Sams in the headers + a bare "Sam" -> must stay ambiguous
    add_item(db, user, "m4", "Billing revamp scoping", d(2, 15), PRED,
             ["Sam Lee <sam.lee@acme.com>", " Sam Patel <sam.patel@acme.com>"], [{
        "people": [{"name": "Sam", "role_or_context": ""}],
        "projects": [{"name": "Billing revamp", "context": ""}],
        "decisions": [],
        "action_items": [{"description": "Draft the scoping document for the billing revamp", "owner": "Sam", "status": "open"}],
    }])
    # m5/m6: a project known through exactly ONE other person (knowledge concentration)
    for sid, day, subj in (("m5", (3, 1), "Legacy cleanup plan"), ("m6", (3, 10), "Legacy cleanup follow-up")):
        add_item(db, user, sid, subj, d(*day), PRIYA, [PRED], [{"projects": [{"name": "Legacy cleanup", "context": ""}]}])
    # m7/m8: only the predecessor ever appears with this project
    for sid, day, subj in (("m7", (3, 12), "Archive migration notes"), ("m8", (3, 14), "Archive migration notes 2")):
        add_item(db, user, sid, subj, d(*day), PRED, [], [{"projects": [{"name": "Archive migration", "context": ""}]}])
    # m9: automated sender must never become a person
    add_item(db, user, "m9", "Invoice", d(3, 20), "Noreply <no-reply@vendor.com>", [PRED], [{}])

    db.commit()
    return user


@pytest.fixture()
def seeded(db):
    from app.graph.builder import rebuild_graph
    user = seed_mailbox(db)
    stats = rebuild_graph(db, user)
    return user, stats
