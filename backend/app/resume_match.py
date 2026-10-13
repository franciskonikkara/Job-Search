"""Rule-based resume/JD matching and ATS analysis (no external API).

Given a master resume (plain text) and a job description, this:
  - extracts skills/keywords from the JD (a curated cyber/tech skill lexicon
    plus notable capitalized terms),
  - checks which appear in the resume,
  - computes a 0-100 match score with component breakdowns,
  - lists missing keywords the user could add IF they truly have them,
  - suggests which of the user's existing resume bullets are most relevant to
    surface first (reordering only — it never invents experience).

Everything here reorganizes/surfaces the user's real content. It must not
fabricate skills. The UI reinforces this: missing keywords are shown as
"do you actually have these?" prompts, not auto-inserted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# A curated lexicon of cyber/tech skills, tools, frameworks, and concepts.
# Multi-word entries are matched as phrases. Case-insensitive.
SKILL_LEXICON = [
    # Security domains
    "incident response", "threat intelligence", "threat hunting",
    "vulnerability management", "penetration testing", "red team",
    "blue team", "purple team", "security operations", "soc", "siem",
    "soar", "dfir", "digital forensics", "malware analysis",
    "reverse engineering", "endpoint detection", "edr", "xdr", "ids", "ips",
    "firewall", "zero trust", "identity and access management", "iam",
    "pki", "encryption", "cryptography", "data loss prevention", "dlp",
    "grc", "governance", "risk", "compliance", "audit", "security awareness",
    "application security", "appsec", "devsecops", "secure coding",
    "owasp", "sast", "dast", "container security", "cloud security",
    "network security", "cloud posture", "cspm", "casb", "waf",
    "phishing", "social engineering", "vulnerability assessment",
    # Frameworks / standards
    "nist", "nist 800-53", "nist csf", "iso 27001", "soc 2", "pci dss",
    "hipaa", "gdpr", "fedramp", "cis", "mitre att&ck", "cmmc",
    # Tools / platforms
    "splunk", "qradar", "sentinel", "microsoft sentinel", "crowdstrike",
    "carbon black", "sentinelone", "wireshark", "nmap", "metasploit",
    "burp suite", "nessus", "qualys", "tenable", "rapid7", "snort",
    "suricata", "elastic", "elk", "kibana", "wazuh", "okta", "duo",
    "cyberark", "hashicorp vault", "palo alto", "fortinet", "cisco",
    # Cloud / infra
    "aws", "azure", "gcp", "google cloud", "kubernetes", "docker",
    "terraform", "ansible", "linux", "windows server", "active directory",
    "vmware", "ec2", "s3", "iam roles", "cloudtrail", "guardduty",
    "security hub", "kms", "lambda", "vpc",
    # Programming / scripting
    "python", "powershell", "bash", "go", "golang", "java", "javascript",
    "sql", "regex", "rest api", "git", "ci/cd", "jenkins",
    # Certs
    "security+", "comptia security+", "cissp", "cism", "ceh", "oscp",
    "gcih", "gsec", "gcia", "ccsp", "az-500", "aws security", "network+",
    "cysa+", "pentest+",
    # General analyst skills
    "log analysis", "packet analysis", "network monitoring",
    "vulnerability scanning", "ticketing", "documentation",
    "root cause analysis", "security controls", "access control",
]

# Normalize a few aliases so resume/JD phrasing lines up.
_ALIASES = {
    "comptia security+": "security+",
    "microsoft sentinel": "sentinel",
    "google cloud": "gcp",
    "golang": "go",
    "elk": "elastic",
}

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#./&-]*")


@dataclass
class MatchResult:
    overall: int
    skills_match: int
    keyword_coverage: int
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    jd_skills: list[str] = field(default_factory=list)
    suggested_bullets: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "overall": self.overall,
            "skills_match": self.skills_match,
            "keyword_coverage": self.keyword_coverage,
            "matched_skills": self.matched_skills,
            "missing_skills": self.missing_skills,
            "jd_skills": self.jd_skills,
            "suggested_bullets": self.suggested_bullets,
            "notes": self.notes,
        }


def _canon(skill: str) -> str:
    s = skill.lower().strip()
    return _ALIASES.get(s, s)


def _present(skill: str, text_lc: str) -> bool:
    """Whole-phrase presence check that tolerates word boundaries."""
    s = _canon(skill)
    # Escape regex special chars but keep +/# which matter for skill names.
    pattern = re.escape(s)
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text_lc) is not None


def extract_jd_skills(jd: str) -> list[str]:
    """Skills from the lexicon that appear in the JD, de-duplicated (canon)."""
    jd_lc = jd.lower()
    found: list[str] = []
    seen: set[str] = set()
    for skill in SKILL_LEXICON:
        c = _canon(skill)
        if c in seen:
            continue
        if _present(skill, jd_lc):
            found.append(c)
            seen.add(c)
    return found


def _split_bullets(resume: str) -> list[str]:
    lines = [ln.strip(" \t-•*") for ln in resume.splitlines()]
    return [ln for ln in lines if len(ln) >= 25]


def _rank_bullets(bullets: list[str], jd_skills: list[str], limit=8) -> list[str]:
    """Rank the user's existing bullets by how many JD skills they mention."""
    scored = []
    for b in bullets:
        b_lc = b.lower()
        hits = sum(1 for s in jd_skills if _present(s, b_lc))
        if hits > 0:
            scored.append((hits, b))
    scored.sort(key=lambda x: (-x[0], len(x[1])))
    return [b for _, b in scored[:limit]]


def analyze(resume: str, jd: str) -> MatchResult:
    resume = resume or ""
    jd = jd or ""
    resume_lc = resume.lower()

    jd_skills = extract_jd_skills(jd)
    matched = [s for s in jd_skills if _present(s, resume_lc)]
    missing = [s for s in jd_skills if s not in matched]

    skills_match = (
        round(len(matched) / len(jd_skills) * 100) if jd_skills else 0
    )

    # Keyword coverage: broader token overlap between JD and resume (captures
    # non-lexicon domain words the JD emphasises).
    jd_tokens = {
        w.lower() for w in _WORD.findall(jd)
        if len(w) >= 4 and not w.isdigit()
    }
    resume_tokens = {w.lower() for w in _WORD.findall(resume)}
    if jd_tokens:
        overlap = len(jd_tokens & resume_tokens) / len(jd_tokens)
        keyword_coverage = round(overlap * 100)
    else:
        keyword_coverage = 0

    # Overall: weight the curated-skill match more than raw token overlap.
    overall = round(0.65 * skills_match + 0.35 * keyword_coverage)

    suggested = _rank_bullets(_split_bullets(resume), jd_skills)

    notes = []
    if not jd_skills:
        notes.append(
            "No known skills detected in the job description. Paste the full "
            "JD text for a better analysis."
        )
    if missing:
        notes.append(
            "Missing keywords are suggestions only. Add them to your resume "
            "ONLY if you genuinely have that experience — never fabricate."
        )
    if not suggested and resume:
        notes.append(
            "No resume bullets strongly matched the JD skills. Consider "
            "rephrasing your real experience using the JD's terminology."
        )

    return MatchResult(
        overall=overall,
        skills_match=skills_match,
        keyword_coverage=keyword_coverage,
        matched_skills=matched,
        missing_skills=missing,
        jd_skills=jd_skills,
        suggested_bullets=suggested,
        notes=notes,
    )


# --- Iterative tailoring ---------------------------------------------------

@dataclass
class TailoredResume:
    tailored_resume: str          # the rewritten, ATS-optimized resume text
    matched_keywords: list[str]   # JD skills already backed by the resume
    injected_keywords: list[str]  # matched skills woven into summary/competencies
    gap_keywords: list[str]       # JD skills NOT in the resume (add if genuine)
    before_score: int
    after_score: int
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "tailored_resume": self.tailored_resume,
            "matched_keywords": self.matched_keywords,
            "injected_keywords": self.injected_keywords,
            "gap_keywords": self.gap_keywords,
            "before_score": self.before_score,
            "after_score": self.after_score,
            "notes": self.notes,
        }


def _title_case_skill(s: str) -> str:
    # Keep known acronyms upper; title-case the rest.
    acronyms = {
        "soc", "siem", "soar", "edr", "xdr", "ids", "ips", "iam", "pki",
        "dlp", "grc", "dfir", "aws", "gcp", "sast", "dast", "waf", "casb",
        "cspm", "nist", "iso", "pci", "dss", "hipaa", "gdpr", "fedramp",
        "cis", "cmmc", "sql", "api", "ci/cd", "vpc", "kms", "cissp", "cism",
        "ceh", "oscp", "gcih", "gsec", "gcia", "ccsp", "cysa+", "pentest+",
        "network+", "security+", "az-500", "mitre att&ck", "owasp",
    }
    if s in acronyms:
        return s.upper() if "+" not in s and "att&ck" not in s else s.title()
    return " ".join(
        w.upper() if w in acronyms else w.capitalize() for w in s.split()
    )


def tailor(resume: str, jd: str) -> TailoredResume:
    """Rewrite the resume to naturally weave in the JD's keywords for ATS.

    Strategy (no fabrication):
      1. Analyze the resume vs JD.
      2. Build a JD-targeted PROFESSIONAL SUMMARY that names the target role
         and the keywords the resume ALREADY supports.
      3. Build a CORE COMPETENCIES / SKILLS block listing the matched skills
         (great for ATS keyword scanning) — only skills the resume backs up.
      4. Keep the user's original resume body, with the most JD-relevant
         bullets surfaced at the top of an "Most Relevant Experience" section.
      5. List JD keywords NOT found in the resume as a clearly-separated
         "Consider adding (only if you have this)" block — NOT woven into
         experience, so nothing is fabricated.
    """
    resume = (resume or "").strip()
    jd = (jd or "").strip()
    base = analyze(resume, jd)

    # Try to detect the target role from the JD's first non-empty line.
    role = ""
    for ln in jd.splitlines():
        ln = ln.strip()
        if ln:
            role = re.sub(r"[^A-Za-z0-9 /,-]", "", ln)[:80].strip()
            break

    matched_display = [_title_case_skill(s) for s in base.matched_skills]
    gap_display = [_title_case_skill(s) for s in base.missing_skills]

    # 1) Summary — names the role + weaves in matched keywords naturally.
    summary_bits = ", ".join(base.matched_skills[:8]) if base.matched_skills else ""
    summary = "PROFESSIONAL SUMMARY\n"
    role_phrase = f" for {role}" if role else ""
    if summary_bits:
        summary += (
            f"Cybersecurity professional targeting{role_phrase} with hands-on "
            f"exposure to {summary_bits}. Applies these skills to strengthen "
            f"security operations, reduce risk, and support detection and "
            f"response."
        )
    else:
        summary += (
            f"Cybersecurity professional targeting{role_phrase}, eager to apply "
            f"a growing security skill set to real-world problems."
        )

    # 2) Core competencies block (pure keyword surface for ATS).
    competencies = ""
    if matched_display:
        competencies = "CORE COMPETENCIES\n" + " • ".join(matched_display)

    # 3) Most relevant experience (reordered real bullets).
    relevant = ""
    if base.suggested_bullets:
        relevant = "MOST RELEVANT EXPERIENCE\n" + "\n".join(
            f"- {b}" for b in base.suggested_bullets
        )

    # 4) Keep the original resume as the full detail section.
    original = f"FULL RESUME\n{resume}" if resume else ""

    # 5) Gap block — explicitly separate, never woven into experience.
    gap = ""
    if gap_display:
        gap = (
            "CONSIDER ADDING (only if you genuinely have this experience)\n"
            + ", ".join(gap_display)
        )

    parts = [p for p in [summary, competencies, relevant, original, gap] if p]
    tailored = "\n\n".join(parts)

    # After-score: the tailored resume now contains the matched skills in the
    # summary + competencies, so re-analyzing reflects the ATS improvement.
    after = analyze(tailored, jd)

    notes = [
        "Keywords you already back up were woven into the summary and a Core "
        "Competencies block to raise your ATS score.",
        "The 'Consider adding' list is kept separate on purpose — add those to "
        "your experience ONLY if they are genuinely true. Never fabricate.",
        "Review and edit the wording so it sounds like you before sending.",
    ]

    return TailoredResume(
        tailored_resume=tailored,
        matched_keywords=matched_display,
        injected_keywords=matched_display,
        gap_keywords=gap_display,
        before_score=base.overall,
        after_score=after.overall,
        notes=notes,
    )
