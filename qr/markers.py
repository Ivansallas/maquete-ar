"""Estrutura de dados de um QR Code detectado e validação do texto lido."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from core.content import ID_PATTERN

#: Textos maiores que isso nem são considerados identificadores.
MAX_QR_TEXT = 64


class MarkerStatus(StrEnum):
    """Situação de um QR Code encontrado na imagem."""

    OK = "ok"  # texto lido e com formato de identificador válido
    INVALID = "invalid"  # texto lido, mas não é um identificador (ex.: URL)
    UNREADABLE = "unreadable"  # QR localizado, mas não decodificado (parcial/borrado)


def normalize_qr_text(raw: str | None) -> str | None:
    """Transforma o texto do QR em um identificador seguro, ou ``None``.

    Apenas ``[a-z0-9_]`` é aceito. Assim um QR com comandos, caminhos
    (``../``), URLs ou qualquer outro conteúdo é simplesmente rejeitado.
    """
    if not raw or len(raw) > MAX_QR_TEXT:
        return None
    text = raw.strip().lower()
    return text if ID_PATTERN.fullmatch(text) else None


@dataclass
class QRMarker:
    """Um QR Code encontrado em um quadro de vídeo.

    ``corners`` tem forma ``(4, 2)`` na ordem do próprio QR:
    superior-esquerdo, superior-direito, inferior-direito, inferior-esquerdo.
    Como a ordem acompanha o QR, girar o QR também gira o conteúdo de AR.
    """

    text: str
    corners: np.ndarray
    element_id: str | None = None
    status: MarkerStatus = MarkerStatus.UNREADABLE

    @classmethod
    def from_detection(cls, text: str, corners: np.ndarray) -> QRMarker:
        corners = np.asarray(corners, dtype=np.float32).reshape(4, 2)
        if not text:
            return cls(text="", corners=corners, status=MarkerStatus.UNREADABLE)
        element_id = normalize_qr_text(text)
        status = MarkerStatus.OK if element_id else MarkerStatus.INVALID
        return cls(text=text, corners=corners, element_id=element_id, status=status)

    @property
    def center(self) -> tuple[float, float]:
        cx, cy = self.corners.mean(axis=0)
        return float(cx), float(cy)

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """Retângulo alinhado aos eixos: ``(x, y, largura, altura)``."""
        x0, y0 = self.corners.min(axis=0)
        x1, y1 = self.corners.max(axis=0)
        return int(x0), int(y0), int(round(x1 - x0)), int(round(y1 - y0))

    @property
    def size(self) -> tuple[float, float]:
        """Largura e altura médias do QR (média dos lados opostos), em pixels."""
        c = self.corners
        w = (np.linalg.norm(c[1] - c[0]) + np.linalg.norm(c[2] - c[3])) / 2
        h = (np.linalg.norm(c[3] - c[0]) + np.linalg.norm(c[2] - c[1])) / 2
        return float(w), float(h)

    @property
    def angle(self) -> float:
        """Rotação no plano da imagem, em graus (borda superior do QR)."""
        dx, dy = self.corners[1] - self.corners[0]
        return math.degrees(math.atan2(dy, dx))

    @property
    def label(self) -> str:
        """Texto curto para exibição (id, texto bruto ou '?')."""
        if self.element_id:
            return self.element_id
        if self.text:
            return self.text[:24] + ("…" if len(self.text) > 24 else "")
        return "?"
