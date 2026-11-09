# Project Context

Augmented-reality app for a physical school model ("maquete") of an urban/rural
community. A camera sees printed QR Codes placed on the model; the app identifies
each element (agriculture, livestock, tractor...) and overlays an educational
panel that follows the QR in perspective. Audience: school students. Two
front-ends share `content/`: the Python desktop app (Windows PC + USB webcam +
projector) and a static web app in `web/` that runs on each student's phone
(GitHub Pages). Single maintainer. Current phase: **Phase 4
(one ArUco per element, fused with QR) done** — do not start later phases unless asked.

# Stack

- Python 3.12 (supported floor: 3.11), venv in `.venv/`, pip + `requirements.txt`
- OpenCV 5.0 (`opencv-python`; QR via `cv2.QRCodeDetectorAruco`, ArUco via `cv2.aruco`)
- NumPy 2.x, Pillow ≥10.1 (text with accents/emoji), `qrcode` (generation)
- pytest, ruff (lint + format), mypy (types) — config in `pyproject.toml`
- Web (phone) version: plain HTML/CSS/ES modules in `web/`, no build tool, no npm
  runtime deps; vendored `jsQR` + `js-aruco2` in `web/vendor/`; Node 22 only for
  `node --test` (run by pytest). Published by `.github/workflows/site.yml`.
- No database, no backend: the site is static; camera frames never leave the device

# Commands

Run from the project root (Windows paths; Linux/macOS use `.venv/bin/`).

```
# Install
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# Run (webcam from config.json)
.venv\Scripts\python app.py
# Run without camera (synthetic animated model)
.venv\Scripts\python app.py --demo
# Headless smoke run, saves last frame (use this to verify visual changes)
.venv\Scripts\python app.py --demo --headless --frames 60 --save out.png

# Test
.venv\Scripts\python -m pytest -q

# Lint + format + typecheck
.venv\Scripts\ruff check . && .venv\Scripts\ruff format . && .venv\Scripts\mypy

# Generate printable QR codes + each element's ArUco (qrcodes/*.png + A4 sheet[s])
.venv\Scripts\python scripts\gerar_qrcodes.py

# Web (phone) version: build the site and serve it locally (camera works on localhost)
.venv\Scripts\python scripts\exportar_web.py
.venv\Scripts\python -m http.server -d build\web 8000   # then /?teste=1&debug=1
node --test "web/tests/*.test.mjs"                       # JS unit tests (also run by pytest)
```

No build step.

# File Structure

```
app.py        entry point + MaqueteARApp (Camera → QR → Tracker → Content → Renderer)
config.json   runtime config (camera, debug, AR panel, ArUco); defaults in core/config.py
core/         config loading, ContentManager (JSON content + validation), assets.py (safe media paths, image/animation loading)
camera/       frame sources (webcam, file, demo), CameraManager, calibration
qr/           QRCodeDetector, QRMarker + id validation, QR generator/print sheet
vision/       homography (perspective.py), tracking, ArUco, QR+ArUco fusion, ObjectDetector interface
ar/           panel/text drawing (overlay.py), ARObject types, animations, ARRenderer
content/      one <id>.json per model element (educational text, PT-BR)
web/          phone version: index.html, css/, js/ (geometry, markers = JS port of
              fusion/tracking, main), vendor/ (third-party, unmodified), tests/
scripts/      gerar_qrcodes.py, gerar_aruco.py, testar_camera.py, exportar_web.py
tests/        pytest suite (no camera needed)
assets/       images/ (Phase 2) and animations/ (Phase 3) for panels; icons/videos/models later
```

# Workflow Rules

- After any code change run lint + typecheck + tests (commands above); a hook in
  `.claude/settings.json` blocks `git commit`/`git push` if any of them fail.
- For visual/rendering changes, also run the headless demo and look at the saved frame.
- Fix bugs test-first: add a failing test in `tests/` that reproduces it, then fix.
- Never put educational text in Python code — it lives in `content/*.json`.
- The app must never crash during class: wrap failures, show an on-screen message, keep running.
- Behaviour shared by both front-ends (QR parsing, fusion, tracking rules) must
  change in **both** `qr/`/`vision/` (Python) and `web/js/markers.js` (JS), with tests
  on each side.
- For web changes, verify in a real browser: `?teste=1&debug=1` (headless Edge
  screenshot works if the Chrome extension is unavailable).
- Keep phases incremental: new content types = new `ARObject` subclass registered in
  `ARObjectFactory` (`ar/objects.py`), not changes to the render loop.

# Deeper Context (read when relevant)

- Business rules and domain logic: @agent_docs/business-rules.md
- Security practices for this project: @agent_docs/security.md
- Engineering standards and quality philosophy: @agent_docs/engineering-standards.md
- Architecture decisions: @agent_docs/architecture.md
- Productivity tools and workflows: @agent_docs/productivity.md
- Path-scoped conventions: see `.claude/rules/` (e.g. `content.md` for `content/*.json`)

# Keeping This File Current

This is a living system, not a one-time setup artifact. If you encounter
something during real work that should be a permanent rule — a business
rule, a security constraint, an architectural decision, a mistake worth
never repeating — don't just apply it silently. Ask whether it should be
added, and add it to the right file above (not dumped into this one). When
you get something wrong because a rule was missing, that's a signal the
docs need updating — say so.

# Response Language

Always respond in Brazilian Portuguese, regardless of the language used in the prompt.
