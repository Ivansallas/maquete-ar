"""Arquivos de mídia referenciados pelo conteúdo (Fase 2: imagens).

Segurança: o caminho vem de um JSON editável, então é tratado como entrada
não confiável. Ele é sempre resolvido **dentro** da pasta ``assets/``;
caminhos absolutos ou que escapam da pasta (``../``) são rejeitados.
Falhas de leitura viram :class:`AssetError` para quem chamou decidir o
que fazer (o painel cai para "só texto"; a aplicação nunca fecha).
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import cv2
import numpy as np

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
#: Arquivos maiores que isso nem são lidos (protege a memória/tempo de abertura).
MAX_IMAGE_BYTES = 15 * 1024 * 1024


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
