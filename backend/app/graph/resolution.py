"""
Entity resolution for the knowledge graph — pure Python, no database.

The extraction model emits free-text names per chunk ("Priya", "Priya Sharma",
"Sharma, Priya", "Project Atlas", "Atlas migration"). Left alone, every spelling
becomes its own node and the graph fragments. This module decides which mentions
refer to the same real-world entity.

Design rules (all deliberately conservative — a wrong merge silently corrupts the
record, while a missed merge is visible and fixable):
  * Mentions are resolved in a single batch, most-specific names first (more tokens,
    then more frequent). Full names therefore exist before bare first names arrive, so
    the result does not depend on the order emails were ingested.
  * A bare first or last name merges into a full name ONLY if exactly one existing
    person could be meant. "Sam" with both "Sam Lee" and "Sam Patel" present stays its
    own (name-only) node rather than guessing.
  * Fuzzy matching is a typo guard (>= 0.92 similarity), not a similarity search, so
    "John Smith" and "John Smyth" are NOT merged.
  * Two non-identical names never merge if both carry email addresses and the
    addresses do not overlap.
"""
from __future__ import annotations

import difflib
import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import getaddresses
from typing import Iterable

from app.db.models import gen_uuid

# --------------------------------------------------------------------------- vocab

GENERIC_PEOPLE = {
    "team", "everyone", "everybody", "all", "me", "you", "us", "we", "i", "someone",
    "anyone", "somebody", "client", "customer", "customers", "manager", "management",
    "hr", "admin", "administrator", "support", "unknown", "none", "n/a", "na", "tbd",
    "vendor", "stakeholders", "stakeholder", "group", "department", "staff", "user",
    "users", "colleague", "colleagues", "he", "she", "they", "them",
}
GENERIC_PROJECTS = {
    "project", "projects", "none", "n/a", "na", "tbd", "various", "general", "misc",
    "miscellaneous", "meeting", "meetings", "email", "update", "updates", "weekly update",
    "work", "task", "tasks", "team", "unknown",
}
_TITLES = {"mr", "mrs", "ms", "miss", "dr", "prof", "sir", "shri", "smt"}
_PROJECT_STOP = {"project", "the", "a", "an", "initiative"}
_SYSTEM_LOCALPART = re.compile(
    r"(no-?reply|do-?not-?reply|notifications?|mailer-daemon|postmaster|bounces?|alerts?|"
    r"newsletter|calendar-notification|updates?@)", re.I)

FUZZY_THRESHOLD = 0.92
TEXT_DEDUPE_THRESHOLD = 0.70


# ------------------------------------------------------------------------ normalizers

def clean_person_display(raw: str) -> str:
    """'"Sharma, Priya" <p@x.com>' -> 'Priya Sharma'. Keeps original casing."""
    n = (raw or "").strip()
    n = re.sub(r"<[^>]*>", " ", n)
    n = re.sub(r"\([^)]*\)", " ", n)
    n = n.replace('"', " ").strip()
    if n.count(",") == 1:
        last, first = [x.strip() for x in n.split(",")]
        ok = lambda s: s and not re.search(r"\d", s) and len(s.split()) <= 2
        if ok(last) and ok(first):
            n = f"{first} {last}"
    return re.sub(r"\s+", " ", n).strip()


def normalize_person(raw: str) -> str:
    n = clean_person_display(raw).lower()
    n = re.sub(r"[^a-z0-9À-ɏऀ-ॿ ]+", " ", n)
    toks = [t for t in n.split() if t not in _TITLES]
    return " ".join(toks)


def normalize_project(raw: str) -> str:
    n = re.sub(r"\([^)]*\)", " ", (raw or "").lower())
    n = re.sub(r"[^a-z0-9À-ɏऀ-ॿ ]+", " ", n)
    toks = [t for t in n.split() if t not in _PROJECT_STOP]
    return " ".join(toks)


def normalize_text(raw: str) -> str:
    n = re.sub(r"[^a-z0-9 ]+", " ", (raw or "").lower())
    return re.sub(r"\s+", " ", n).strip()


def is_generic_person(key: str) -> bool:
    if not key or len(key) < 2 or key.isdigit():
        return True
    return all(t in GENERIC_PEOPLE for t in key.split())


def is_generic_project(key: str) -> bool:
    return (not key) or len(key) < 2 or key.isdigit() or key in GENERIC_PROJECTS


def pretty(raw: str) -> str:
    """Title-case only when the raw string is all lower/upper; never mangle 'McDonald'."""
    return raw.title() if raw and (raw.islower() or raw.isupper()) else raw


def name_from_email(email: str) -> str | None:
    """'priya.sharma@acme.com' -> 'Priya Sharma'; system/no-reply senders -> None."""
    local = (email or "").split("@")[0]
    if not local or _SYSTEM_LOCALPART.search(email or ""):
        return None
    toks = [t for t in re.split(r"[._\-+]+", local) if t.isalpha()]
    if len(toks) >= 2:
        return " ".join(t.capitalize() for t in toks)
    if len(toks) == 1 and len(toks[0]) >= 3:
        return toks[0].capitalize()
    return None


def parse_header_people(participants: dict | None, limit_recipients: int = 10) -> list[dict]:
    """
    Parses the stored {"from": "...", "to": [...]} header dict into
    [{"name": str|None, "email": str, "role": "from"|"to"}], dropping system senders.
    Robust to the connector having split a quoted 'Doe, John' recipient on its comma.
    """
    out: list[dict] = []
    participants = participants or {}
    sender = participants.get("from") or ""
    to_list = participants.get("to") or []
    pairs: list[tuple[str, str, str]] = []
    for name, addr in getaddresses([sender]):
        pairs.append((name, addr, "from"))
    for name, addr in getaddresses([",".join(to_list)])[:limit_recipients]:
        pairs.append((name, addr, "to"))
    seen: set[str] = set()
    for name, addr, role in pairs:
        addr = (addr or "").strip().lower()
        if not addr or "@" not in addr or addr in seen or _SYSTEM_LOCALPART.search(addr):
            continue
        seen.add(addr)
        display = clean_person_display(name) or name_from_email(addr)
        out.append({"name": display, "email": addr, "role": role})
    return out


# ----------------------------------------------------------------------- data classes

@dataclass
class Mention:
    raw: str
    email: str | None = None
    date: datetime | None = None
    role: str | None = None   # free-text role/context from the extractor


@dataclass
class Entity:
    id: str
    kind: str
    key: str
    name: str
    keys: set[str] = field(default_factory=set)
    aliases: set[str] = field(default_factory=set)
    emails: set[str] = field(default_factory=set)
    roles: list[str] = field(default_factory=list)
    name_only: bool = False   # bare first/last name that could not be tied to one full name


# -------------------------------------------------------------------------- resolver

class EntityResolver:
    """Batch resolver for one entity kind: 'person' or 'project'."""

    def __init__(self, kind: str):
        assert kind in ("person", "project")
        self.kind = kind
        self.entities: list[Entity] = []
        self.key_to_entity: dict[str, Entity] = {}
        self.email_to_entity: dict[str, Entity] = {}

    # -- public

    def normalize(self, raw: str) -> str:
        return normalize_person(raw) if self.kind == "person" else normalize_project(raw)

    def build(self, mentions: Iterable[Mention]) -> "EntityResolver":
        groups: dict[str, dict] = {}
        for m in mentions:
            key = self.normalize(m.raw)
            generic = is_generic_person(key) if self.kind == "person" else is_generic_project(key)
            if generic:
                continue
            g = groups.setdefault(key, {"raws": Counter(), "emails": set(), "roles": [], "count": 0})
            g["raws"][clean_person_display(m.raw) if self.kind == "person" else m.raw.strip()] += 1
            g["count"] += 1
            if m.email:
                g["emails"].add(m.email.lower())
            if m.role and m.role not in g["roles"] and len(g["roles"]) < 3:
                g["roles"].append(m.role)

        order = sorted(groups, key=lambda k: (-len(k.split()), -groups[k]["count"], k))
        for key in order:
            g = groups[key]
            ent = self._match(key, g)
            if ent is None:
                ent = Entity(id=gen_uuid(), kind=self.kind, key=key, name="")
                self.entities.append(ent)
                ent.name_only = self.kind == "person" and len(key.split()) == 1
            self._absorb(ent, key, g)
        return self

    def lookup(self, raw: str | None, email: str | None = None) -> Entity | None:
        if email:
            ent = self.email_to_entity.get(email.lower())
            if ent:
                return ent
        if not raw:
            return None
        return self.key_to_entity.get(self.normalize(raw))

    # -- matching

    def _match(self, key: str, g: dict) -> Entity | None:
        emails = g["emails"]
        for e in emails:                                  # shared address: strongest signal
            if e in self.email_to_entity:
                return self.email_to_entity[e]
        if not self.entities:
            return None
        return self._match_person(key, emails) if self.kind == "person" else self._match_project(key)

    def _match_person(self, key: str, emails: set[str]) -> Entity | None:
        toks = key.split()
        found: dict[str, Entity] = {}
        for ent in self.entities:
            if emails and ent.emails and not (emails & ent.emails):
                continue                                  # both have addresses, none shared -> distinct
            for ek in ent.keys:
                etoks = ek.split()
                if len(toks) >= 2:
                    if len(etoks) >= 2 and toks[0] == etoks[0] and toks[-1] == etoks[-1]:
                        found[ent.id] = ent               # "priya k sharma" == "priya sharma"
                    elif len(etoks) >= 2 and key[0] == ek[0] and _ratio(key, ek) >= FUZZY_THRESHOLD:
                        found[ent.id] = ent               # typo guard
                else:
                    tok = toks[0]
                    if len(tok) >= 3 and len(etoks) >= 2 and tok in (etoks[0], etoks[-1]):
                        found[ent.id] = ent               # bare first/last name
        return next(iter(found.values())) if len(found) == 1 else None

    def _match_project(self, key: str) -> Entity | None:
        tset = set(key.split())
        found: dict[str, Entity] = {}
        for ent in self.entities:
            for ek in ent.keys:
                eset = set(ek.split())
                if _ratio(key, ek) >= 0.90:
                    found[ent.id] = ent
                    continue
                shorter, longer = (tset, eset) if len(tset) <= len(eset) else (eset, tset)
                if shorter < longer and (len(shorter) >= 2 or any(len(t) >= 4 for t in shorter)):
                    found[ent.id] = ent                   # "atlas" ⊂ "atlas migration"
        return next(iter(found.values())) if len(found) == 1 else None

    def _absorb(self, ent: Entity, key: str, g: dict) -> None:
        ent.keys.add(key)
        self.key_to_entity[key] = ent
        for raw, _ in g["raws"].most_common():
            ent.aliases.add(pretty(raw))
        for e in g["emails"]:
            ent.emails.add(e)
            self.email_to_entity[e] = ent
        for r in g["roles"]:
            if r not in ent.roles and len(ent.roles) < 3:
                ent.roles.append(r)
        if not ent.name:                                  # first (most specific) form wins as display
            ent.name = pretty(g["raws"].most_common(1)[0][0])
        if len(key.split()) > 1:
            ent.name_only = False


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------- text de-duplication

_STOP = {"the", "a", "an", "to", "of", "and", "for", "on", "in", "we", "is", "be", "will",
         "with", "that", "this", "it", "are", "as", "by", "at", "from", "or"}


def token_set(text: str) -> frozenset[str]:
    return frozenset(t for t in normalize_text(text).split() if t not in _STOP)


def text_key(text: str) -> str:
    return hashlib.sha1(normalize_text(text).encode()).hexdigest()[:20]


class TextIndex:
    """
    Near-duplicate finder for decisions and action items. Overlapping chunks (150-word
    overlap) routinely make the extractor report the same decision twice with slightly
    different wording; token-set Jaccard similarity collapses those.
    """

    def __init__(self, threshold: float = TEXT_DEDUPE_THRESHOLD):
        self.threshold = threshold
        self._items: list[tuple[frozenset[str], object]] = []

    def find(self, text: str):
        ts = token_set(text)
        if not ts:
            return None
        for other, payload in self._items:
            union = len(ts | other)
            if union and len(ts & other) / union >= self.threshold:
                return payload
        return None

    def add(self, text: str, payload) -> None:
        self._items.append((token_set(text), payload))
