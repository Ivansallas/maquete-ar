"""Parâmetros intrínsecos da câmera (necessários para estimar pose 3D).

Sem calibração usamos uma aproximação razoável (distância focal ≈ largura
da imagem, sem distorção). Ela basta para desenhar eixos sobre ArUco; para
medidas precisas, calibre com um tabuleiro de xadrez impresso usando
:func:`calibrate_from_chessboard` e salve o resultado com :meth:`save`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class CameraCalibration:
    """Matriz da câmera ``K`` (3x3) e coeficientes de distorção."""

    camera_matrix: np.ndarray
    dist_coeffs: np.ndarray
    approximate: bool = True

    @classmethod
    def approximate_for(cls, width: int, height: int) -> CameraCalibration:
        f = float(width)
        K = np.array([[f, 0, width / 2], [0, f, height / 2], [0, 0, 1]], np.float64)
        return cls(K, np.zeros((5, 1), np.float64), approximate=True)

    @classmethod
    def load(cls, path: str | Path, frame_size: tuple[int, int]) -> CameraCalibration:
        """Lê a calibração do arquivo; se não existir, usa a aproximação."""
        path = Path(path)
        width, height = frame_size
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                K = np.array(data["camera_matrix"], np.float64).reshape(3, 3)
                dist = np.array(data["dist_coeffs"], np.float64).reshape(-1, 1)
                calib_w, calib_h = data.get("width", width), data.get("height", height)
                if (calib_w, calib_h) != (width, height):  # ajusta à resolução atual
                    K[0] *= width / calib_w
                    K[1] *= height / calib_h
                return cls(K, dist, approximate=False)
            # TypeError/ZeroDivisionError: largura/altura ausentes, texto ou zero no JSON
            except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
                log.warning("Calibração inválida em '%s' (%s); usando aproximação.", path, exc)
        return cls.approximate_for(width, height)

    def save(self, path: str | Path, frame_size: tuple[int, int]) -> None:
        data = {
            "width": frame_size[0],
            "height": frame_size[1],
            "camera_matrix": self.camera_matrix.tolist(),
            "dist_coeffs": self.dist_coeffs.ravel().tolist(),
        }
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def calibrate_from_chessboard(
    images: Iterable[np.ndarray],
    pattern: tuple[int, int] = (9, 6),
    square_size_m: float = 0.025,
) -> tuple[CameraCalibration, float]:
    """Calibra a câmera a partir de fotos de um tabuleiro de xadrez.

    Args:
        images: fotos (BGR) do tabuleiro em posições/ângulos variados (~15).
        pattern: número de cantos *internos* (colunas, linhas).
        square_size_m: lado de cada quadrado impresso, em metros.

    Returns:
        A calibração e o erro de reprojeção RMS (bom quando < 1 pixel).
    """
    objp = np.zeros((pattern[0] * pattern[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0 : pattern[0], 0 : pattern[1]].T.reshape(-1, 2) * square_size_m
    obj_points, img_points, size = [], [], None
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-3)
    for img in images:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        size = gray.shape[::-1]
        ok, corners = cv2.findChessboardCorners(gray, pattern)
        if ok:
            corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            obj_points.append(objp)
            img_points.append(corners)
    if len(obj_points) < 3 or size is None:
        raise ValueError("Tabuleiro encontrado em menos de 3 imagens.")
    rms, K, dist, _, _ = cv2.calibrateCamera(obj_points, img_points, size, None, None)
    return CameraCalibration(K, dist, approximate=False), float(rms)
