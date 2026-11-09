# Architecture

## Per-frame pipeline

```
CameraManager.read() → QRCodeDetector.detect() + ArucoDetector.detect()
   → MarkerFusion.update() → MarkerTracker.update() → ARRenderer.render() → cv2.imshow
```

Orchestrated by `MaqueteARApp.process()` in `app.py`. Each class has one job;
they communicate through plain dataclasses (`QRMarker`, `TrackedMarker`,
`ArucoMarker`, `FrameStats`), not through each other's internals.

## Key decisions (don't "fix" these without discussing)

- **One ArUco per element, fused with the QR (Phase 4).** Each element's JSON has
  `"aruco": N`; the ArUco is glued next to the QR. ArUco is detected much farther
  and at steeper angles than QR, so `vision/fusion.py: MarkerFusion` turns an
  ArUco into a synthetic `QRMarker` (`via_aruco=True`) whenever that element's QR
  wasn't read. When QR and ArUco are seen together it *learns* the QR corners in
  the ArUco's unit-square space (no calibration step), so the synthetic marker
  lands exactly where the QR is; before learning it uses the ArUco square itself.
  A read QR always wins (no duplicates); an unreadable QR lying inside the
  synthetic quad is dropped (it is that same QR). Learning is in-memory only and
  rejected if the QR is more than `MAX_LEARN_DISTANCE` ArUco sides away. The
  tracker matches by `element_id`, so switching between QR and ArUco keeps the
  same track (no flicker). ArUco poses (`rvec`/`tvec`) remain available for 3D (Phase 6).
- **OpenCV's native QR detector, not PyZBar.** No native `zbar` install needed,
  and it returns the 4 corners. `QRCodeDetectorAruco` is preferred: measured
  ~2× faster than the classic detector at `detect_scale=0.75`, and it decoded
  more codes.
- **Homography in "marker space".** The QR is the unit square (0,0)-(1,1);
  the panel is a rectangle in that space above it, projected with the same
  homography (`vision/perspective.py`, `ar/objects.py: TextPanel`). That's why the
  panel tilts/rotates with the QR. If the projected panel is too small or too
  distorted to read, it falls back to a screen-aligned "billboard" that still
  follows the QR position. The panel also falls back to billboard when its top
  edge (the title) would be off-screen.
- **Billboard placement avoids covering QRs** (a covered QR stops being read and
  its panel flickers). It tries above → below → right → left of the QR, may
  shrink to `MIN_BILLBOARD_SCALE` to fit free space, and picks the spot with
  least overlap with its own QR (heavily weighted) and other *readable* QRs
  (`RenderContext.obstacles`). Unreadable QRs are not obstacles (bogus quads).
- **Text is rendered with Pillow, not `cv2.putText`**, because OpenCV can't draw
  accents or emoji. Panels are rendered once per element and cached; small labels
  are cached with `lru_cache` (`ar/overlay.py`). Returned arrays are shared — never
  mutate them.
- **Alpha blending uses `cv2.blendLinear`** (C++) on the bounding ROI only;
  NumPy float blending was the second biggest cost per frame.
- **Tracker smooths and persists markers** for `max_missing_frames` so panels
  don't flicker when a frame fails to decode; an unreadable QR near a known track
  keeps that track's identity — but only if its size is within ±1.5× of the track
  (`QRCodeDetectorAruco` occasionally returns "unreadable" quads with bogus,
  oversized corners that would otherwise warp a real track and its panel).
- **`max_panels`**: only the N markers closest to the image center get a full
  panel (the student "aims" at what they want to read); others get a tag.
- **Sources are pluggable** (`camera/camera.py: FrameSource`): webcam, image/video
  file, and `DemoSource` (synthetic moving camera) so everything is testable
  without hardware.

## Phone version (web/)

- **Static site, processing on the phone.** No backend: the browser reads the
  camera (`getUserMedia`, needs HTTPS or localhost), detects, and draws. Frames
  never leave the device. Hosted on GitHub Pages; `.github/workflows/site.yml`
  runs the tests and `scripts/exportar_web.py` (copies `web/`, writes
  `data/conteudo.json` from `content/`, copies only validated media, renders
  `data/teste.png`) on every push to main.
- **QR = link.** With `config.json → web.url`, printed QRs contain
  `<url>/?e=<id>` so the phone's native camera opens the site. Both front-ends
  accept the plain id or such a link (`normalize_qr_text` / `parseQrText`).
- **Libraries**: `jsQR` (one QR per call, returns 4 corners) and `js-aruco2`
  (`ARUCO_4X4_1000`, whose first 50 codes equal OpenCV `DICT_4X4_50` bit-for-bit;
  corners come TL,TR,BR,BL like OpenCV — verified by reading its source).
  Vendored unmodified in `web/vendor/` (no CDN at runtime).
- **jsQR quirks handled in `main.js: readQrs`**: it fails when two QRs are in the
  image and is confused by ArUco squares (they look like finder patterns). So:
  full frame → centre crop → per-ArUco crops, with detected ArUcos painted white
  first. Per-ArUco crop = the learned QR box (`Fusion.predict`), or before
  learning one side at a time (left first, as on the print sheet; remembered).
- **Panel** = real HTML (crisp text, GIF animates natively) placed with CSS
  `matrix3d` from a homography (`geometry.js`). If it would not fit on screen
  or be too small/distorted, it becomes a bottom **card** that stays
  `CARD_KEEP_SECONDS` after the marker is lost (time to read on a phone).
  Only the element closest to the screen centre gets a panel.
- **Detection budget**: copy downscaled to 960 px wide (ArUco needs ~50 px),
  every 60 ms. `?debug=1` overlays frames/QR/ArUco/crops; `?teste=1` uses
  `data/teste.png` instead of the camera.

## Extension points for later phases

- New content type → subclass `ARObject` and select it in `ARObjectFactory._create()`
  based on JSON fields (`animacao`, `modelo` are already parsed). Phase 2 did
  exactly this: `ImagePanel(TextPanel)` only overrides `_build_image()`; if the
  image fails to load the factory falls back to `TextPanel`.
- Phase 3: `AnimatedPanel(TextPanel)` plays `animacao` (GIF/WebP/APNG, decoded by
  Pillow into an `AnimatedImage`). The panel is rendered once with an empty
  picture slot (`render_panel_slot`); each animation frame is pre-composed onto
  that slot's background, and per video frame only the slot is swapped, and only
  when the animation frame changes. Time comes from `RenderContext.elapsed`
  (seconds since the marker appeared), so animations restart when a QR reappears
  and play at the GIF's own speed, independent of camera FPS.
- Media files referenced from JSON → always via `core/assets.py`
  (`resolve_asset` + `load_image` / `load_animation`), never by opening the path directly.
- Animations → `ar/animations.py` (`Animation.value(elapsed)`).
- Object recognition → implement `vision/detector.py: ObjectDetector`
  (`NullObjectDetector` is the current placeholder wired in `app.py`).

## Performance budget (1280×720, demo with 8 QRs, dev PC)

QR detection ~20 ms, ArUco ~8 ms, rendering ~14 ms (debug on) → ~20–26 FPS.
If FPS becomes a problem, the next step is running detection in a background
thread, not dropping features.
