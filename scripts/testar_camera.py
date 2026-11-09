"""Diagnóstico de câmera: lista as câmeras disponíveis e mostra a imagem.

Uso:
    python scripts/testar_camera.py            # procura câmeras 0..4 e abre a primeira
    python scripts/testar_camera.py --index 1  # abre a câmera 1
    python scripts/testar_camera.py --list     # apenas lista
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

from ar.overlay import configure_console_utf8  # noqa: E402
from camera.camera import CameraError, DeviceSource  # noqa: E402


def probe(max_index: int = 5) -> list[tuple[int, tuple[int, int]]]:
    found = []
    for i in range(max_index):
        src = DeviceSource(i, 1280, 720, 30)
        try:
            src.open()
        except CameraError:
            continue
        found.append((i, src.actual_size or (0, 0)))
        src.release()
    return found


def main() -> int:
    configure_console_utf8()
    parser = argparse.ArgumentParser(description="Teste de câmera")
    parser.add_argument("--index", type=int)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    print("Procurando câmeras...")
    cams = probe()
    for i, (w, h) in cams:
        print(f"  câmera {i}: {w}x{h}")
    if not cams:
        print("Nenhuma câmera encontrada. Use 'python app.py --demo' para testar sem câmera.")
        return 1
    if args.list:
        return 0

    index = args.index if args.index is not None else cams[0][0]
    src = DeviceSource(index, 1280, 720, 30)
    try:
        src.open()
    except CameraError as exc:
        print(exc)
        return 1
    print(f"Mostrando câmera {index}. ESC para sair. Use esse índice em config.json -> camera.index")
    last, fps = time.perf_counter(), 0.0
    while True:
        frame = src.read()
        if frame is None:
            print("Falha na leitura.")
            break
        now = time.perf_counter()
        fps = 0.9 * fps + 0.1 / max(now - last, 1e-6)
        last = now
        cv2.putText(
            frame,
            f"Camera {index}  {frame.shape[1]}x{frame.shape[0]}  FPS {fps:.0f}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
        )
        cv2.imshow("Teste de camera", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break
    src.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
