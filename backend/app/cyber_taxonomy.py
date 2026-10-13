"""Cybersecurity role taxonomy and seniority detection.

Categorizes job titles into the 8 groups the user cares about and detects
entry-level seniority. Used by the job ingester (to filter/tag fetched jobs)
and by the bulletin query builder (to offer role presets).
"""
from __future__ import annotations

import re

# 8 categories -> representative title keywords/phrases (lowercase).
CATEGORIES: dict[str, list[str]] = {
    "SOC & Blue Team": [
        "soc analyst", "security operations center", "security operations",
        "cybersecurity analyst", "information security analyst",
        "security monitoring", "incident response analyst",
        "threat monitoring", "detection & response", "detection and response",
        "detection engineer", "security specialist", "it security specialist",
        "mssp", "managed security", "blue team", "siem",
    ],
    "Vulnerability & Offensive": [
        "penetration tester", "pen tester", "pentester",
        "vulnerability assessment", "vulnerability management",
        "vulnerability analyst", "ethical hacker",
        "application security analyst", "appsec analyst",
        "security researcher", "red team", "purple team",
        "security assessment",
    ],
    "GRC & Audit": [
        "grc", "governance, risk", "governance risk", "compliance analyst",
        "it auditor", "cyber risk", "security risk analyst",
        "information security risk", "security compliance",
        "third-party risk", "tprm", "policy and compliance",
        "risk and compliance", "risk & compliance", "audit",
    ],
    "IAM": [
        "iam analyst", "identity & access", "identity and access",
        "access control", "directory services", "identity security",
        "privileged access", "pam ", "iam engineer", "identity engineer",
    ],
    "Infra, Cloud & Network Security": [
        "cloud security", "network security", "firewall",
        "security infrastructure", "systems security", "infrastructure security",
        "cloud security engineer", "network security analyst",
    ],
    "Security Engineering & AppDev": [
        "application security engineer", "product security",
        "cybersecurity engineer", "security software engineer",
        "security engineer", "devsecops", "appsec engineer",
    ],
    "Threat Intel, Forensics & DFIR": [
        "threat intelligence", "cti analyst", "digital forensics",
        "dfir", "forensic", "cybercrime", "threat hunter", "threat hunting",
        "incident response",
    ],
    "Feeder & Bridge": [
        "security administrator", "security analyst", "noc",
        "security technician", "cybersecurity technician",
        "security support", "security rotational", "security associate",
        "systems administrator",
    ],
}

# Broad "is this cyber at all" keywords (any category hit also qualifies).
# NOTE: these are matched as WHOLE WORDS/PHRASES (see _contains), so short
# tokens like "soc" or "iam" won't match inside "aSSOCiate" or "mIAMi".
CORE_KEYWORDS = [
    "cybersecurity", "cyber security", "information security", "infosec",
    "security analyst", "soc", "soc analyst", "vulnerability", "appsec",
    "application security", "iam", "identity and access", "grc",
    "penetration tester", "penetration testing", "threat intelligence",
    "threat hunting", "threat detection", "forensics", "digital forensics",
    "incident response", "devsecops", "security engineer",
    "security operations", "malware", "siem", "red team", "blue team",
    "purple team", "cloud security", "network security",
    "security compliance", "security risk", "security administrator",
    "security specialist", "security consultant", "security architect",
    "security researcher", "security operations center", "ethical hacker",
    "pentester", "pen tester", "security governance",
]

# Titles that are general software/other engineering and must NOT be treated
# as cybersecurity even if a stray token matches. If a title contains one of
# these AND no strong cyber phrase, it is excluded.
NON_CYBER_MARKERS = [
    "software engineer", "software developer", "full stack", "fullstack",
    "front end", "frontend", "back end", "backend", "web developer",
    "mobile", "ios ", "android", "data engineer", "data scientist",
    "data analyst", "machine learning", "ml engineer", "ai engineer",
    "devops engineer", "platform engineer", "qa engineer",
    "quality assurance", "solutions engineer", "sales engineer",
    "embedded software", "embedded sw", "firmware", "game", "ui engineer",
    "ux ", "business analyst", "product manager", "project manager",
    "marketing", "designer", "accountant", "controller", "recruiter",
    "mechanical", "electrical engineer", "civil engineer", "biomedical",
]

# Strong cyber phrases: if present, the title is cyber regardless of any
# non-cyber marker (e.g. "Security Software Engineer", "Product Security
# Engineer", "Application Security Engineer" are genuinely cyber).
STRONG_CYBER = [
    "cybersecurity", "cyber security", "information security", "infosec",
    "soc analyst", "security operations center", "security operations",
    "incident response", "threat intelligence", "threat hunting",
    "threat detection", "penetration test", "pentest", "pen tester",
    "ethical hacker", "vulnerability", "appsec", "application security",
    "product security", "security engineer", "devsecops", "malware",
    "digital forensics", "forensics", "siem", "red team", "blue team",
    "purple team", "cloud security", "network security", "security analyst",
    "iam analyst", "identity and access", "privileged access",
    "security architect", "security researcher", "security specialist",
    "security administrator", "security compliance", "security risk",
    "grc analyst", "security consultant", "detection and response",
    "detection engineer", "security governance", "it auditor", "cyber risk",
    "security software engineer", "zero trust", "identity security",
    "access control", "security assessment", "security monitoring",
]

# Seniority modifiers that mark an entry-level / early-career role.
# Matched as whole words (punctuation stripped), so "i" matches "Analyst I".
ENTRY_MODIFIERS = [
    "junior", "jr", "associate", "entry", "entry level", "early career",
    "graduate", "grad", "new grad", "intern", "internship", "level 1",
    "level i", "tier 1", "tier i", "l1", "i", "trainee", "apprentice",
    "campus", "university",
]

# Senior markers used to exclude when entry-only is requested.
SENIOR_MARKERS = [
    "senior", "sr", "staff", "principal", "lead", "manager", "director",
    "vp", "head", "architect", "ii", "iii", "iv", "level 2", "level 3",
    "level ii", "level iii", "distinguished", "expert", "chief", "mid",
]

_WORDY = re.compile(r"[^a-z0-9]+")


def _norm(text: str) -> str:
    # Space-padded, single-spaced, lowercased -> enables whole-phrase matching
    # by searching for " phrase " (so "soc" won't match inside "associate").
    return " " + _WORDY.sub(" ", (text or "").lower()).strip() + " "


def _contains(norm_text: str, phrase: str) -> bool:
    """Whole-word/phrase containment on a space-padded normalized string."""
    p = _WORDY.sub(" ", phrase.lower()).strip()
    return f" {p} " in norm_text


def _has_any(norm_text: str, phrases: list[str]) -> bool:
    return any(_contains(norm_text, p) for p in phrases)


def categorize(title: str) -> str | None:
    """Return the best-matching cyber category for a title, or None.

    Uses whole-phrase matching and prefers the most specific (longest) match.
    """
    t = _norm(title)
    best: str | None = None
    best_len = 0
    for cat, phrases in CATEGORIES.items():
        for p in phrases:
            if _contains(t, p) and len(p) > best_len:
                best, best_len = cat, len(p)
    return best


def is_cyber(title: str) -> bool:
    """True only for genuine cybersecurity roles.

    A title qualifies if it contains a strong cyber phrase. If it only matches
    a weak/generic signal AND looks like general software/other engineering,
    it is excluded so SWE roles don't leak in.
    """
    t = _norm(title)
    has_strong = _has_any(t, STRONG_CYBER)
    if has_strong:
        return True
    # No strong cyber phrase: reject anything that looks like general SWE/other.
    if _has_any(t, NON_CYBER_MARKERS):
        return False
    # Otherwise fall back to the broader core keywords (whole-word).
    return _has_any(t, CORE_KEYWORDS) or categorize(title) is not None


def is_entry_level(title: str) -> bool:
    """True if the title looks entry-level / early-career.

    A title with an explicit entry modifier qualifies. A title with NO
    seniority markers at all is treated as potentially entry-level too, so we
    don't over-filter roles that simply omit a level.
    """
    t = _norm(title)
    if _has_any(t, ENTRY_MODIFIERS):
        return True
    if _has_any(t, SENIOR_MARKERS):
        return False
    return True  # no level stated -> keep it


def seniority(title: str) -> str:
    t = _norm(title)
    if _has_any(t, ENTRY_MODIFIERS):
        return "entry"
    if _has_any(t, SENIOR_MARKERS):
        return "senior"
    return "unspecified"
