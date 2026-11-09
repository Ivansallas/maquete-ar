"""Geração das imagens de QR Code para impressão."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import qrcode
from PIL import Image, ImageDraw
from qrcode.constants import ERROR_CORRECT_H

from ar.overlay import load_font
from qr.markers import normalize_qr_text


class QRCodeGenerator:
    """Cria QR Codes com o identificador do elemento e uma legenda abaixo.

    A correção de erro "H" (30 %) deixa o QR legível mesmo com pequenas
    sujeiras, dobras ou reflexos na maquete.
    """

    def __init__(self, box_size: int = 20, border: int = 4) -> None:
        self.box_size = box_size
        self.border = border  # "zona de silêncio" branca obrigatória (>= 4 módulos)

    def make_qr(self, data: str) -> Image.Image:
        """Retorna apenas o QR (imagem PIL em tons de cinza)."""
        if normalize_qr_text(data) != data:
            raise ValueError(f"Identificador inválido para QR: {data!r}")
        qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H, box_size=self.box_size, border=self.border)
        qr.add_data(data)
        qr.make(fit=True)
        return qr.make_image(fill_color="black", back_color="white").get_image().convert("L")

    def make_labeled(self, data: str, label: str | None = None) -> Image.Image:
        """QR com legenda (ex.: "Agricultura") embaixo, pronto para imprimir."""
        qr_img = self.make_qr(data)
        label = label or data
        font = load_font(max(18, qr_img.width // 14), bold=True)
        text_h = int(font.size * 1.8)
        canvas = Image.new("L", (qr_img.width, qr_img.height + text_h), 255)
        canvas.paste(qr_img, (0, 0))
        draw = ImageDraw.Draw(canvas)
        tw = draw.textlength(label, font=font)
        draw.text(((qr_img.width - tw) / 2, qr_img.height - self.box_size), label, fill=0, font=font)
        return canvas

    def save(self, data: str, out_dir: str | Path, label: str | None = None) -> Path:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{data}.png"
        self.make_labeled(data, label).save(path, dpi=(300, 300))
        return path


def make_print_sheet(
    items: list[tuple[str, str]],
    generator: QRCodeGenerator,
    qr_cm: float = 5.0,
    dpi: int = 300,
) -> Image.Image:
    """Monta uma folha A4 (300 dpi) com todos os QR Codes em tamanho real.

    ``qr_cm`` é o lado de cada QR impresso (incluindo a margem branca).
    """
    page_w, page_h = int(21.0 / 2.54 * dpi), int(29.7 / 2.54 * dpi)
    sheet = Image.new("L", (page_w, page_h), 255)
    draw = ImageDraw.Draw(sheet)
    side = int(qr_cm / 2.54 * dpi)
    margin = int(1.0 / 2.54 * dpi)
    cols = max(1, (page_w - 2 * margin) // (side + margin // 2))
    cell_w = (page_w - 2 * margin) // cols
    font = load_font(int(dpi * 0.16), bold=True)
    cell_h = side + int(font.size * 2.2)
    x0, y = margin, margin
    for i, (data, label) in enumerate(items):
        col = i % cols
        if col == 0 and i > 0:
            y += cell_h
        if y + cell_h > page_h - margin:
            break  # folha cheia (cabe 8 QRs de 5 cm)
        qr_img = generator.make_qr(data).resize((side, side), Image.Resampling.NEAREST)
        x = x0 + col * cell_w + (cell_w - side) // 2
        sheet.paste(qr_img, (x, y))
        tw = draw.textlength(label, font=font)
        draw.text((x + (side - tw) / 2, y + side + 4), label, fill=0, font=font)
        # linhas de corte pontilhadas
        for dx in range(0, side, 24):
            draw.line([(x + dx, y - 6), (x + dx + 10, y - 6)], fill=170)
    return sheet


def build_demo_board(
    items: list[tuple[str, str]],
    generator: QRCodeGenerator | None = None,
    size: tuple[int, int] = (1600, 1000),
    qr_px: int = 210,
) -> np.ndarray:
    """Cria uma "maquete virtual" (imagem BGR) com QR Codes espalhados.

    Usada no modo de demonstração quando não há câmera disponível.
    """
    import cv2  # import local: só necessário no modo demo

    generator = generator or QRCodeGenerator(box_size=8, border=4)
    w, h = size
    board = np.zeros((h, w, 3), np.uint8)
    board[:] = (70, 140, 95)  # gramado
    rng = np.random.default_rng(7)
    for _ in range(900):  # textura de grama/terra
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        shade = tuple(int(v) for v in rng.integers(40, 120, 3))
        cv2.circle(board, (x, y), int(rng.integers(2, 9)), (shade[0] // 2, shade[1] + 40, shade[2] // 2), -1)
    cv2.rectangle(board, (0, h // 2 - 40), (w, h // 2 + 40), (90, 90, 90), -1)  # estrada
    for x in range(0, w, 80):
        cv2.line(board, (x, h // 2), (x + 40, h // 2), (230, 230, 230), 4)
    for i in range(0, w, 60):  # canteiros de plantação
        cv2.line(board, (i, 30), (i + 30, h // 2 - 70), (40, 100, 140), 6)

    cols = 4
    gap_x = w // cols
    for i, (data, _label) in enumerate(items):
        qr = np.array(generator.make_qr(data).resize((qr_px, qr_px), Image.Resampling.NEAREST))
        qr_bgr = cv2.cvtColor(qr, cv2.COLOR_GRAY2BGR)
        row, col = divmod(i, cols)
        x = col * gap_x + (gap_x - qr_px) // 2
        y = 120 + row * (h // 2) if row == 0 else h // 2 + 110
        board[y : y + qr_px, x : x + qr_px] = qr_bgr
    return board
