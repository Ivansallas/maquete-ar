# Security Considerations

Local desktop app: no network, no accounts, no database, no secrets. The
attack surface is **what the camera reads** and **files loaded from disk**.

## QR Code content is untrusted input

Anyone can print a QR Code and hold it in front of the camera.

- The decoded text is **only an identifier**. It is normalized and must match
  `^[a-z0-9_]{1,40}$` (`qr/markers.py: normalize_qr_text`); anything else is
  rejected as "QR inválido".
- Never `eval`/`exec` it, pass it to a shell/`subprocess`, open URLs from it,
  or build file paths from it. Content is looked up in an in-memory dict that
  `ContentManager` built at startup from `content/*.json`, so path traversal
  (`../`) is impossible by construction — keep it that way.
- Long or binary QR payloads are dropped (`MAX_QR_TEXT`).

## Files loaded from disk

- JSON is parsed with `json.load` only (never `pickle`, `yaml.load`, or
  `eval`). Fields are type-checked in `ElementContent.from_dict`.
- Media referenced from JSON (images since Phase 2; videos and 3D models later)
  goes through `core/assets.py: resolve_asset`, which resolves paths relative
  to `assets/`, rejects absolute paths, drive letters and anything that escapes
  `assets/` after `Path.resolve()`, and allows only known extensions.
  `load_image` caps file size (`MAX_IMAGE_BYTES`) and pixel size; decode
  failures raise `AssetError` and are recoverable (text-only panel, never a crash).
- Use `np.fromfile` + `cv2.imdecode` / `buf.tofile` for image I/O so paths
  with accents work on Windows.

## Privacy

- The camera may capture students' faces. Frames are processed in memory and
  never stored or transmitted. Screenshots happen only when the user presses
  `S` and go to `screenshots/` (git-ignored). Do not add automatic recording,
  uploading, or face analysis without the user explicitly asking.

## Dependencies

- Install only from PyPI via `requirements.txt`; prefer well-known packages.
  `opencv-python` (not `-contrib`) is enough — ArUco is in the main module
  since 4.7. Don't add heavy dependencies (YOLO/torch, Open3D) before their phase.
- No secrets exist in this project; if one is ever needed (e.g. a cloud API in a
  later phase), load it from environment variables and never commit it.
