"""Printable storyboard of the scenario "shopping" (static/scenarios.js) for the station "Compare" of the
interactive presentation: an A3 sheet with ten frames, captions, and lines for attendees' notes on where the
design helps or hinders. Further design variants (e.g. "action") can be added to VARIANTS, one sheet each.

Requires a running server (default http://localhost:8027) and google-chrome.
Usage: python3 scripts/storyboards.py [out-dir]   (default ../chiir27-dialog-first-storyboards)
"""

import html
import os
import subprocess
import sys
from pathlib import Path

URL = os.environ.get("URL", "http://localhost:8027")
CHROME = os.environ.get("CHROME", "google-chrome")
VARIANTS = {
    "query": "Storyboard",
}
TASK = ("A student looks for a light laptop under €1,000 that is delivered tomorrow and has a long battery life, "
        "from a brand that offers good value; the student compares candidates and puts one into the cart.")

# The ten steps of the paper: (steps of the scenario replayed before the frame, title, caption; a dict gives
# captions per variant).
FRAMES = [
    (0, "Opening answer", "The dialog opens with an answer: all laptops, most recommended first, with facets and "
                          "example questions."),
    (2, "A vague question, clarified", "“Which brands offer the best value among lightweight laptops?” The "
                                       "system offers three readings, each an unambiguous question backed by a "
                                       "query; the chosen one becomes the student's turn."),
    (3, "Facet: 16 GB RAM", {
        "query": "The facet value refines the answer in place; the filter stays removable. No new turn.",
        "action": "The facet value is written as a new user turn; the earlier answer is minimized."}),
    (4, "Expand a brand", {
        "query": "Expanding Lumo shows its models within the table. No new turn.",
        "action": "Expanding Lumo is written as a new user turn as well."}),
    (5, "A new question", "Light laptops under €1,000, delivered tomorrow, with the longest battery life. The "
                          "earlier answers shrink to their interpretation."),
    (7, "Product page", "Clicking a laptop opens its page in place of the dialog; the input box stays. The circle "
                        "selects the Aero 13."),
    (11, "Collecting candidates", "Back in the list, the student selects the Lumo Air 13 and opens the Aero 14: it "
                                  "is attached to the question next to the two selected laptops."),
    (12, "Asking about the selection", "“Which of them is the lightest?” refers only to the attached laptops, which "
                                       "the user turn records; the delivery condition still holds."),
    (13, "A click becomes a question", "The click on the price of the Lumo Air 13 is written as the student's "
                                       "question and keeps the condition: offers delivered tomorrow."),
    (14, "Add to cart", "The cheapest offer delivered tomorrow goes into the (fake) cart; the way to the purchase "
                        "stays within the dialog."),
]

STYLE = """
@page { size: A3 landscape; margin: 10mm; }
* { box-sizing: border-box; }
body { margin: 0; font: 10pt/1.35 "Noto Sans", Verdana, sans-serif; color: #222; }
.sheet { height: 277mm; display: flex; flex-direction: column; page-break-after: always; }
.sheet:last-child { page-break-after: auto; }
header { display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 1.5pt solid #323232;
  padding-bottom: 3mm; margin-bottom: 4mm; }
h1 { font-size: 18pt; font-weight: 400; margin: 0; }
h1 b { font-weight: 600; }
.task { max-width: 230mm; color: #444; }
.grid { flex: 1; min-height: 0; display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); grid-template-rows: repeat(2, minmax(0, 1fr)); gap: 4mm; }
.frame { display: flex; flex-direction: column; min-height: 0; overflow: hidden; border: 0.5pt solid #bbb; padding: 2.5mm; }
.frame img { display: block; width: 100%; height: 76mm; object-fit: contain; object-position: center top; border: 0.5pt solid #ddd; }
.title { font-weight: 600; margin: 2mm 0 1mm; display: flex; gap: 2mm; align-items: center; }
.num { display: inline-flex; align-items: center; justify-content: center; width: 5.5mm; height: 5.5mm;
  border-radius: 50%; background: #323232; color: #fff; font-size: 8.5pt; }
.caption { font-size: 8.5pt; line-height: 1.3; color: #333; }
.notes { margin-top: auto; padding-top: 2mm; font-size: 8.5pt; color: #777; }
.notes div { border-bottom: 0.5pt solid #bbb; height: 6mm; padding-top: 1.5mm; }
"""


def shoot(out: Path, variant: str, until: int) -> Path:
    file = out / "frames" / f"{variant}-{until:02d}.png"
    file.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=900,1060",
                    "--force-device-scale-factor=2", "--virtual-time-budget=10000", f"--screenshot={file}",
                    f"{URL}/?scenario=shopping&until={until}&variant={variant}"],
                   check=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    return file


def sheet(out: Path, variant: str, label: str) -> str:
    frames = []
    for number, (until, title, caption) in enumerate(FRAMES, 1):
        image = shoot(out, variant, until).relative_to(out)
        text = caption[variant] if isinstance(caption, dict) else caption
        frames.append(f"""<div class="frame"><img src="{image}" alt="">
          <div class="title"><span class="num">{number}</span>{html.escape(title)}</div>
          <div class="caption">{html.escape(text)}</div>
          <div class="notes"><div>+ helps:</div><div>– hinders:</div></div></div>""")
    return f"""<section class="sheet"><header>
      <h1>Dialog-First product search · <b>{html.escape(label)}</b></h1>
      <div class="task"><b>Task.</b> {html.escape(TASK)}<br><b>Annotate</b> where the design helps (+) or hinders
      (–) compared with online shops you know. Which steps should be turns of the dialog, which only views?</div>
      </header><div class="grid">{"".join(frames)}</div></section>"""


def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    sheets = "".join(sheet(out, variant, label) for variant, label in VARIANTS.items())
    page = out / "storyboard.html"
    page.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Dialog-First storyboards</title>
      <style>{STYLE}</style></head><body>{sheets}</body></html>""", encoding="utf-8")
    pdf = out / "storyboard.pdf"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}",
                    page.resolve().as_uri()], check=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    print(pdf)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "../chiir27-dialog-first-storyboards").resolve())
