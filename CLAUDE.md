# Project Context

Augmented-reality app for a physical school model ("maquete") of an urban/rural
community. A camera sees printed QR Codes placed on the model; the app identifies
each element (agriculture, livestock, tractor...) and overlays an educational
panel that follows the QR in perspective. Audience: school students; runs on a
Windows PC with a USB webcam. Single maintainer. Current phase: **Phase 2
(images in panels) done** — do not start later phases unless asked.

# Stack

- Python 3.12 (supported floor: 3.11), venv in `.venv/`, pip + `requirements.txt`
- OpenCV 5.0 (`opencv-python`; QR via `cv2.QRCodeDetectorAruco`, ArUco via `cv2.aruco`)
- NumPy 2.x, Pillow ≥10.1 (text with accents/emoji), `qrcode` (generation)
- pytest, ruff (lint + format), mypy (types) — config in `pyproject.toml`
- No database, no network, no deployment: local desktop app

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

# Generate printable QR codes (qrcodes/*.png + A4 sheet)
.venv\Scripts\python scripts\gerar_qrcodes.py
```

No build step.

# File Structure

```
app.py        entry point + MaqueteARApp (Camera → QR → Tracker → Content → Renderer)
config.json   runtime config (camera, debug, AR panel, ArUco); defaults in core/config.py
core/         config loading, ContentManager (JSON content + validation), assets.py (safe image paths/loading)
camera/       frame sources (webcam, file, demo), CameraManager, calibration
qr/           QRCodeDetector, QRMarker + id validation, QR generator/print sheet
vision/       homography (perspective.py), tracking, ArUco, ObjectDetector interface
ar/           panel/text drawing (overlay.py), ARObject types, animations, ARRenderer
content/      one <id>.json per model element (educational text, PT-BR)
scripts/      gerar_qrcodes.py, gerar_aruco.py, testar_camera.py
tests/        pytest suite (no camera needed)
assets/       images/ for panels (Phase 2); icons/videos/models for later phases
```

# Workflow Rules

- After any code change run lint + typecheck + tests (commands above); a hook in
  `.claude/settings.json` blocks `git commit`/`git push` if any of them fail.
- For visual/rendering changes, also run the headless demo and look at the saved frame.
- Fix bugs test-first: add a failing test in `tests/` that reproduces it, then fix.
- Never put educational text in Python code — it lives in `content/*.json`.
- The app must never crash during class: wrap failures, show an on-screen message, keep running.
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
