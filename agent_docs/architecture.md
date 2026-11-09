# Architecture

## Per-frame pipeline

```
CameraManager.read() → QRCodeDetector.detect() → MarkerTracker.update()
   → (ArucoDetector.detect()) → ARRenderer.render() → cv2.imshow
```

Orchestrated by `MaqueteARApp.process()` in `app.py`. Each class has one job;
they communicate through plain dataclasses (`QRMarker`, `TrackedMarker`,
`ArucoMarker`, `FrameStats`), not through each other's internals.

## Key decisions (don't "fix" these without discussing)

- **QR identifies, ArUco locates.** QR Codes say *what* an element is; ArUco
  markers (Phase 4) give a stable pose for 3D anchoring. Both are detected; only
  QR drives content today.
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

## Extension points for later phases

- New content type → subclass `ARObject` and select it in `ARObjectFactory._create()`
  based on JSON fields (`animacao`, `modelo` are already parsed). Phase 2 did
  exactly this: `ImagePanel(TextPanel)` only overrides `_build_image()`; if the
  image fails to load the factory falls back to `TextPanel`.
- Media files referenced from JSON → always via `core/assets.py`
  (`resolve_asset` + `load_image`), never by opening the path directly.
- Animations → `ar/animations.py` (`Animation.value(elapsed)`).
- Object recognition → implement `vision/detector.py: ObjectDetector`
  (`NullObjectDetector` is the current placeholder wired in `app.py`).

## Performance budget (1280×720, demo with 8 QRs, dev PC)

QR detection ~20 ms, ArUco ~8 ms, rendering ~14 ms (debug on) → ~20–26 FPS.
If FPS becomes a problem, the next step is running detection in a background
thread, not dropping features.
