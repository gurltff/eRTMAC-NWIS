"""Creates data/samples/drilling_report_sample.pdf – a SAMPLE well completion report
to demo the document extraction page. Run:  python -m scripts.make_sample_pdf"""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

OUT = Path(__file__).resolve().parents[2] / "data" / "samples" / "drilling_report_sample.pdf"

BODY = [
    ("h", "SAMPLE WELL COMPLETION REPORT – for demo only"),
    ("p", "Well name: HGJ-77"),
    ("p", "Field: Hugrijan"),
    ("p", "Operator: Oil India Limited"),
    ("p", "Rig: E-1400-7"),
    ("p", "Report date: 2019-03-14"),
    ("p", "Latitude: 27.4612  Longitude: 95.3488"),
    ("p", "Total depth: 3620 m"),
    ("h2", "Formation tops"),
    ("p", "Dhekiajuli top: 240 m"),
    ("p", "Namsang top: 1120 m"),
    ("p", "Girujan Clay top: 1540 m"),
    ("p", "Tipam Sandstone top: 2105 m"),
    ("p", "Barail top: 2560 m"),
    ("p", "Kopili Shale top: 3140 m"),
    ("p", "Sylhet Limestone top: 3390 m"),
    ("h2", "Drilling history and problems"),
    ("p", "While drilling the 12 1/4 in hole at 1685 m in Girujan Clay the string got stuck during a connection with 45 t overpull. "
          "Cause: swelling clay closing the hole. Jarred down 30 times and spotted a pipe-freeing pill, free after 14 hrs. "
          "Lesson: back-ream every stand and keep KCl above 7% through Girujan."),
    ("p", "Partial losses of 25 bbl/hr were observed at 2190 m in Tipam Sandstone due to depleted sands. "
          "Pumped 60 bbl LCM pill and reduced flow rate, losses cured after 6 hrs."),
    ("p", "At 3172 m in Kopili Shale a pit gain of 12 bbl was seen and flow check was positive. "
          "Shut in the well and circulated out the kick with the Driller's method, raised mud weight from 11.4 to 11.9 ppg. "
          "Lesson: raise mud weight to 11.9 ppg before entering Kopili."),
    ("p", "Poor bond was seen on the CBL across Tipam on the 9 5/8 in casing due to mud channelling. Squeezed 40 bbl slurry."),
    ("p", "Rig repair: top drive breakdown at 2890 m, 9 hrs NPT."),
    ("h2", "Lessons learnt"),
    ("p", "Lessons learnt: pre-treat mud with LCM 50 m above the Tipam top and use a lightweight lead slurry across Tipam."),
]


def main():
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, title="Sample well completion report HGJ-77")
    story = []
    for kind, text in BODY:
        style = {"h": styles["Title"], "h2": styles["Heading2"], "p": styles["BodyText"]}[kind]
        story += [Paragraph(text, style), Spacer(1, 4)]
    story.append(Table([["This document is SAMPLE data generated for the eRTMAC NWIS prototype."]]))
    doc.build(story)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
