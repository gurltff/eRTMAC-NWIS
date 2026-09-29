# eRTMAC NWIS – Nearby Wells Intelligence System

Prototype for **Oil India Limited problem statement 26121**: an AI-assisted offset-well knowledge and decision
support platform for drilling operations, built around a location-intelligence map, driller registration,
live geotag tracking with range checks, an offset-well alert engine and AI document extraction.

> **Everything runs on SAMPLE data.** Field names, formations and protected-area names are real; locations,
> outlines, events and all numbers are approximate or generated. The UI shows a "Sample data" badge on every
> screen and a full honesty panel under **Office view → Data & models**.

- **Backend:** Python, FastAPI, SQLAlchemy + SQLite, websockets, scikit-learn, pypdf, optional Claude (Anthropic SDK)
- **Frontend:** React + Vite, Leaflet (CARTO basemaps), Recharts, light and dark themes
- **Tests:** 35 pytest tests (geometry, trajectory, breach detection, alert engine, main API routes, websocket, extraction)

**Live demo (browser-only build):** https://claude.ai/artifact/82Wddt5F3s9UpK7aMoSCEs
(private until shared from its Share menu). A GitHub Pages copy publishes automatically from
`.github/workflows/pages.yml` once Pages is switched on (Settings → Pages → Source: **GitHub Actions**) at
`https://gurltff.github.io/eRTMAC-NWIS/`. See section 7 for what the hosted build does differently.

---

## 1. Run it locally (two commands)

Needs Python 3.10+ and Node 18+.

```bash
# Terminal 1 – API (creates and seeds backend/nwis.db on first start)
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Terminal 2 – web app
cd frontend
npm install
npm run dev            # open http://localhost:5173
```

The Vite dev server proxies `/api` and `/ws` to port 8000. API docs are at http://localhost:8000/docs.

**Single process instead:** `cd frontend && npm run build`, then start the backend. FastAPI serves the built app at
http://localhost:8000.

**Docker:** `docker compose up --build` → app at http://localhost:8080, API at http://localhost:8000.

**Reset the sample data:** `cd backend && python -m seed.seed`.

**Run the tests:** `cd backend && pytest -q`.

### Optional settings (`.env.example`)

| Variable | Effect |
|---|---|
| `ANTHROPIC_API_KEY` | Document extraction uses Claude (structured JSON output). Without it, rule-based extraction runs. |
| `JWT_SECRET` | Signing key for login tokens. Set a long random value outside a demo. |
| `SOILGRIDS_ENABLED=0` | Skip live ISRIC SoilGrids calls (an estimate from geology is used instead). |
| `DRILLING_SIM_ENABLED=0` | Stop the active wells' depth from advancing on its own. |

---

## 2. Log in as each role

| Role | Email | Password | What to show |
|---|---|---|---|
| Admin | `admin@nwis.demo` | `Admin@123` | Approvals (documents and registrations), all dashboards |
| Drilling engineer | `engineer@nwis.demo` | `Engineer@123` | Office view: map, offset wells, knowledge base, tracking, documents |
| Driller (approved) | `driller@nwis.demo` | `Driller@123` | Field view on a phone, live tracking, simulator, alerts |
| Driller (approved, 2nd) | `driller2@nwis.demo` | `Driller@123` | A second crew on the tracking map |
| Driller (under review) | `driller3@nwis.demo` | `Driller@123` | Registration status, a rejected document |
| Driller (not finished) | `driller4@nwis.demo` | `Driller@123` | Empty registration wizard |

The login page has one-click buttons for these. New heads of drilling can also **Create an account** and go
through the six-step registration (personal → company → documents → rigs → working area → submit). The admin then
approves or rejects each document and the registration.

---

## 3. Suggested demo script (≈5 minutes)

1. **Location intelligence.** Log in as the engineer and open **Location map**. Tap any spot. The panel shows:
   history, rock and soil, a success score (0–100) with confidence, hazards (landslide, subsidence, flooding,
   gas kick, mud loss, stuck pipe, earthquake, eco-sensitivity), legal or illegal zone, estimated oil (P90/P50/P10
   and risked), and ownership. Try a spot inside Dehing Patkai National Park (illegal) and one on open ground.
2. **Untapped spots.** Leave *Untapped spots* and *Potential heatmap* on. Click a gold star, then
   **How untapped spots work** for the plain-language explanation.
3. **Live tracking and range alerts.** Open **Live tracking** and press **Start simulator** for Rituraj Baruah.
   The dot walks around the site, into the Maguri-Motapung wetland (→ *Entered an illegal zone*), back, then out
   past the edge of the allowed circle (→ *Left the allowed working zone*). Every event shows as a toast and is
   logged with time and coordinates. On a phone, log in as `driller@nwis.demo` and use **Share my GPS** or **Simulator**.
4. **Offset wells.** Open **Offset wells**, pick `NHK-A01`, change the radius. Drag *Demo: move the bit* to just
   above the next risk zone and press **Set**: an alert appears with a recommendation and "what worked nearby".
   Scroll down for the depth-vs-formation correlation, the ML risk curves and the searchable event list.
5. **Document extraction.** Open **Document extraction** → **Try the sample report**. Well `HGJ-77`, its formation
   tops and five problems are pulled out and saved. Search "HGJ-77" in the knowledge base or find it on the map.
6. **Approvals.** Log in as admin → **Approvals** → Kaustav Saikia: approve or reject documents, then the registration.
7. **Field view.** Switch to the field view (sidebar button, or log in as the driller on a phone). It uses the
   same "library and reader" layout as the design reference: the active well is the book, formations are chapters.
   The theme button switches light and dark.

The active wells drill by themselves (3 m every 4 s) so alerts also fire on their own during a demo.

---

## 4. How the main parts work

**Allowed zone (physics and geometry, `backend/app/services/geo.py`)**
- Distances use the **haversine** formula.
- Operating radius = rig **maximum horizontal reach + safety margin**, where margin = max(10 % of reach, 250 m).
  The radius is capped by the working radius the driller declared.
- The planned **bottom-hole location** comes from the **minimum curvature method** (MD, inclination, azimuth)
  on a build-and-hold well plan. The app warns if it goes beyond rig reach or ends under a protected area.
- **Breach detection**: every position is classified as INSIDE, NEAR_EDGE (>90 % of radius), OUTSIDE, or
  ILLEGAL_ZONE (ray-casting point-in-polygon against protected, forest, wetland and restricted polygons). Events are
  logged **only when the status changes**, so standing outside for an hour gives one record, not thousands.

**Offset alert engine (`backend/app/services/alerts.py`)** – problems from offset wells are moved onto the active
well's depth by **formation correlation** (same relative position inside the same formation), grouped by problem
type and formation, and raised when the bit is within 150 m above the zone or inside it. Severity depends on how
many wells had the problem, how bad it was and how close those wells are. Each alert has a recommendation plus the
actions and lessons from the nearest wells.

**Models (`backend/app/services/ml.py`, scikit-learn)**
- *Prospect model:* random forest over structural closure (sample seismic map), depth to the Tipam reservoir,
  geological play prior, success share of nearby wells and well density. It is trained on the finished sample
  wells and cross-validated; the score is shown in the panel. Confidence = tree agreement + distance to data.
- *Untapped spots:* grid cells (~2.7 km) scoring ≥ 50 with no well within 2.5 km, outside illegal zones, ≥ 5 km apart.
- *Drilling risk model:* one random forest per problem type over 50 m intervals (depth, formation, mud weight,
  pore pressure, overbalance, offset frequency in the same formation within 15 km).

**Oil estimate** – volumetric STOIIP = 7758 · A · h · φ · (1 − Sw) / Bo × recovery factor, 2,000 Monte Carlo runs
with inputs borrowed from the nearest fields and net pay scaled by closure. It is multiplied by the chance of success to give the risked value.

**Document extraction** – pypdf text (OCR with pytesseract + pdf2image if installed), then Claude with a strict
schema when `ANTHROPIC_API_KEY` is set, else regex and keyword rules. Results create or update the well and its
events, so they appear in search and on the map straight away.

**Live updates** – a websocket (`/ws/live`) pushes driller positions, breaches, well depth changes and new alerts.
Office roles see everything; a driller sees their own feed.

---

## 5. Data sources: loaders and sample files

Loaders live in `backend/loaders/`. Each reads the real dataset from `data/raw/<folder>/` when it is there, and
otherwise falls back to the sample in `data/samples/`. See `data/raw/README.md` for what goes where.

| Dataset | Loader | Used now | Notes |
|---|---|---|---|
| GEM Oil & Gas Extraction Tracker (India) | `gem_loader.py` | Sample CSV in GEM layout: 18 real Assam/Arunachal field names and operators, approximate centroids | Wells are scattered around field centroids, as the brief asks |
| Equinor Volve daily drilling reports | `volve_ddr_loader.py` | Synthetic DDR in the real WITSML `drillReport` structure | Parsed events go on well `VOLVE-F12 (relocated)`, **moved onto Assam coordinates for the demo** |
| GSI Bhukosh geology (shapefiles) | `geology_loader.py` | Simplified sample polygons of the main Upper Assam units | Put the downloaded shapefiles in `data/raw/bhukosh/` |
| NASA Global Landslide Catalog | `landslide_loader.py` | Sample rows in the NASA column layout | |
| OpenTopography SRTM 30 m | `app/services/terrain.py` | Modelled terrain surface | Add GeoTIFFs + `pip install rasterio` for real elevation; slope uses the same 30 m central-difference method either way |
| ISRIC SoilGrids | `app/services/soil.py` | **Live API** (cached per ~1 km cell); estimate if offline | UI notes that soil covers only the top 2 m (surface safety, not oil potential) |
| WDPA + OSM forests | `zones_loader.py` | Simplified outlines of real protected areas and reserved forests | Any point inside is marked **illegal** |
| Land ownership | seed script | Generated parcels and ownership history | No open dataset exists; a real version would connect to state land-record portals (e.g. Assam Dharitree) |
| DGH National Data Repository | – | Not connected | Named as the production integration |

FORCE 2020, NLOG and NSTA NDR are optional extra training data. They are not wired in; the loader pattern above is where they would go.

---

## 6. What is real and what is mocked (for the demo Q&A)

| | |
|---|---|
| **Real** | Full-stack app (FastAPI + DB + React), JWT auth with roles, websocket live tracking, the geometry (haversine, point-in-polygon, minimum curvature, allowed radius), breach logging, the alert engine, trained and cross-validated scikit-learn models, PDF text extraction + rule-based NLP, optional Claude extraction, live SoilGrids calls, the dataset loaders |
| **Real names, sample values** | Oil fields and operators, stratigraphy (Girujan, Tipam, Barail, Kopili, Sylhet…), protected areas (Dibru-Saikhowa, Dehing Patkai, Maguri-Motapung…), field history notes (e.g. Digboi 1889, Baghjan 2020 blowout) |
| **Sample / generated** | Well locations, events, depth logs, production, reserves, reservoir parameters, zone outlines, geology polygons, landslides, drillers and companies, land ownership, the seismic structure map, terrain |
| **Simulated** | Driller GPS movement (simulator), live bit depth of the three active wells |

Models are trained on sample data, so their numbers show how the system works. They are not real predictions.

---

## 7. Hosted demo (static, browser-only)

The hosted link runs **the same frontend** built with `npm run build:demo`. There is no Python server in that
build: API calls are answered **inside the browser** by `frontend/src/demo/`, using

- a snapshot of the sample database (`frontend/public/demo/snapshot.json`, made by `python -m scripts.export_demo`),
  which includes precomputed model outputs (success score on a 2.7 km grid, risk curves, untapped spots);
- JavaScript ports of the geometry, breach, alert-engine and rule-based extraction code (checked against the
  Python results);
- `pdf.js` to read PDFs, and in-browser timers for the tracking and drilling simulators.

Changes you make there (registrations, approvals, breaches) are saved only in your own browser. If the map
tiles can't load (offline, or a host that blocks external images), the map draws a simple basemap from the
app's own geology, river and field layers instead. For the full
system (real backend, Claude extraction, OCR, retraining), run it locally as in section 1.

To rebuild the hosted version: `cd backend && python -m scripts.export_demo && cd ../frontend && npm run build:demo`.

---

## 8. Project layout

```
backend/
  app/
    main.py              FastAPI app, startup seeding, background simulators, serves the built frontend
    models.py            SQLAlchemy tables
    auth.py              PBKDF2 password hashing, JWT, role checks
    routers/             auth, driller, admin, tracking (+ websocket), wells/events/alerts, map/analytics, documents
    services/            geo, terrain, subsurface, spatial, soil, hazards, reserves, ml, alerts,
                         well_monitor, tracking, location_intel, extraction, event_classifier
  loaders/               GEM, Volve DDR, Bhukosh, WDPA/OSM, NASA landslides
  seed/seed.py           sample data generator (deterministic)
  scripts/               sample geodata + sample PDF generators, demo snapshot export
  tests/                 pytest suite
frontend/
  src/pages/             office pages, driller portal, field (phone) pages
  src/components/        map layers, location panel, correlation view, charts, layouts
  src/demo/              in-browser backend for the static hosted demo
data/
  samples/               sample datasets (committed)
  raw/                   put real downloads here (git-ignored)
```

## 9. Choices made where the brief was open

- **SQLite + Python geometry instead of PostGIS.** It runs with zero setup, and all spatial queries sit behind small helpers, so switching to PostGIS only touches the models and those helpers.
- **"Allowed zone" is a circle around the approved site.** Radius = rig reach + margin, capped by the declared area; no-go polygons are checked separately and override it.
- **Legality has three states.** *Legal* (inside a licence block), *Illegal* (protected, forest, wetland or restricted) and *Needs licence* (open ground no licence covers yet).
- **Self-registration is only for drillers.** Engineer and admin accounts are seeded; in production an admin would create them.
- **The simulator runs fast-forward (~45 m/s).** That way one loop, including both breach types, fits in about two minutes.
- **HashRouter** keeps the static hosted demo working without server-side rewrites.
