# Productivity & Tooling

- **Test without a camera**: `app.py --demo` (animated synthetic model) or
  `app.py --source qrcodes/demo_maquete.png` / any `.mp4`. Use
  `--headless --frames N --save out.png` to run in a terminal and inspect the
  result image — this is how to verify rendering changes in a Claude session.
- **Camera problems**: `scripts/testar_camera.py --list` finds working camera
  indices; put the right one in `config.json → camera.index`.
- **Printing**: `scripts/gerar_qrcodes.py` puts each element's ArUco next to its
  QR (5 cm QR + 3 cm ArUco = `aruco.marker_length_m`), 8 pairs per A4 page,
  extra pages as needed. Print at 100 % and glue each pair together, flat.
- **Phone version locally**: `scripts/exportar_web.py` then
  `python -m http.server -d build/web 8000`; `/?teste=1&debug=1` needs no camera.
  Headless check without the Chrome extension:
  `msedge --headless=new --user-data-dir=<tmp> --window-size=1280,720
  --virtual-time-budget=8000 --screenshot=<png> "http://127.0.0.1:8000/?teste=1&debug=1"`
  (use a fresh profile dir per run; for true phone width put the page in a
  390 px iframe — headless enforces a ~500 px minimum window).
- **In-app keys**: `D` toggles DEBUG overlay, `S` saves a screenshot, `ESC`/`Q` quits.
- **Version control**: Git, default branch `main` (local only, no remote yet).
  Use Conventional Commits and `feat/`/`fix/` branches (see `.claude/rules/general.md`);
  the pre-commit hook in `.claude/settings.json` validates lint/types/tests.
  `.gitattributes` forces LF line endings; generated files (`qrcodes/*.png`,
  `assets/markers/`, caches, `.venv/`) are git-ignored.
