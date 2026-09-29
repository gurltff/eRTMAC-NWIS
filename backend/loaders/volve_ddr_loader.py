"""Equinor Volve daily drilling reports (WITSML 1.4 drillReport XML).

Real data: https://www.equinor.com/energy/volve-data-sharing – copy the DDR
XML files into data/raw/volve_ddr/. Without them the synthetic sample
data/samples/volve_ddr_sample.xml (same structure) is parsed.

Each <activity> is classified with the keyword rules in
app/services/event_classifier.py. Activities whose proprietaryCode starts with
'interruption' or whose state is 'fail' are treated as problem events.
For the demo, Volve wells are relocated onto Assam coordinates by the seed
script (stated clearly in the README and the UI).
"""
import xml.etree.ElementTree as ET
from pathlib import Path

from app.config import RAW_DIR, SAMPLES_DIR
from app.services.event_classifier import action_sentences, classify, find_hours, severity_from

NS = {"w": "http://www.witsml.org/schemas/1series"}

# Approximate Volve formation tops (m MD) used to tag events with a formation.
VOLVE_TOPS = [
    ("Nordland Gp", 0), ("Utsira Fm", 700), ("Hordaland Gp", 1050), ("Rogaland Gp", 2200),
    ("Shetland Gp", 2450), ("Cromer Knoll Gp", 2900), ("Draupne Fm", 3000), ("Heather Fm", 3080),
    ("Hugin Fm", 3150), ("Sleipner Fm", 3300), ("Skagerrak Fm", 3400),
]


def formation_at(md: float | None) -> str | None:
    if md is None:
        return None
    name = None
    for fm, top in VOLVE_TOPS:
        if md >= top:
            name = fm
    return name


def _text(el, path):
    found = el.find(path, NS)
    return found.text.strip() if found is not None and found.text else None


def parse_file(path: Path) -> list[dict]:
    root = ET.parse(path).getroot()
    events = []
    for rep in root.findall("w:drillReport", NS):
        well = _text(rep, "w:nameWell") or path.stem
        for act in rep.findall("w:activity", NS):
            code = (_text(act, "w:proprietaryCode") or "").lower()
            state = (_text(act, "w:state") or "").lower()
            comments = _text(act, "w:comments") or ""
            md_text = _text(act, "w:md")
            md = float(md_text) if md_text else None
            if not (code.startswith("interruption") or state == "fail"):
                continue
            etype = classify(comments) or classify(code) or "NPT"
            lesson = None
            if "lesson:" in comments.lower():
                lesson = comments[comments.lower().index("lesson:") + 7:].strip()
            cause = None
            if "cause:" in comments.lower():
                cause = comments[comments.lower().index("cause:") + 6:].split(".")[0].strip()
            hours = find_hours(comments)
            events.append({
                "well": well,
                "event_type": etype,
                "depth_m": md,
                "formation": formation_at(md),
                "event_date": (_text(act, "w:dTimStart") or "")[:10],
                "description": comments.split(". Lesson")[0],
                "cause": cause,
                "action_taken": action_sentences(comments.split("Lesson")[0]),
                "lesson": lesson,
                "npt_hours": hours,
                "severity": severity_from(etype, hours),
                "source": f"Volve DDR format ({path.name})",
            })
    return events


def load_events() -> tuple[list[dict], bool]:
    raw_dir = RAW_DIR / "volve_ddr"
    files = sorted(raw_dir.glob("*.xml")) if raw_dir.exists() else []
    real = bool(files)
    if not files:
        files = [SAMPLES_DIR / "volve_ddr_sample.xml"]
    events = []
    for f in files:
        try:
            events.extend(parse_file(f))
        except ET.ParseError:
            continue
    return events, real


if __name__ == "__main__":
    evs, real = load_events()
    print(f"{len(evs)} events ({'real Volve files' if real else 'sample file'})")
    for e in evs:
        print(e["event_type"], e["depth_m"], e["formation"], "-", e["description"][:70])
