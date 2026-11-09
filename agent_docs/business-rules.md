# Business Rules & Domain Knowledge

This is an educational tool used live in a classroom. Its "business rules" are
about pedagogy, reliability in front of students, and safety of what the
camera reads.

## Pedagogy and content

- **All student-facing text is Brazilian Portuguese**, correct accents and
  spelling, written for school-age students: short sentences, no jargon
  without explanation, factual and neutral.
- **Content lives only in `content/<id>.json`**, never hard-coded in Python.
  A teacher must be able to change a text without touching code.
- **One element = one id = one JSON file = one printed QR Code.** The file
  name must equal the `id` field (`agricultura.json` ↔ `"id": "agricultura"`);
  the loader rejects mismatches.
- **The 8 base elements must always exist**: agricultura, pecuaria, comercio,
  industria, infraestrutura, meio_ambiente, residencia, trator
  (enforced by `tests/test_content.py`). Adding elements is fine; removing or
  renaming one invalidates QR Codes already printed and glued to the model.
- **Never change an existing id** for the same reason. Change the title or
  description instead.
- Keep descriptions to ~2–3 sentences (~200 characters) so the panel stays
  readable on screen.

## Reliability during class

- **The app must not close on its own.** Missing/busy camera, unreadable
  frames, bad JSON, unknown QR — all are shown as on-screen messages while the
  app keeps running and retrying. Only ESC/Q or closing the window exits.
- A broken content file must not prevent the other elements from loading.
- A missing/invalid image (`imagem`) never hides the element: it is reported
  as an on-screen warning at startup and the panel is shown with text only.
- A QR that is valid but has no content shows "Conteúdo desconhecido"; a QR
  with arbitrary text shows "QR inválido". Neither is an error that stops anything.

## Phases

Development is phased (1: QR + text → 2: images → 3: animations → 4: ArUco
tracking → 5: YOLO → 6: 3D → 7: full AR). Phases 1 and 2 are done. Do not implement a
later phase unless the user explicitly asks; keep the architecture ready for it.
