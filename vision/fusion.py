"""Fusão QR + ArUco (Fase 4): um ArUco colado ao lado de cada QR.

O QR diz **o que** é o elemento, mas só é lido de perto e de frente. O
ArUco é bem mais simples: é detectado de mais longe, em ângulos maiores e
com cantos mais precisos. Cada elemento tem um ArUco (campo ``"aruco"`` do
JSON), então o ArUco sozinho também identifica o elemento.

Aprendizado automático (sem calibração)
---------------------------------------
Quando o QR e o ArUco de um elemento aparecem juntos, guardamos onde
ficam os cantos do QR **no sistema de coordenadas do ArUco** (o ArUco é o
quadrado unitário, como em :mod:`vision.perspective`). Como os dois estão
colados no mesmo plano, essa relação não muda. Depois, se o QR ficar
ilegível, coberto ou longe demais, projetamos esses cantos com a
homografia do ArUco e "recriamos" o QR no lugar certo — o resto do
pipeline (rastreamento, painéis) nem percebe a diferença.

Antes de aprender, usamos o próprio quadrado do ArUco como posição.
"""

from __future__ import annotations

import cv2
import numpy as np

from qr.markers import MarkerStatus, QRMarker
from vision.aruco import ArucoMarker
from vision.perspective import UNIT_SQUARE, marker_homography, project_points

#: Distância máxima (em lados do ArUco) entre o ArUco e os cantos do QR para
#: aceitar o aprendizado. Evita aprender com uma associação errada (ex.: dois
#: elementos iguais na mesa ou um ArUco bem longe do QR).
MAX_LEARN_DISTANCE = 8.0


class MarkerFusion:
    """Completa as detecções de QR com os ArUcos dos elementos.

    Args:
        aruco_map: id do ArUco -> id do elemento (``ContentManager.aruco_map``).
        smoothing: média móvel do aprendizado (0 = só a última observação).
    """

    def __init__(self, aruco_map: dict[int, str], smoothing: float = 0.8) -> None:
        self.aruco_map = dict(aruco_map)
        self.smoothing = float(min(max(smoothing, 0.0), 0.99))
        #: elemento -> cantos do QR no espaço do ArUco (4x2)
        self.learned: dict[str, np.ndarray] = {}

    def update(self, qr_markers: list[QRMarker], aruco_markers: list[ArucoMarker]) -> list[QRMarker]:
        """Devolve as detecções de QR + marcadores recriados a partir dos ArUcos."""
        known = [a for a in aruco_markers if a.marker_id in self.aruco_map]
        read_ids = {m.element_id for m in qr_markers if m.status == MarkerStatus.OK}
        by_element = {self.aruco_map[a.marker_id]: a for a in known}

        for m in qr_markers:  # QR e ArUco do mesmo elemento visíveis: aprende
            if m.status == MarkerStatus.OK and m.element_id in by_element:
                self._learn(m.element_id, m.corners, by_element[m.element_id])

        out = list(qr_markers)
        for element_id, a in by_element.items():
            if element_id in read_ids:
                continue  # o QR foi lido: ele manda
            corners = project_points(marker_homography(a.corners), self.learned.get(element_id, UNIT_SQUARE))
            if not np.all(np.isfinite(corners)):
                continue
            synthetic = QRMarker(element_id, corners.astype(np.float32), element_id, MarkerStatus.OK, via_aruco=True)
            # um QR "ilegível" exatamente onde o QR deste elemento deveria estar é o
            # próprio QR (borrado/longe): o ArUco já o identificou, então ele sai
            out = [m for m in out if not (m.status == MarkerStatus.UNREADABLE and _inside(m.center, corners))]
            out.append(synthetic)
        return out

    def _learn(self, element_id: str, qr_corners: np.ndarray, a: ArucoMarker) -> None:
        H = marker_homography(a.corners)
        try:
            local = project_points(np.linalg.inv(H), qr_corners)
        except np.linalg.LinAlgError:
            return
        if not np.all(np.isfinite(local)) or np.abs(local - 0.5).max() > MAX_LEARN_DISTANCE:
            return
        prev = self.learned.get(element_id)
        self.learned[element_id] = local if prev is None else self.smoothing * prev + (1 - self.smoothing) * local


def _inside(point: tuple[float, float], quad: np.ndarray) -> bool:
    return cv2.pointPolygonTest(quad.reshape(-1, 1, 2).astype(np.float32), point, False) >= 0
