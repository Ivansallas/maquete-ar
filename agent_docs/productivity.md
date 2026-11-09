# Productivity & Tooling

- **Test without a camera**: `app.py --demo` (animated synthetic model) or
  `app.py --source qrcodes/demo_maquete.png` / any `.mp4`. Use
  `--headless --frames N --save out.png` to run in a terminal and inspect the
  result image — this is how to verify rendering changes in a Claude session.
- **Camera problems**: `scripts/testar_camera.py --list` finds working camera
  indices; put the right one in `config.json → camera.index`.
- **In-app keys**: `D` toggles DEBUG overlay, `S` saves a screenshot, `ESC`/`Q` quits.
- **Version control**: Git, default branch `main` (local only, no remote yet).
  Use Conventional Commits and `feat/`/`fix/` branches (see `.claude/rules/general.md`);
  the pre-commit hook in `.claude/settings.json` validates lint/types/tests.
  `.gitattributes` forces LF line endings; generated files (`qrcodes/*.png`,
  `assets/markers/`, caches, `.venv/`) are git-ignored.
