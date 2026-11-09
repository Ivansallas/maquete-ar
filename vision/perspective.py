"""Homografia e transformação de perspectiva para "colar" conteúdo no QR.

Ideia central
-------------
O QR Code é um quadrado conhecido. Definimos um sistema de coordenadas
do próprio marcador em que o QR ocupa o quadrado unitário
``(0,0)-(1,1)``. A homografia ``H`` leva esse quadrado aos quatro cantos
vistos na câmera. Qualquer ponto "no plano da maquete" (por exemplo, o
retângulo do painel logo acima do QR) pode então ser projetado na imagem
com a mesma ``H`` — por isso o painel inclina, gira e escala junto com o QR.
"""

from __future__ import annotations

import cv2
import numpy as np


def f32(points: object) -> np.ndarray:
    """Converte listas de pontos em ``ndarray`` float32 (formato do OpenCV)."""
    return np.asarray(points, dtype=np.float32)


UNIT_SQUARE = f32([[0, 0], [1, 0], [1, 1], [0, 1]])


def marker_homography(corners: np.ndarray) -> np.ndarray:
    """Homografia do quadrado unitário (plano do marcador) para a imagem."""
    return cv2.getPerspectiveTransform(UNIT_SQUARE, np.asarray(corners, np.float32).reshape(4, 2))


def project_points(H: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Aplica a homografia ``H`` a uma lista de pontos ``(N, 2)``."""
    pts = np.asarray(points, np.float32).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, H).reshape(-1, 2)


def rect_corners(w: float, h: float, x: float = 0.0, y: float = 0.0) -> np.ndarray:
    """Cantos de um retângulo na ordem TL, TR, BR, BL."""
    return f32([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])


def quad_is_valid(quad: np.ndarray, frame_shape: tuple[int, ...], max_scale: float = 4.0) -> bool:
    """Rejeita projeções degeneradas (cruzadas, minúsculas ou gigantes)."""
    quad = np.asarray(quad, np.float32).reshape(4, 2)
    if not np.all(np.isfinite(quad)):
        return False
    if not cv2.isContourConvex(quad.reshape(-1, 1, 2)):
        return False
    area = cv2.contourArea(quad)
    h, w = frame_shape[:2]
    return 25.0 < area < (w * h) * max_scale


def warp_onto(frame: np.ndarray, overlay_bgra: np.ndarray, dst_quad: np.ndarray, opacity: float = 1.0) -> bool:
    """Deforma ``overlay_bgra`` para ``dst_quad`` e mistura sobre ``frame``.

    Só a região do quadro coberta pelo quadrilátero é processada, o que
    mantém o custo baixo mesmo com vários painéis na tela.
    Retorna ``False`` se nada foi desenhado.
    """
    fh, fw = frame.shape[:2]
    dst = np.asarray(dst_quad, np.float32).reshape(4, 2)
    x0, y0 = np.floor(dst.min(axis=0)).astype(int)
    x1, y1 = np.ceil(dst.max(axis=0)).astype(int)
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, fw), min(y1, fh)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return False
    oh, ow = overlay_bgra.shape[:2]
    M = cv2.getPerspectiveTransform(rect_corners(ow, oh), dst - f32([x0, y0]))
    warped = cv2.warpPerspective(
        overlay_bgra,
        M,
        (x1 - x0, y1 - y0),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    alpha_blend(frame[y0:y1, x0:x1], warped, opacity)
    return True


def alpha_blend(roi: np.ndarray, overlay_bgra: np.ndarray, opacity: float = 1.0) -> None:
    """Mistura ``overlay_bgra`` sobre ``roi`` (mesmo tamanho), no próprio ``roi``.

    Usa ``cv2.blendLinear`` (C++), bem mais rápido que a conta em NumPy.
    """
    w_fg = overlay_bgra[:, :, 3].astype(np.float32) * (opacity / 255.0)
    w_bg = 1.0 - w_fg
    w_bg += 1e-6  # evita divisão por zero dentro do blendLinear
    roi[:] = cv2.blendLinear(np.ascontiguousarray(overlay_bgra[:, :, :3]), roi, w_fg, w_bg)


def perspective_info(corners: np.ndarray) -> dict[str, float]:
    """Medidas simples de inclinação do QR (para o modo DEBUG).

    ``skew_x``/``skew_y`` comparam lados opostos: 1.0 = de frente para a
    câmera; valores maiores indicam que o QR está inclinado.
    """
    c = np.asarray(corners, np.float32).reshape(4, 2)
    top, bottom = np.linalg.norm(c[1] - c[0]), np.linalg.norm(c[2] - c[3])
    left, right = np.linalg.norm(c[3] - c[0]), np.linalg.norm(c[2] - c[1])
    eps = 1e-6
    return {
        "skew_x": float(max(top, bottom) / (min(top, bottom) + eps)),
        "skew_y": float(max(left, right) / (min(left, right) + eps)),
        "area": float(cv2.contourArea(c)),
    }
