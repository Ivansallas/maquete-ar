"""Fontes de imagem (webcam, arquivo de imagem/vídeo, demonstração) e o
:class:`CameraManager`, que cuida de abrir, ler e reconectar a câmera sem
derrubar a aplicação.
"""

from __future__ import annotations

import logging
import math
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from vision.perspective import f32

log = logging.getLogger(__name__)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

_BACKENDS = {
    "any": cv2.CAP_ANY,
    "dshow": cv2.CAP_DSHOW,
    "msmf": cv2.CAP_MSMF,
    "v4l2": cv2.CAP_V4L2,
    "avfoundation": cv2.CAP_AVFOUNDATION,
}


class CameraError(RuntimeError):
    """Erro ao abrir/ler a fonte de vídeo (mensagem pronta para o usuário)."""


class FrameSource(ABC):
    """Qualquer coisa que forneça quadros BGR: webcam, vídeo, imagem, demo."""

    live: bool = True  # fontes "ao vivo" não precisam de controle de ritmo

    @abstractmethod
    def open(self) -> None:
        """Abre a fonte; lança :class:`CameraError` com mensagem amigável."""

    @abstractmethod
    def read(self) -> np.ndarray | None:
        """Próximo quadro, ou ``None`` se a leitura falhou."""

    def release(self) -> None:  # noqa: B027 - opcional nas subclasses
        """Libera a fonte."""

    @property
    def description(self) -> str:
        return self.__class__.__name__


class DeviceSource(FrameSource):
    """Webcam/câmera USB acessada pelo índice (0, 1, 2...)."""

    def __init__(self, index: int, width: int, height: int, fps: int, backend: str = "auto") -> None:
        self.index = index
        self.width, self.height, self.fps = width, height, fps
        self.backend = backend
        self.cap: cv2.VideoCapture | None = None
        self.actual_size: tuple[int, int] | None = None

    @property
    def description(self) -> str:
        return f"câmera {self.index}"

    def _backends(self) -> list[int]:
        if self.backend != "auto":
            return [_BACKENDS.get(self.backend, cv2.CAP_ANY)]
        if sys.platform.startswith("win"):
            return [cv2.CAP_DSHOW, cv2.CAP_MSMF]  # DSHOW abre bem mais rápido
        return [cv2.CAP_ANY]

    def open(self) -> None:
        for api in self._backends():
            cap = cv2.VideoCapture(self.index, api)
            if cap.isOpened():
                self.cap = cap
                break
            cap.release()
        if self.cap is None:
            raise CameraError(
                f"Câmera {self.index} não encontrada. Verifique o cabo/USB ou "
                f'altere "camera.index" no config.json (rode scripts/testar_camera.py).'
            )
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # menos atraso

        frame = None
        for _ in range(20):  # algumas câmeras demoram a "acordar"
            ok, frame = self.cap.read()
            if ok and frame is not None:
                break
            time.sleep(0.05)
        else:
            self.release()
            raise CameraError(
                f"A câmera {self.index} abriu mas não envia imagens. Ela pode estar "
                f"sendo usada por outro programa (Teams, Zoom, navegador...)."
            )
        self.actual_size = (frame.shape[1], frame.shape[0])

    def read(self) -> np.ndarray | None:
        if self.cap is None:
            return None
        ok, frame = self.cap.read()
        return frame if ok else None

    def release(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None


class FileSource(FrameSource):
    """Imagem estática (repetida) ou vídeo (em loop) — modo de teste sem câmera."""

    live = False

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.cap: cv2.VideoCapture | None = None
        self.image: np.ndarray | None = None
        self.fps = 30.0

    @property
    def description(self) -> str:
        return f"arquivo {self.path.name}"

    def open(self) -> None:
        if not self.path.exists():
            raise CameraError(f"Arquivo de vídeo/imagem não encontrado: {self.path}")
        if self.path.suffix.lower() in IMAGE_EXTS:
            # imdecode + fromfile aceita caminhos com acentos no Windows
            data = np.fromfile(str(self.path), dtype=np.uint8)
            self.image = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if self.image is None:
                raise CameraError(f"Não foi possível ler a imagem: {self.path}")
            return
        self.cap = cv2.VideoCapture(str(self.path))
        if not self.cap.isOpened():
            raise CameraError(f"Não foi possível abrir o vídeo: {self.path}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0

    def read(self) -> np.ndarray | None:
        if self.image is not None:
            return self.image.copy()
        if self.cap is None:
            return None
        ok, frame = self.cap.read()
        if not ok:  # fim do vídeo: recomeça
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        return frame if ok else None

    def release(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None


class DemoSource(FrameSource):
    """ "Câmera virtual" sobrevoando uma maquete sintética com QR Codes.

    A cada quadro a vista gira, aproxima, se afasta e inclina, permitindo
    testar detecção, perspectiva e rastreamento sem câmera física.
    """

    live = False

    def __init__(self, board: np.ndarray, width: int = 1280, height: int = 720, fps: float = 30.0) -> None:
        self.board = board
        self.width, self.height, self.fps = width, height, fps
        self.frame_index = 0

    @property
    def description(self) -> str:
        return "modo demonstração"

    def open(self) -> None:
        self.frame_index = 0

    def view_quad(self, t: float) -> np.ndarray:
        """Região da maquete vista no instante ``t`` (em pixels do tabuleiro)."""
        bh, bw = self.board.shape[:2]
        cx = bw / 2 + bw * 0.16 * math.sin(0.21 * t)
        cy = bh / 2 + bh * 0.12 * math.sin(0.33 * t + 1.0)
        zoom = 0.82 + 0.14 * math.sin(0.27 * t)
        vw = bw * zoom
        vh = vw * self.height / self.width
        angle = math.radians(14 * math.sin(0.19 * t))
        tilt = 0.18 + 0.12 * math.sin(0.23 * t)  # lado de cima "mais longe"
        local = f32(
            [
                [-vw / 2 * (1 + tilt), -vh / 2],
                [vw / 2 * (1 + tilt), -vh / 2],
                [vw / 2, vh / 2],
                [-vw / 2, vh / 2],
            ]
        )
        rot = f32([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
        return local @ rot.T + f32([cx, cy])

    def read(self) -> np.ndarray | None:
        t = self.frame_index / self.fps
        self.frame_index += 1
        dst = f32([[0, 0], [self.width, 0], [self.width, self.height], [0, self.height]])
        H = cv2.getPerspectiveTransform(self.view_quad(t), dst)
        return cv2.warpPerspective(
            self.board,
            H,
            (self.width, self.height),
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(45, 45, 45),
        )


def build_source(
    cam_cfg: dict[str, Any], source: str | int | None = None, demo_ids: list[str] | None = None
) -> FrameSource:
    """Cria a fonte a partir da configuração ou do argumento ``--source``.

    ``source`` pode ser: índice da câmera (``0``), caminho de imagem/vídeo
    ou ``"demo"``.
    """
    source = cam_cfg.get("source") if source is None else source
    width, height = int(cam_cfg.get("width", 1280)), int(cam_cfg.get("height", 720))
    fps = int(cam_cfg.get("fps", 30))
    if source is None or source == "":
        source = int(cam_cfg.get("index", 0))
    if isinstance(source, str) and source.strip().isdigit():
        source = int(source)
    if isinstance(source, int):
        return DeviceSource(source, width, height, fps, str(cam_cfg.get("backend", "auto")))
    if str(source).lower() == "demo":
        from qr.generator import build_demo_board  # import local evita ciclo

        ids = demo_ids or ["agricultura", "pecuaria", "comercio", "industria"]
        board = build_demo_board([(i, i) for i in ids])
        return DemoSource(board, width, height, fps)
    return FileSource(source)


class CameraManager:
    """Abre, lê e reconecta a fonte de vídeo sem derrubar a aplicação.

    Em vez de lançar exceções para o laço principal, guarda a última
    mensagem de erro em :attr:`error` (exibida na tela) e tenta reconectar
    periodicamente.
    """

    #: leituras falhas seguidas antes de considerar a câmera "perdida"
    MAX_FAILED_READS = 30

    def __init__(
        self,
        source: FrameSource,
        mirror: bool = False,
        reconnect_interval: float = 2.0,
        requested_size: tuple[int, int] | None = None,
    ) -> None:
        self.source = source
        self.mirror = mirror
        self.reconnect_interval = reconnect_interval
        self.requested_size = requested_size
        self.is_open = False
        self.error: str | None = None
        self.warning: str | None = None
        self._failed_reads = 0
        self._last_attempt = 0.0
        self._last_frame_time = 0.0

    def open(self) -> bool:
        """Tenta abrir a fonte. Retorna ``True`` em caso de sucesso."""
        self._last_attempt = time.monotonic()
        try:
            self.source.open()
        except CameraError as exc:
            self.is_open, self.error = False, str(exc)
            log.error("%s", exc)
            return False
        except cv2.error as exc:
            self.is_open, self.error = False, f"Erro do OpenCV ao abrir {self.source.description}: {exc}"
            log.error("%s", self.error)
            return False
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira aviso na tela; o app não pode fechar
            self.is_open, self.error = False, f"Erro ao abrir {self.source.description}: {exc}"
            log.exception("%s", self.error)
            return False
        self.is_open, self.error, self._failed_reads = True, None, 0
        self._check_resolution()
        log.info("Fonte de vídeo aberta: %s", self.source.description)
        return True

    def _check_resolution(self) -> None:
        actual = getattr(self.source, "actual_size", None)
        if self.requested_size and actual and tuple(actual) != tuple(self.requested_size):
            self.warning = (
                f"Resolução {self.requested_size[0]}x{self.requested_size[1]} não suportada; "
                f"usando {actual[0]}x{actual[1]}."
            )
            log.warning(self.warning)

    def read(self) -> np.ndarray | None:
        """Lê um quadro. Retorna ``None`` (e define :attr:`error`) em falhas."""
        if not self.is_open:
            if time.monotonic() - self._last_attempt >= self.reconnect_interval:
                self.open()
            return None
        self._pace()
        try:
            frame = self.source.read()
        except Exception as exc:  # noqa: BLE001 - cv2.error, USB removido etc.: conta como leitura falha
            log.debug("Erro de leitura: %s", exc)
            frame = None
        if frame is None or frame.size == 0:
            self._failed_reads += 1
            if self._failed_reads >= self.MAX_FAILED_READS:
                self.error = f"Sem imagem de {self.source.description}. Tentando reconectar..."
                log.error(self.error)
                self.release()
            return None
        self._failed_reads = 0
        self.error = None
        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        return cv2.flip(frame, 1) if self.mirror else frame

    def _pace(self) -> None:
        """Para arquivos/demonstração, limita a velocidade ao FPS da fonte."""
        if self.source.live:
            return
        interval = 1.0 / float(getattr(self.source, "fps", 30.0) or 30.0)
        wait = self._last_frame_time + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_frame_time = time.monotonic()

    def release(self) -> None:
        self.source.release()
        self.is_open = False
