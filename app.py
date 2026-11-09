"""Maquete AR — Realidade Aumentada para maquete escolar.

Fluxo de cada quadro:

    CameraManager -> QRCodeDetector -> MarkerTracker -> ContentManager -> ARRenderer

Uso:
    python app.py                 # webcam definida no config.json
    python app.py --demo          # sem câmera: maquete virtual animada
    python app.py --source foto.jpg | video.mp4 | 1
    python app.py --demo --headless --frames 90 --save saida.png   # teste sem janela
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ar.overlay import configure_console_utf8
from ar.renderer import ARRenderer, FrameStats
from camera.calibration import CameraCalibration
from camera.camera import CameraManager, build_source
from core.config import load_config
from core.content import ContentManager
from qr.detector import QRCodeDetector
from qr.markers import MarkerStatus
from vision.aruco import ArucoDetector, ArucoMarker
from vision.detector import NullObjectDetector, ObjectDetector
from vision.tracking import MarkerTracker

ROOT = Path(__file__).resolve().parent
log = logging.getLogger("maquete_ar")

KEY_ESC, KEY_Q, KEY_D, KEY_S = 27, ord("q"), ord("d"), ord("s")


class MaqueteARApp:
    """Orquestra câmera, detecção, rastreamento e renderização."""

    def __init__(self, config: dict[str, Any], source: str | int | None = None) -> None:
        self.cfg = config
        paths = config["paths"]
        assets_dir = ROOT / paths["assets"]
        self.contents = ContentManager(ROOT / paths["content"], assets_dir=assets_dir)
        cam_cfg = config["camera"]
        self.camera = CameraManager(
            build_source(cam_cfg, source, demo_ids=self.contents.ids[:8]),
            mirror=bool(cam_cfg.get("mirror", False)),
            reconnect_interval=float(cam_cfg.get("reconnect_interval", 2.0)),
            requested_size=(int(cam_cfg["width"]), int(cam_cfg["height"])),
        )
        self.frame_size = (int(cam_cfg["width"]), int(cam_cfg["height"]))
        self.qr = QRCodeDetector(config["qr"].get("backend", "auto"), float(config["qr"].get("detect_scale", 1.0)))
        trk = config["tracking"]
        self.tracker = MarkerTracker(float(trk["smoothing"]), int(trk["max_missing_frames"]))
        self.renderer = ARRenderer(
            self.contents,
            config["ar"],
            bool(config.get("debug", False)),
            int(trk["max_missing_frames"]),
            assets_dir=assets_dir,
        )
        aru = config["aruco"]
        self.aruco = ArucoDetector(aru["dictionary"], float(aru["marker_length_m"])) if aru.get("enabled") else None
        self.calibration: CameraCalibration | None = None
        self.object_detector: ObjectDetector = NullObjectDetector()  # Fase 5: YOLO
        self.stats = FrameStats(qr_backend=self.qr.backend, source=self.camera.source.description)
        self._last_time = time.perf_counter()

    # ------------------------------------------------------------------ #
    def process(self, frame: np.ndarray) -> np.ndarray:
        """Processa um quadro e devolve a imagem com a realidade aumentada."""
        now = time.monotonic()
        h, w = frame.shape[:2]
        if self.calibration is None or self.stats.resolution != (w, h):
            self.calibration = CameraCalibration.load(ROOT / self.cfg["paths"]["calibration"], (w, h))
        self.stats.resolution = (w, h)

        detections = self.qr.detect(frame)
        tracks = self.tracker.update(detections, now)
        aruco: list[ArucoMarker] = self.aruco.detect(frame, self.calibration) if self.aruco else []

        self.stats.detected = sum(1 for d in detections if d.status != MarkerStatus.UNREADABLE)
        readable = [d for d in detections if d.text]
        if readable:
            self.stats.last_qr = readable[0].label
        self.stats.aruco = aruco
        self.stats.warning = self.camera.warning or (
            f"{len(self.contents.errors)} arquivo(s) de conteúdo com erro (veja o log)"
            if self.contents.errors
            else None
        )
        self._update_fps()

        if self.aruco and self.renderer.debug:
            self.aruco.draw(frame, aruco, self.calibration)
        self.renderer.render(frame, tracks, self.stats, now)
        return frame

    def _update_fps(self) -> None:
        t = time.perf_counter()
        dt = max(t - self._last_time, 1e-6)
        self._last_time = t
        inst = 1.0 / dt
        self.stats.fps = inst if self.stats.fps == 0 else 0.9 * self.stats.fps + 0.1 * inst

    def next_frame(self) -> np.ndarray:
        """Lê e processa o próximo quadro; em falha, devolve uma tela de aviso."""
        frame = self.camera.read()
        if frame is None:
            if self.camera.error:
                return ARRenderer.message_screen(self.frame_size, "Câmera indisponível", self.camera.error)
            return ARRenderer.message_screen(self.frame_size, "Aguardando imagem...", "Conectando à câmera.")
        try:
            return self.process(frame)
        except Exception:  # noqa: BLE001 - um quadro ruim não pode fechar a aplicação
            log.exception("Erro ao processar quadro; continuando.")
            return frame

    # ------------------------------------------------------------------ #
    def run(self) -> None:
        """Laço principal com janela (ESC/Q sai, D alterna debug, S salva captura)."""
        title = self.cfg["window"]["title"]
        cv2.namedWindow(title, cv2.WINDOW_NORMAL)
        if self.cfg["window"].get("fullscreen"):
            cv2.setWindowProperty(title, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        else:
            cv2.resizeWindow(title, *self.frame_size)
        self.camera.open()
        try:
            while True:
                out = self.next_frame()
                cv2.imshow(title, out)
                key = cv2.waitKey(1 if self.camera.is_open else 200) & 0xFF
                if key in (KEY_ESC, KEY_Q):
                    break
                if key == KEY_D:
                    self.renderer.debug = not self.renderer.debug
                elif key == KEY_S:
                    self.save_screenshot(out)
                if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
                    break  # janela fechada no "X"
        finally:
            self.close()
            cv2.destroyAllWindows()

    def run_headless(self, frames: int, save: Path | None = None) -> np.ndarray:
        """Executa sem janela (testes/servidores). Retorna o último quadro."""
        self.camera.open()
        out = np.zeros((self.frame_size[1], self.frame_size[0], 3), np.uint8)
        found: set[str] = set()
        try:
            for _ in range(frames):
                out = self.next_frame()
                found.update(t.marker.element_id for t in self.tracker.tracks if t.marker.element_id)
        finally:
            self.close()
        print(f"Quadros: {frames} | FPS médio: {self.stats.fps:.1f} | elementos vistos: {sorted(found)}")
        if self.camera.error:
            print(f"Erro da câmera: {self.camera.error}")
        if save:
            self.save_screenshot(out, save)
        return out

    def save_screenshot(self, frame: np.ndarray, path: Path | None = None) -> Path:
        if path is None:
            folder = ROOT / self.cfg["paths"]["screenshots"]
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / time.strftime("captura_%Y%m%d_%H%M%S.png")
        path.parent.mkdir(parents=True, exist_ok=True)
        ok, buf = cv2.imencode(path.suffix or ".png", frame)
        if ok:
            buf.tofile(str(path))  # funciona com acentos no caminho (Windows)
            print(f"Captura salva em {path}")
        return path

    def close(self) -> None:
        self.camera.release()
        self.object_detector.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Realidade Aumentada para maquete escolar")
    p.add_argument("--config", default=str(ROOT / "config.json"), help="arquivo de configuração")
    p.add_argument("--source", help="índice da câmera, caminho de imagem/vídeo ou 'demo'")
    p.add_argument("--demo", action="store_true", help="modo demonstração (sem câmera)")
    p.add_argument("--debug", dest="debug", action="store_true", default=None, help="força DEBUG ligado")
    p.add_argument("--no-debug", dest="debug", action="store_false", help="força DEBUG desligado")
    p.add_argument("--headless", action="store_true", help="executa sem janela")
    p.add_argument("--frames", type=int, default=60, help="quadros no modo --headless")
    p.add_argument("--save", type=Path, help="salva o último quadro (modo --headless)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_console_utf8()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args(argv)
    config = load_config(args.config)
    if args.debug is not None:
        config["debug"] = args.debug
    source = "demo" if args.demo else args.source

    app = MaqueteARApp(config, source)
    if app.contents.errors:
        for err in app.contents.errors:
            print(f"[conteúdo] {err}")
    if args.headless:
        app.run_headless(args.frames, args.save)
    else:
        app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
