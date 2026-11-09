"""Detecção e decodificação de QR Codes com o detector nativo do OpenCV.

Escolhemos o detector do próprio OpenCV (em vez do PyZBar) porque ele não
exige a instalação da biblioteca nativa ``zbar`` e já devolve os quatro
cantos de cada QR, inclusive inclinado ou em perspectiva.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from qr.markers import QRMarker

log = logging.getLogger(__name__)


class QRCodeDetector:
    """Encontra e lê vários QR Codes em um quadro.

    Para cada QR retorna um :class:`QRMarker` com texto, quatro cantos,
    centro, bounding box e situação (válido, inválido ou ilegível).

    Args:
        backend: ``"aruco"`` usa ``cv2.QRCodeDetectorAruco`` (mais robusto,
            OpenCV >= 4.8); ``"classic"`` usa ``cv2.QRCodeDetector``;
            ``"auto"`` escolhe o melhor disponível.
        detect_scale: fator de redução da imagem antes da detecção
            (ex.: 0.5 deixa a detecção ~4x mais rápida, mas QRs pequenos
            podem deixar de ser lidos). Os cantos retornados sempre estão
            nas coordenadas da imagem original.
    """

    def __init__(self, backend: str = "auto", detect_scale: float = 1.0) -> None:
        self.detect_scale = float(min(max(detect_scale, 0.2), 1.0))
        use_aruco = backend in ("auto", "aruco") and hasattr(cv2, "QRCodeDetectorAruco")
        if backend == "aruco" and not use_aruco:
            log.warning("cv2.QRCodeDetectorAruco indisponível; usando detector clássico.")
        self.backend = "aruco" if use_aruco else "classic"
        self._detector = cv2.QRCodeDetectorAruco() if use_aruco else cv2.QRCodeDetector()

    def detect(self, frame: np.ndarray) -> list[QRMarker]:
        """Detecta todos os QR Codes do quadro. Nunca lança exceção do OpenCV."""
        if frame is None or frame.size == 0:
            return []
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        scale = self.detect_scale
        if scale < 1.0:
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        try:
            found, texts, points, _ = self._detector.detectAndDecodeMulti(gray)
        except cv2.error as exc:  # quadros corrompidos/resolução estranha
            log.debug("Falha na detecção de QR: %s", exc)
            return []
        if not found or points is None:
            return []

        markers: list[QRMarker] = []
        for text, pts in zip(texts, points, strict=True):
            pts = np.asarray(pts, dtype=np.float32).reshape(4, 2) / scale
            if not np.all(np.isfinite(pts)):
                continue
            markers.append(QRMarker.from_detection(text or "", pts))
        return markers
