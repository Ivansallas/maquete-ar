"""Desenho de textos e painéis (com acentos e emoji) usando Pillow.

O ``cv2.putText`` do OpenCV não desenha acentos ("Pecuária") nem emoji,
por isso os textos são desenhados com Pillow e convertidos para NumPy.
"""

from __future__ import annotations

import contextlib
import logging
import sys
from functools import lru_cache
from pathlib import Path
from typing import cast

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from core.content import ElementContent
from vision.perspective import alpha_blend

log = logging.getLogger(__name__)

Color = tuple[int, int, int]

_WIN_FONTS = Path("C:/Windows/Fonts")
_FONT_CANDIDATES = {
    "regular": [
        _WIN_FONTS / "segoeui.ttf",
        _WIN_FONTS / "arial.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    ],
    "bold": [
        _WIN_FONTS / "segoeuib.ttf",
        _WIN_FONTS / "arialbd.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/Library/Fonts/Arial Bold.ttf"),
    ],
    "emoji": [
        _WIN_FONTS / "seguiemj.ttf",
        Path("/System/Library/Fonts/Apple Color Emoji.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
        Path("/usr/share/fonts/noto/NotoColorEmoji.ttf"),
    ],
}


@lru_cache(maxsize=64)
def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Carrega uma fonte TrueType do sistema (com fallback para a padrão)."""
    for path in _FONT_CANDIDATES["bold" if bold else "regular"]:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    log.warning("Nenhuma fonte TrueType encontrada; usando fonte padrão do Pillow.")
    return cast(ImageFont.FreeTypeFont, ImageFont.load_default(size))


@lru_cache(maxsize=16)
def load_emoji_font(size: int) -> ImageFont.FreeTypeFont | None:
    """Fonte de emoji colorido, ou ``None`` se o sistema não tiver uma."""
    for path in _FONT_CANDIDATES["emoji"]:
        if not path.exists():
            continue
        try:
            font = ImageFont.truetype(str(path), size)
            # Testa se a fonte desenha nesse tamanho (Noto só aceita 109 px).
            ImageDraw.Draw(Image.new("RGBA", (8, 8))).text((0, 0), "🌱", font=font, embedded_color=True)
            return font
        except OSError:
            continue
    return None


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """Quebra o texto em linhas que caibam em ``max_width`` pixels."""
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}".strip()
            if font.getlength(candidate) <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _rgb(bgr: Color) -> tuple[int, int, int]:
    return bgr[2], bgr[1], bgr[0]


#: Altura máxima da imagem no painel, em fração da largura do painel
#: (imagens muito altas deixariam o painel grande demais para a tela).
PICTURE_MAX_HEIGHT = 0.42


def render_panel(content: ElementContent, width: int = 640, picture: np.ndarray | None = None) -> np.ndarray:
    """Cria a imagem BGRA do painel informativo de um elemento.

    O painel é renderizado em alta resolução apenas uma vez e depois
    reaproveitado (deformado em perspectiva) em todos os quadros.
    ``picture`` (BGRA, Fase 2) é desenhada entre o título e a descrição.
    """
    pad = width // 20
    title_font = load_font(width // 13, bold=True)
    body_font = load_font(width // 22)
    emoji_font = load_emoji_font(title_font.size)
    accent = _rgb(content.color_bgr)

    body_lines = wrap_text(content.descricao, body_font, width - 2 * pad)
    title_h = int(title_font.size * 1.5)
    line_h = int(body_font.size * 1.35)
    header_h = title_h + pad
    pic = _fit_picture(picture, width - 2 * pad, int(width * PICTURE_MAX_HEIGHT)) if picture is not None else None
    pic_h = pic.height + pad // 2 if pic is not None else 0
    height = header_h + pad // 2 + pic_h + line_h * len(body_lines) + pad

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = width // 24
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius, fill=(20, 24, 28, 225))
    draw.rounded_rectangle((0, 0, width - 1, header_h), radius, fill=accent + (255,))
    draw.rectangle((0, header_h - radius, width - 1, header_h), fill=accent + (255,))

    x = pad
    if content.icone and emoji_font is not None:
        draw.text((x, pad // 2 + title_font.size * 0.05), content.icone, font=emoji_font, embedded_color=True)
        x += int(emoji_font.getlength(content.icone)) + pad // 2
    # título claro ou escuro conforme a cor de fundo do cabeçalho
    luminance = 0.299 * accent[0] + 0.587 * accent[1] + 0.114 * accent[2]
    title_color = (20, 20, 20) if luminance > 160 else (255, 255, 255)
    draw.text((x, pad // 2), content.titulo.upper(), font=title_font, fill=title_color)

    y = header_h + pad // 2
    if pic is not None:
        img.alpha_composite(pic, ((width - pic.width) // 2, y))
        y += pic_h
    for line in body_lines:
        draw.text((pad, y), line, font=body_font, fill=(235, 235, 235))
        y += line_h
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius, outline=accent + (255,), width=4)

    rgba = np.array(img)
    return rgba[:, :, [2, 1, 0, 3]].copy()  # RGBA -> BGRA


def _fit_picture(picture: np.ndarray, max_w: int, max_h: int) -> Image.Image:
    """Redimensiona a imagem BGRA para caber em ``max_w`` x ``max_h`` (mantendo a
    proporção) e arredonda os cantos. Retorna uma imagem PIL RGBA."""
    h, w = picture.shape[:2]
    scale = min(max_w / w, max_h / h)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    pil = Image.fromarray(np.ascontiguousarray(picture[:, :, [2, 1, 0, 3]]), "RGBA")
    pil = pil.resize(size, Image.Resampling.LANCZOS)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), max(4, min(size) // 16), fill=255)
    alpha = Image.fromarray(np.minimum(np.array(pil.getchannel("A")), np.array(mask)))
    pil.putalpha(alpha)
    return pil


@lru_cache(maxsize=256)  # etiquetas se repetem a cada quadro: renderiza uma vez só
def render_text_image(
    text: str,
    size: int = 20,
    color: Color = (255, 255, 255),
    bg: Color | None = (0, 0, 0),
    bg_alpha: int = 170,
    bold: bool = False,
    pad: int = 6,
) -> np.ndarray:
    """Imagem BGRA com uma ou mais linhas de texto (etiquetas, HUD, erros).

    O resultado fica em cache e é compartilhado: não modifique o array.
    """
    font = load_font(size, bold=bold)
    lines = text.split("\n")
    line_h = int(size * 1.3)
    width = int(max(font.getlength(line) for line in lines)) + 2 * pad
    height = line_h * len(lines) + 2 * pad
    fill_bg = (_rgb(bg) + (bg_alpha,)) if bg is not None else (0, 0, 0, 0)
    img = Image.new("RGBA", (max(width, 1), height), fill_bg)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((pad, pad + i * line_h), line, font=font, fill=_rgb(color) + (255,))
    return np.array(img)[:, :, [2, 1, 0, 3]].copy()


def blend_bgra(frame: np.ndarray, overlay: np.ndarray, x: int, y: int, opacity: float = 1.0) -> None:
    """Cola ``overlay`` (BGRA) sobre ``frame`` (BGR) na posição (x, y), com recorte."""
    fh, fw = frame.shape[:2]
    oh, ow = overlay.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + ow, fw), min(y + oh, fh)
    if x0 >= x1 or y0 >= y1:
        return
    alpha_blend(frame[y0:y1, x0:x1], overlay[y0 - y : y1 - y, x0 - x : x1 - x], opacity)


def draw_text(
    frame: np.ndarray,
    text: str,
    org: tuple[int, int],
    size: int = 20,
    color: Color = (255, 255, 255),
    bg: Color | None = (0, 0, 0),
    bold: bool = False,
    anchor: str = "lt",
) -> tuple[int, int]:
    """Desenha texto com acentos sobre o quadro. Retorna (largura, altura).

    ``anchor``: "lt" (canto superior esquerdo em ``org``), "lb" (inferior
    esquerdo) ou "ct" (centralizado horizontalmente, topo em ``org``).
    """
    img = render_text_image(text, size, color, bg, bold=bold)
    h, w = img.shape[:2]
    x, y = org
    if anchor == "lb":
        y -= h
    elif anchor == "ct":
        x -= w // 2
    elif anchor == "cb":
        x, y = x - w // 2, y - h
    blend_bgra(frame, img, int(x), int(y))
    return w, h


def configure_console_utf8() -> None:
    """Evita erro ao imprimir acentos/emoji no console do Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError):
                reconfigure(encoding="utf-8")
