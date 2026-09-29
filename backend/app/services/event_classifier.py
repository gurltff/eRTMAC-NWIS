"""Keyword rules that turn free-text drilling report lines into event types.

Used by the Volve DDR loader and by the rule-based document extractor.
Order matters: the first matching type wins for a sentence.
"""
import re

EVENT_TYPES = ["KICK", "STUCK_PIPE", "MUD_LOSS", "CEMENTING", "TORQUE_SPIKE", "FISHING", "NPT"]

EVENT_LABELS = {
    "MUD_LOSS": "Mud loss",
    "KICK": "Kick / influx",
    "STUCK_PIPE": "Stuck pipe",
    "TORQUE_SPIKE": "Torque spike",
    "CEMENTING": "Cementing problem",
    "FISHING": "Fishing job",
    "NPT": "Non-productive time",
}

_RULES = [
    ("KICK", r"\bkick\b|influx|pit gain|well control|flow check positive|shut[- ]in (the )?well|gas cut mud"),
    ("STUCK_PIPE", r"stuck|pack(ed)?[- ]off|differential(ly)? stick|overpull|tight hole|jarr(ed|ing)"),
    ("CEMENTING", r"cement(ing)? (job|problem|failure)|top of cement|squeeze|channel(l)?ing|micro[- ]?annul|poor bond"),
    ("MUD_LOSS", r"\blosses\b|\bloss(es)? of (mud|returns|circulation)|lost circulation|lost returns|mud loss|partial loss|total loss"),
    ("TORQUE_SPIKE", r"torque spike|erratic torque|high torque|torque (increased|fluctuat)|stick[- ]slip"),
    ("FISHING", r"\bfish(ing)?\b|twist[- ]?off|junk in hole|parted string"),
    ("NPT", r"\bNPT\b|waiting on|rig repair|breakdown|downtime|non[- ]productive"),
]
_COMPILED = [(t, re.compile(p, re.I)) for t, p in _RULES]


def classify(text: str) -> str | None:
    for event_type, rx in _COMPILED:
        if rx.search(text or ""):
            return event_type
    return None


def classify_all(text: str) -> list[str]:
    return [t for t, rx in _COMPILED if rx.search(text or "")]


_DEPTH_RX = re.compile(r"(\d{3,5}(?:\.\d+)?)\s*(m|mtr|meters|metres|ft|feet)\b(?:\s*MD)?", re.I)


def find_depth_m(text: str) -> float | None:
    """First depth mentioned in the text, converted to metres."""
    m = _DEPTH_RX.search(text or "")
    if not m:
        return None
    val = float(m.group(1))
    return round(val * 0.3048, 1) if m.group(2).lower() in ("ft", "feet") else val


def find_hours(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(hrs|hours|hr|h)\b", text or "", re.I)
    return float(m.group(1)) if m else None


def severity_from(event_type: str, hours: float | None) -> str:
    if event_type in ("KICK",) or (hours or 0) >= 12:
        return "high"
    if (hours or 0) >= 4 or event_type in ("STUCK_PIPE", "FISHING"):
        return "medium"
    return "low"


_ACTION_RX = re.compile(r"\b(pumped|spotted|reduced|raised|increased|jarred|circulated|pulled|reamed|backreamed|"
                        r"shut in|killed|squeezed|set|ran|added|switched|worked|washed|freed|cured)\b", re.I)


def action_sentences(text: str) -> str | None:
    """Sentences that describe what the crew did (used as 'action taken')."""
    sents = [s.strip() for s in re.split(r"(?<=[.;])\s+", text or "") if s.strip()]
    acts = [s for s in sents if _ACTION_RX.search(s) and not s.lower().startswith(("lesson", "cause"))]
    return " ".join(acts) or None
