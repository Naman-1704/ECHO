import re

# Fast, cheap first pass — catches obvious PII patterns before anything hits an LLM.
# This is NOT a substitute for the consent/review workflow described in the product
# doc (departing employee marking folders as excluded) — treat this as defense-in-depth,
# not the primary control.

_PATTERNS = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "salary_mention": re.compile(r"\b(salary|compensation|ctc)\b.{0,40}\b(\d{4,})\b", re.IGNORECASE),
}

# Subject-line / label heuristics for likely-personal threads — extend this list
# with your org's actual HR/personal label names once you see real data.
_SENSITIVE_SUBJECT_KEYWORDS = [
    "performance review", "medical", "leave application", "salary", "payslip",
    "hr confidential", "personal", "resignation", "disciplinary",
]


def contains_sensitive_pattern(text: str) -> bool:
    return any(p.search(text) for p in _PATTERNS.values())


def is_likely_personal_subject(subject: str) -> bool:
    subject_lower = (subject or "").lower()
    return any(kw in subject_lower for kw in _SENSITIVE_SUBJECT_KEYWORDS)


def should_exclude(subject: str, body: str) -> bool:
    """
    Returns True if this item should be excluded from ingestion entirely.
    Call this BEFORE chunking/embedding/extraction — never after.
    """
    return is_likely_personal_subject(subject) or contains_sensitive_pattern(body)


def redact_patterns(text: str) -> str:
    """For items that pass the exclusion check but still contain isolated PII spans."""
    redacted = text
    for name, pattern in _PATTERNS.items():
        redacted = pattern.sub(f"[REDACTED_{name.upper()}]", redacted)
    return redacted
