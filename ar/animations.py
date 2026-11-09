"""Animações simples baseadas em tempo (Fase 1: fade-in/fade-out).

Cada animação é uma função do tempo decorrido que devolve um valor entre
0 e 1. Na Fase 3 novas animações (pulsar, deslizar, sprites, vídeos)
podem ser adicionadas aqui sem alterar o restante do código.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod


def ease_out_cubic(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1.0 - (1.0 - x) ** 3


class Animation(ABC):
    """Animação parametrizada pelo tempo decorrido (segundos)."""

    def __init__(self, duration: float) -> None:
        self.duration = max(float(duration), 1e-6)

    @abstractmethod
    def value(self, elapsed: float) -> float:
        """Valor da animação (normalmente entre 0 e 1)."""


class FadeIn(Animation):
    """0 → 1 com suavização no final."""

    def value(self, elapsed: float) -> float:
        return ease_out_cubic(elapsed / self.duration)


class FadeOut(Animation):
    """1 → 0 linear."""

    def value(self, elapsed: float) -> float:
        return 1.0 - min(max(elapsed / self.duration, 0.0), 1.0)


class Pulse(Animation):
    """Oscila suavemente entre ``low`` e 1 (período = ``duration``)."""

    def __init__(self, duration: float = 1.0, low: float = 0.4) -> None:
        super().__init__(duration)
        self.low = low

    def value(self, elapsed: float) -> float:
        s = 0.5 + 0.5 * math.sin(2 * math.pi * elapsed / self.duration)
        return self.low + (1.0 - self.low) * s
