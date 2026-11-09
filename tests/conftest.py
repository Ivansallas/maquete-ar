"""Configuração comum dos testes: raiz do projeto no sys.path e utilitários."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qr.generator import QRCodeGenerator  # noqa: E402


@pytest.fixture(scope="session")
def generator() -> QRCodeGenerator:
    return QRCodeGenerator(box_size=8, border=4)


def make_scene(
    generator: QRCodeGenerator, ids: list[str], size: tuple[int, int] = (1280, 720), qr_px: int = 220
) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Cena cinza com QRs lado a lado. Retorna a imagem e os centros esperados."""
    w, h = size
    scene = np.full((h, w, 3), 128, np.uint8)
    centers = []
    step = w // max(len(ids), 1)
    for i, data in enumerate(ids):
        qr = cv2.resize(np.array(generator.make_qr(data)), (qr_px, qr_px), interpolation=cv2.INTER_NEAREST)
        x = i * step + (step - qr_px) // 2
        y = (h - qr_px) // 2
        scene[y : y + qr_px, x : x + qr_px] = cv2.cvtColor(qr, cv2.COLOR_GRAY2BGR)
        centers.append((x + qr_px // 2, y + qr_px // 2))
    return scene, centers
