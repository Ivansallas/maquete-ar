"""Interface para reconhecimento de objetos (Fase 5 — ex.: YOLO).

Hoje existe apenas a interface e uma implementação "nula". Na Fase 5
basta criar, por exemplo, ``YoloObjectDetector(ObjectDetector)`` em um
novo arquivo e selecioná-lo pela configuração — o restante da aplicação
(rastreamento, renderização) continua igual.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

#: Classes que pretendemos reconhecer na maquete.
TARGET_CLASSES = ("trator", "carro", "casa", "animal", "arvore", "plantacao", "industria")


@dataclass
class DetectedObject:
    """Objeto reconhecido em um quadro."""

    label: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x, y, largura, altura

    @property
    def center(self) -> tuple[float, float]:
        x, y, w, h = self.bbox
        return x + w / 2, y + h / 2


class ObjectDetector(ABC):
    """Contrato de qualquer detector de objetos usado pela aplicação."""

    @abstractmethod
    def detect(self, frame: np.ndarray) -> list[DetectedObject]:
        """Retorna os objetos encontrados no quadro BGR."""

    def close(self) -> None:  # noqa: B027 - implementação opcional
        """Libera recursos (modelos, GPU...)."""


class NullObjectDetector(ObjectDetector):
    """Implementação vazia usada enquanto o YOLO não é integrado."""

    def detect(self, frame: np.ndarray) -> list[DetectedObject]:
        return []
