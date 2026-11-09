---
paths:
  - "content/**/*.json"
---
# Content JSON Rules

- File name == `id` field; `id` matches `^[a-z0-9_]{1,40}$`. Never rename an
  existing id (printed QR Codes depend on it).
- Required: `id`, `titulo`, `descricao` (non-empty strings). Optional: `icone`
  (one emoji), `cor` (named color from `core/content.py: COLOR_NAMES` or
  `#RRGGBB`), `imagem` (Phase 2), `animacao` (Phase 3), and for later phases `modelo`.
- `imagem`: path relative to `assets/`, e.g. `"images/trator.jpg"` (a leading
  `assets/` is tolerated). PNG/JPG/WEBP/BMP, ≤ 15 MB; landscape images look best
  (shown at most ~0.42× the panel width tall). PNG transparency is kept. A missing
  file shows a startup warning and a text-only panel — never remove the element.
  Only use images the school has the right to use (own photos, free licenses).
- `animacao`: animated GIF/WebP/APNG relative to `assets/`, e.g.
  `"animations/plantio.gif"`. Shown in the picture area, looping at the file's
  own speed, restarting when the QR appears. Takes priority over `imagem` (keep
  both: the image is the fallback). Keep it short (≤ ~10 s, ≤ 300 frames) —
  longer ones are cut to fit the memory budget.
- Text in Brazilian Portuguese with accents, for school students, ~2–3
  sentences (~200 chars). UTF-8, 4-space indentation.
- After adding a new element: run `scripts/gerar_qrcodes.py` to create its QR,
  then `pytest -q`.
