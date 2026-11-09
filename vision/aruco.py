"""Marcadores ArUco: referência espacial (posição e orientação).

QR Code  -> diz **o que** é o elemento (texto/identificador).
ArUco    -> diz **onde** está e **como está orientado** (pose 3D estável).

Marcadores ArUco são mais simples que QR Codes (poucos "pixels"), por isso
são detectados mais longe, mais rápido e com cantos mais precisos — ideais
para servir de âncora para objetos 3D nas próximas fases.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

from camera.calibration import CameraCalibration

log = logging.getLogger(__name__)


@dataclass
class ArucoMarker:
    """Um marcador ArUco detectado (cantos na ordem TL, TR, BR, BL)."""

    marker_id: int
    corners: np.ndarray
    rvec: np.ndarray | None = None  # orientação (vetor de Rodrigues)
    tvec: np.ndarray | None = None  # posição em metros, no referencial da câmera

    @property
    def center(self) -> tuple[float, float]:
        cx, cy = self.corners.mean(axis=0)
        return float(cx), float(cy)

    @property
    def distance_m(self) -> float | None:
        return float(np.linalg.norm(self.tvec)) if self.tvec is not None else None

    @property
    def euler_deg(self) -> tuple[float, float, float] | None:
        """Ângulos (x, y, z) em graus derivados de ``rvec``."""
        if self.rvec is None:
            return None
        R, _ = cv2.Rodrigues(self.rvec)
        sy = float(np.hypot(R[0, 0], R[1, 0]))
        x = np.degrees(np.arctan2(R[2, 1], R[2, 2]))
        y = np.degrees(np.arctan2(-R[2, 0], sy))
        z = np.degrees(np.arctan2(R[1, 0], R[0, 0]))
        return float(x), float(y), float(z)


class ArucoDetector:
    """Detecta marcadores ArUco e estima a pose de cada um.

    Args:
        dictionary: nome do dicionário (ex.: ``"DICT_4X4_50"``).
        marker_length_m: lado do marcador impresso, em metros.
    """

    def __init__(self, dictionary: str = "DICT_4X4_50", marker_length_m: float = 0.04) -> None:
        dict_id = getattr(cv2.aruco, dictionary, None)
        if dict_id is None:
            log.warning("Dicionário ArUco '%s' desconhecido; usando DICT_4X4_50.", dictionary)
            dict_id = cv2.aruco.DICT_4X4_50
        self.dictionary = cv2.aruco.getPredefinedDictionary(dict_id)
        self._detector = cv2.aruco.ArucoDetector(self.dictionary, cv2.aruco.DetectorParameters())
        self.marker_length_m = float(marker_length_m)
        half = self.marker_length_m / 2
        # cantos do marcador no seu próprio referencial 3D (plano z = 0)
        self._object_points = np.array(
            [[-half, half, 0], [half, half, 0], [half, -half, 0], [-half, -half, 0]], np.float32
        )

    def detect(self, frame: np.ndarray, calibration: CameraCalibration | None = None) -> list[ArucoMarker]:
        """Detecta os marcadores e, se houver calibração, estima a pose."""
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Marcadores ArUco são simples: dá para procurar numa imagem menor
        # (bem mais rápido) e depois refinar os cantos na imagem original.
        scale = min(1.0, 640.0 / max(gray.shape[1], 1))
        small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
        try:
            corners, ids, _ = self._detector.detectMarkers(small)
        except cv2.error as exc:
            log.debug("Falha na detecção ArUco: %s", exc)
            return []
        if ids is None:
            return []
        markers = []
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.05)
        for c, marker_id in zip(corners, ids.ravel(), strict=True):
            pts = np.asarray(c, np.float32).reshape(-1, 1, 2) / scale
            if scale < 1:
                pts = cv2.cornerSubPix(gray, pts, (5, 5), (-1, -1), criteria)
            m = ArucoMarker(int(marker_id), pts.reshape(4, 2))
            if calibration is not None:
                self.estimate_pose(m, calibration)
            markers.append(m)
        return markers

    def estimate_pose(self, marker: ArucoMarker, calibration: CameraCalibration) -> bool:
        """Calcula ``rvec``/``tvec`` do marcador com ``cv2.solvePnP``."""
        ok, rvec, tvec = cv2.solvePnP(
            self._object_points,
            marker.corners,
            calibration.camera_matrix,
            calibration.dist_coeffs,
            flags=cv2.SOLVEPNP_IPPE_SQUARE,
        )
        if ok:
            marker.rvec, marker.tvec = rvec, tvec
        return bool(ok)

    def draw(self, frame: np.ndarray, markers: list[ArucoMarker], calibration: CameraCalibration | None = None) -> None:
        """Desenha contorno, ID e eixos 3D (X vermelho, Y verde, Z azul)."""
        for m in markers:
            pts = m.corners.astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(frame, [pts], True, (255, 0, 255), 2, cv2.LINE_AA)
            cx, cy = map(int, m.center)
            cv2.putText(
                frame,
                f"ArUco {m.marker_id}",
                (cx - 40, cy - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 0, 255),
                1,
                cv2.LINE_AA,
            )
            if calibration is not None and m.rvec is not None and m.tvec is not None:
                cv2.drawFrameAxes(
                    frame,
                    calibration.camera_matrix,
                    calibration.dist_coeffs,
                    m.rvec,
                    m.tvec,
                    self.marker_length_m * 0.75,
                    2,
                )

    def generate(self, marker_id: int, size_px: int = 400) -> np.ndarray:
        """Gera a imagem de um marcador (com borda branca) para impressão."""
        img = cv2.aruco.generateImageMarker(self.dictionary, marker_id, size_px)
        border = size_px // 8
        return cv2.copyMakeBorder(img, border, border, border, border, cv2.BORDER_CONSTANT, value=255)
