"""Gera marcadores ArUco para impressão (referência espacial — Fase 4).

Uso:
    python scripts/gerar_aruco.py              # os ArUcos dos elementos em content/
    python scripts/gerar_aruco.py --ids 0 1 2

Para imprimir QR + ArUco juntos, use ``scripts/gerar_qrcodes.py`` (folha A4).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

from core.content import ContentManager  # noqa: E402
from vision.aruco import ArucoDetector  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera marcadores ArUco")
    parser.add_argument("--ids", type=int, nargs="+", help="padrão: campo 'aruco' de cada elemento")
    parser.add_argument("--dictionary", default="DICT_4X4_50")
    parser.add_argument("--out", type=Path, default=ROOT / "assets" / "markers")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    detector = ArucoDetector(args.dictionary)
    owners = ContentManager(ROOT / "content").aruco_map
    for marker_id in args.ids or sorted(owners):
        if marker_id in owners:
            print(f"  ArUco {marker_id} -> {owners[marker_id]}")
        img = detector.generate(marker_id)
        path = args.out / f"aruco_{marker_id}.png"
        ok, buf = cv2.imencode(".png", img)
        if ok:
            buf.tofile(str(path))
            print(f"  ok {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
