# Dialog-First product search

Prototype for the CHIIR'27 design paper "Dialog-First: Conversational Interfaces for Search in Databases".
It applies the Dialog-First principles to a fictional laptop
catalog: the dialog is the interface, and result tables, product cards, facets, and queries are embedded
into the answers.

- Backend: Python FastAPI, in-memory SQLite (`app/`)
- Frontend: vanilla HTML, CSS, JS (`static/`), in a plain, flat style
- Catalog: 64 laptops of 8 fictional brands and 6 shops, generated from a fixed seed (`app/catalog.py`);
  products are shown as neutral placeholder drawings (`/img/<id>.svg`)

> **Note on language understanding.** In a real Dialog-First application, a large language model interprets
> the user's questions: it translates them into query plans, recognizes vague questions, and proposes their
> readings. This prototype replaces the model with a small rule-based parser (`app/language.py`) for
> convenience: it runs offline without API keys or GPU, deploys as a single small container, answers
> instantly at no cost, and behaves deterministically, which keeps tests and the figures of the paper
> reproducible. The parser understands the questions of the shopping task and many variations, but not
> arbitrary free-form questions. The interaction design, which the paper is about, does not depend on how
> questions are interpreted: the parser and a language model produce the same query plans.

## Live demo

**Try it: <DEMO-URL>**

No installation is needed. A task to start with: find a light laptop under €1,000 that is delivered tomorrow
and has a long battery life, compare a few candidates, and put one into the (fake) cart. The demo runs the
`Dockerfile` below; to run the prototype on your own machine, see "Run locally".

## How it works

Every turn is answered from a query plan (`app/plan.py`: filters, sorting, grouping, metric). From a plan,
the server derives the SQL query (tab "Query"), the interpretation that opens each answer (P3), the
observations and follow-up questions, and the facets shown inside the answer (`app/language.py`).

- The dialog opens with a first answer: a welcome with a summary of the catalog, all laptops (most recommended
  first) with facets on the left, and example questions. Short typed questions refine this list.
  Lists are sorted by recommendation (rating weighted by the number of reviews) unless a question asks otherwise.
- Typed questions are parsed into plans by a small rule-based parser that stands in for a language model (see
  the note above); questions without reference to the catalog are answered with what can be asked (P2).
  Short follow-ups such as "only with 16 GB RAM" refine the previous answer.
- Vague questions such as "Which laptop is best for students?" have candidate readings, each a query plan with a
  weight for how likely it is meant (`language.readings`). If the most likely reading is likely enough, the
  answer states it ("I read “for travel” as …") and offers the other readings as follow-ups; otherwise the
  system offers the readings as candidates: each is already an executable query (its SQL is shown on request),
  verbalized as an unambiguous question, and choosing one poses that question as the user's turn.
- Facet values filter the answer in place: the answer is re-queried and replaced without a new turn; active
  filters are shown above the facets and can be removed.
- Clicks that pose a new query (price, follow-up question, "… more" in a group) send a plan;
  the server verbalizes it as the user's question (P4). Hovering shows that question in advance.
- The dialog is a tree: acting on an earlier answer opens a new branch (P5); switch with ‹ ›.
- "Enlarge" and clicks on a product replace the dialog with a full-page view (enlarged answer or product page
  with shop offers); the composer stays below. Asking a question, or "Close"/Escape, returns to the dialog.
- Product pages and offer answers list shop offers with a fake "Add to cart" button: it only shows a notice;
  nothing is ordered.
- The circle on a product card selects it; selected products appear above the composer and are attached to
  the next question, which then refers only to them (e.g. "Which of them is the lightest?").
  On a product page, the product is attached to questions asked there (e.g. "How heavy is it?") without being
  selected; selecting it keeps it attached after closing the page, so products can be collected from their pages.
- Verbalization and parsing are consistent: a verbalized question, typed in again, yields the same plan
  (`tests/test_app.py`).

## Design variants (for refining the principles)

Variants are set by URL parameter (e.g. `http://localhost:8027/?variant=action&facets=0`):

| Setting | URL parameter | Effect |
|---|---|---|
| Every query is a turn (default) | `variant=query` | Sorting retrieved results, expanding a brand, and facet filters stay in the answer |
| Every action is a turn | `variant=action` | Sorting, expanding, and facets also become verbalized turns |
| Facets in answers | `facets=0` to hide | Facets computed from each result, left of the result |
| Minimized earlier answers (trial) | `collapse=0` to keep them open | When a new answer arrives, earlier answers shrink to their interpretation and can be reopened |

Products are shown as a result list (image left, details right, as in online shops); cards and table remain
available to scripted figures (`view` step). The "Query" tab, "Enlarge", product pages, and selecting products are always view changes.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --port 8027 --reload
```

Then open http://localhost:8027. Tests: `.venv/bin/python -m pytest`

## Demo container

The `Dockerfile` runs the prototype as a demo (port 7860, e.g., a Hugging Face Space):

```bash
docker build -t dialog-first . && docker run -p 7860:7860 dialog-first
```

To deploy the committed state as a Hugging Face Docker Space (create the Space with SDK "Docker" first; git asks
for the user name and an access token with write permission):

```bash
scripts/deploy-space.sh <user>/<space>
```

## Figures for the paper

`static/scenarios.js` defines scripted sessions with numbered badges (e.g. `paper`, `cards`, `refine`).
`?scenario=paper&figure=1` replays a session and shows only the dialog (without the opening answer). With the server running:

```bash
scripts/screenshots.sh ../chiir27-dialog-first-figures paper cards
```

writes `prototype-<scenario>.png` (2x resolution, trimmed) to the figures folder. Figure mode uses a compact
layout, so that panels taken at a narrow width and cropped to their essential part keep legible text in print.
The paper uses

```bash
WIDTH=580 scripts/screenshots.sh ../chiir27-dialog-first-figures 'opening:shopping&until=0&composer=1&crop=620' \
  'refined:shopping&until=4&last=3&crop=620' 'product:shopping&until=11&composer=1&crop=620' \
  'offers:shopping&until=13&last=4&collapse=1&crop=620'
```

## Storyboards for the presentation

The scenario `shopping` (`static/scenarios.js`) replays a shopping task step by step; `?until=<n>` stops after n
steps and shows only the latest exchange. With the server running,

```bash
python3 scripts/storyboards.py ../chiir27-dialog-first-storyboards
```

renders ten frames and writes `storyboard.pdf`: an A3 sheet with captions and lines for attendees' notes.
Further variants can be added to `VARIANTS` in the script, one sheet each.

## Next steps

- Language model behind `language.parse` and `language.readings`, as in our other Dialog-First applications
  (the rule-based parser stays the reproducible default for tests and figures).
- Further design variants, e.g. drill-down into members without a turn vs. with a turn, hover vs. click
  verbalization, and facets in answers vs. a facet panel.
