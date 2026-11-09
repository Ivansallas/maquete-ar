"""Arquivos de mídia referenciados pelo conteúdo (Fase 2: imagens; Fase 3: animações).

Segurança: o caminho vem de um JSON editável, então é tratado como entrada
não confiável. Ele é sempre resolvido **dentro** da pasta ``assets/``;
caminhos absolutos ou que escapam da pasta (``../``) são rejeitados.
Falhas de leitura viram :class:`AssetError` para quem chamou decidir o
que fazer (o painel cai para "só texto"; a aplicação nunca fecha).
"""

from __future__ import annotations

import bisect
import itertools
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import cv2
import numpy as np
from PIL import Image, ImageSequence

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
#: GIF, WebP animado e APNG (PNG animado). Um arquivo estático vira animação de 1 quadro.
ANIMATION_EXTS = {".gif", ".webp", ".png"}
#: Arquivos maiores que isso nem são lidos (protege a memória/tempo de abertura).
MAX_IMAGE_BYTES = 15 * 1024 * 1024
#: Memória máxima dos quadros decodificados de uma animação. Animações mais
#: longas são cortadas (o loop fica mais curto) em vez de esgotar a memória.
MAX_ANIMATION_DECODED_BYTES = 96 * 1024 * 1024
MAX_ANIMATION_FRAMES = 300
#: Duração usada para quadros com duração 0 ou muito curta (mesma regra dos navegadores).
DEFAULT_FRAME_SECONDS = 0.1


class AssetError(ValueError):
    """Arquivo de mídia inválido, inexistente ou fora de ``assets/``."""


def resolve_asset(assets_dir: str | Path, relative: str, exts: set[str] = IMAGE_EXTS) -> Path:
    """Converte o caminho do JSON (ex.: ``"images/trator.png"``) num caminho seguro.

    Aceita ``\\`` ou ``/`` e um prefixo ``assets/`` opcional (o professor pode
    escrever o caminho a partir da raiz do projeto, por costume).
    """
    root = Path(assets_dir).resolve()
    text = relative.strip().replace("\\", "/")
    if not text:
        raise AssetError("caminho de arquivo vazio")
    if text.startswith("/") or PurePosixPath(text).is_absolute() or ":" in text:
        raise AssetError(f"use um caminho relativo à pasta assets/, não '{relative}'")
    parts = PurePosixPath(text).parts
    if parts and parts[0] == "assets":
        parts = parts[1:]
    path = root.joinpath(*parts).resolve()
    if not path.is_relative_to(root):
        raise AssetError(f"'{relative}' aponta para fora da pasta assets/")
    if path.suffix.lower() not in exts:
        raise AssetError(f"'{relative}': formato não suportado (use {', '.join(sorted(exts))})")
    if not path.is_file():
        raise AssetError(f"'{relative}' não encontrado em assets/")
    return path


def load_image(path: str | Path, max_side: int = 1024) -> np.ndarray:
    """Lê uma imagem como BGRA ``uint8``, reduzindo-a se for maior que ``max_side``.

    ``np.fromfile`` + ``cv2.imdecode`` funciona com acentos no caminho (Windows).
    """
    path = Path(path)
    try:
        if path.stat().st_size > MAX_IMAGE_BYTES:
            raise AssetError(f"'{path.name}' é grande demais (máx. {MAX_IMAGE_BYTES // 2**20} MB)")
        data = np.fromfile(str(path), dtype=np.uint8)
    except OSError as exc:
        raise AssetError(f"não foi possível ler '{path.name}': {exc}") from exc
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None or img.size == 0:
        raise AssetError(f"'{path.name}' não é uma imagem válida")
    img = _to_bgra_u8(img)
    h, w = img.shape[:2]
    scale = max_side / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def _to_bgra_u8(img: np.ndarray) -> np.ndarray:
    if img.dtype == np.uint16:  # PNG de 16 bits
        img = (img >> 8).astype(np.uint8)
    elif img.dtype != np.uint8:
        raise AssetError(f"tipo de imagem não suportado ({img.dtype})")
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    channels = img.shape[2]
    if channels == 4:
        return img
    if channels == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    if channels == 1:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    raise AssetError(f"imagem com {channels} canais não suportada")


@dataclass
class AnimatedImage:
    """Quadros BGRA de uma animação e a duração (s) de cada um; toca em loop."""

    frames: list[np.ndarray]
    durations: list[float]
    _ends: list[float] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.frames or len(self.frames) != len(self.durations):
            raise AssetError("animação sem quadros")
        self._ends = list(itertools.accumulate(self.durations))

    @property
    def total(self) -> float:
        return self._ends[-1]

    def frame_index(self, elapsed: float) -> int:
        """Índice do quadro a mostrar ``elapsed`` segundos após o início."""
        if elapsed <= 0 or len(self.frames) == 1:
            return 0
        # +1e-9: as somas acumuladas têm erro de ponto flutuante (0.1 + 0.2 != 0.3)
        index = bisect.bisect_right(self._ends, elapsed % self.total + 1e-9)
        return min(index, len(self.frames) - 1)


def load_animation(
    path: str | Path,
    max_side: int = 640,
    max_bytes: int = MAX_ANIMATION_DECODED_BYTES,
    max_frames: int = MAX_ANIMATION_FRAMES,
) -> AnimatedImage:
    """Lê um GIF/WebP/APNG com o Pillow (que já compõe cada quadro completo).

    Quadros maiores que ``max_side`` são reduzidos. Se a animação passar de
    ``max_bytes`` decodificados ou ``max_frames``, o restante é ignorado.
    """
    path = Path(path)
    frames: list[np.ndarray] = []
    durations: list[float] = []
    used = 0
    try:
        if path.stat().st_size > MAX_IMAGE_BYTES:
            raise AssetError(f"'{path.name}' é grande demais (máx. {MAX_IMAGE_BYTES // 2**20} MB)")
        with Image.open(path) as im:
            for frame in ImageSequence.Iterator(im):
                rgba = frame.convert("RGBA")
                rgba.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
                size = rgba.width * rgba.height * 4
                if frames and (used + size > max_bytes or len(frames) >= max_frames):
                    break
                used += size
                ms = float(frame.info.get("duration") or 0)
                durations.append(ms / 1000 if ms > 10 else DEFAULT_FRAME_SECONDS)
                frames.append(np.array(rgba)[:, :, [2, 1, 0, 3]].copy())  # RGBA -> BGRA
    # O Pillow sinaliza arquivos ruins com exceções variadas (truncado, formato
    # desconhecido, "bomba" de descompressão...): todas viram AssetError.
    except AssetError:
        raise
    except (OSError, ValueError, EOFError, SyntaxError, Image.DecompressionBombError) as exc:
        raise AssetError(f"'{path.name}' não é uma animação válida ({exc})") from exc
    return AnimatedImage(frames, durations)
