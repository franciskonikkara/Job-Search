"""Template-based outreach drafting (no external API).

Generates first drafts the user reviews and sends themselves — recruiter
emails, referral requests, follow-ups, LinkedIn connection notes/messages, and
a cover letter. Personalized with the user's and job's details. Nothing is
sent automatically; the app only produces copy-to-clipboard text.

These are templates filled with real, user-provided values. They do not invent
experience or credentials.
"""
from __future__ import annotations

from dataclasses import dataclass

# Supported draft kinds.
KINDS = [
    "recruiter_email",
    "referral_request",
    "follow_up",
    "linkedin_connection",
    "linkedin_message",
    "cover_letter",
]


@dataclass
class OutreachInput:
    kind: str
    company: str = ""
    role: str = ""
    contact_name: str = ""
    your_name: str = ""
    your_background: str = ""  # e.g. "Master's in Cybersecurity at UMD"
    highlight: str = ""        # one concrete, real accomplishment/skill
    shared_context: str = ""   # alumni, mutual connection, event, etc.


def _first_name(name: str) -> str:
    name = (name or "").strip()
    return name.split()[0] if name else "there"


def _clean(v: str, fallback: str) -> str:
    v = (v or "").strip()
    return v or fallback


def _recruiter_email(i: OutreachInput) -> tuple[str, str]:
    company = _clean(i.company, "your company")
    role = _clean(i.role, "the open role")
    bg = _clean(i.your_background, "a cybersecurity professional")
    hl = i.highlight.strip()
    subject = f"Interest in {role} at {company}"
    body = (
        f"Hi {_first_name(i.contact_name)},\n\n"
        f"I'm {_clean(i.your_name, 'a candidate')}, {bg}. I recently applied "
        f"for the {role} position at {company} and wanted to introduce myself "
        f"directly.\n\n"
    )
    if hl:
        body += f"A bit about my relevant background: {hl}\n\n"
    body += (
        f"I'm very interested in {company}'s work and would welcome the chance "
        f"to discuss how I can contribute to the team. I'd be glad to share "
        f"more about my experience at your convenience.\n\n"
        f"Thank you for your time and consideration.\n\n"
        f"Best regards,\n{_clean(i.your_name, '')}"
    )
    return subject, body


def _referral_request(i: OutreachInput) -> tuple[str, str]:
    company = _clean(i.company, "your company")
    role = _clean(i.role, "an open role")
    subject = f"Quick referral question — {role} at {company}"
    ctx = f" We {i.shared_context.strip()}." if i.shared_context.strip() else ""
    body = (
        f"Hi {_first_name(i.contact_name)},\n\n"
        f"I hope you're doing well.{ctx} I'm reaching out because I'm applying "
        f"for the {role} position at {company} and saw that you work there.\n\n"
    )
    if i.highlight.strip():
        body += f"For context on my fit: {i.highlight.strip()}\n\n"
    body += (
        f"If you feel comfortable, would you be open to referring me or sharing "
        f"any advice about the team and hiring process? I completely understand "
        f"if not, and I appreciate any insight you can offer.\n\n"
        f"Thanks so much,\n{_clean(i.your_name, '')}"
    )
    return subject, body


def _follow_up(i: OutreachInput) -> tuple[str, str]:
    company = _clean(i.company, "your company")
    role = _clean(i.role, "the role")
    subject = f"Following up — {role} at {company}"
    body = (
        f"Hi {_first_name(i.contact_name)},\n\n"
        f"I wanted to follow up on my application for the {role} position at "
        f"{company}. I remain very interested in the opportunity and would "
        f"appreciate any updates you're able to share.\n\n"
        f"Please let me know if there's anything else you need from me. Thank "
        f"you again for your time.\n\n"
        f"Best regards,\n{_clean(i.your_name, '')}"
    )
    return subject, body


def _linkedin_connection(i: OutreachInput) -> tuple[str, str]:
    company = _clean(i.company, "your company")
    bg = _clean(i.your_background, "pursuing a career in cybersecurity")
    ctx = f" {i.shared_context.strip()}" if i.shared_context.strip() else ""
    # LinkedIn connection notes are capped ~300 chars; keep it short.
    body = (
        f"Hi {_first_name(i.contact_name)}, I'm {bg} and interested in "
        f"cybersecurity opportunities at {company}.{ctx} I'd love to connect "
        f"and learn from your experience there."
    )
    return "LinkedIn connection note", body[:300]


def _linkedin_message(i: OutreachInput) -> tuple[str, str]:
    company = _clean(i.company, "your company")
    role = _clean(i.role, "cybersecurity roles")
    body = (
        f"Hi {_first_name(i.contact_name)}, thanks for connecting. I'm "
        f"currently exploring {role} at {company}"
    )
    if i.highlight.strip():
        body += f", and my background includes {i.highlight.strip()}"
    body += (
        f". I'd really appreciate any advice on the team or hiring process, or "
        f"a referral if you think I'd be a fit. Thanks for your time!"
    )
    return "LinkedIn message", body


def _cover_letter(i: OutreachInput) -> tuple[str, str]:
    company = _clean(i.company, "your company")
    role = _clean(i.role, "the position")
    bg = _clean(i.your_background, "my background in cybersecurity")
    subject = f"Cover letter — {role} at {company}"
    body = (
        f"Dear {_clean(i.contact_name, 'Hiring Manager')},\n\n"
        f"I am writing to express my interest in the {role} position at "
        f"{company}. With {bg}, I am eager to contribute to your team.\n\n"
    )
    if i.highlight.strip():
        body += (
            f"In particular, {i.highlight.strip()}. I believe this experience "
            f"aligns well with what {company} is looking for in this role.\n\n"
        )
    body += (
        f"I am especially drawn to {company} and the opportunity to grow while "
        f"making a meaningful contribution. I would welcome the chance to "
        f"discuss how my skills fit your needs.\n\n"
        f"Thank you for your consideration.\n\n"
        f"Sincerely,\n{_clean(i.your_name, '')}"
    )
    return subject, body


_BUILDERS = {
    "recruiter_email": _recruiter_email,
    "referral_request": _referral_request,
    "follow_up": _follow_up,
    "linkedin_connection": _linkedin_connection,
    "linkedin_message": _linkedin_message,
    "cover_letter": _cover_letter,
}


@dataclass
class OutreachDraft:
    kind: str
    subject: str
    body: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "subject": self.subject, "body": self.body}


def generate(inp: OutreachInput) -> OutreachDraft:
    builder = _BUILDERS.get(inp.kind)
    if builder is None:
        raise ValueError(f"Unknown outreach kind: {inp.kind}")
    subject, body = builder(inp)
    return OutreachDraft(kind=inp.kind, subject=subject, body=body)
