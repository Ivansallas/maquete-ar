"""Geração das imagens de QR Code para impressão."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import qrcode
from PIL import Image, ImageDraw
from qrcode.constants import ERROR_CORRECT_H

from ar.overlay import load_font
from core.content import ID_PATTERN
from qr.markers import normalize_qr_text


def qr_payload(element_id: str, base_url: str | None) -> str:
    """Texto gravado no QR: o id puro ou, se o site estiver configurado
    (``config.json`` → ``web.url``), o link ``<url>/?e=<id>`` que a câmera do
    celular abre direto na página de realidade aumentada."""
    if not ID_PATTERN.fullmatch(element_id):
        raise ValueError(f"Identificador inválido para QR: {element_id!r}")
    if not base_url:
        return element_id
    if not base_url.lower().startswith("https://"):
        raise ValueError("web.url precisa começar com https:// (o celular só libera a câmera em HTTPS)")
    return f"{base_url.rstrip('/')}/?e={element_id}"


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
        if normalize_qr_text(data) is None:  # só id ou link com ?e=<id> (ver qr_payload)
            raise ValueError(f"Conteúdo inválido para QR: {data!r}")
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

    def save(self, element_id: str, out_dir: str | Path, label: str | None = None, payload: str | None = None) -> Path:
        """Salva ``<element_id>.png``; ``payload`` é o texto do QR (padrão: o id)."""
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{element_id}.png"
        self.make_labeled(payload or element_id, label or element_id).save(path, dpi=(300, 300))
        return path


def _aruco_image(marker_id: int, side_px: int) -> Image.Image:
    """ArUco (só a parte preta mede ``side_px``) com margem branca, em PIL."""
    from vision.aruco import ArucoDetector  # import local: evita ciclo qr <-> vision

    return Image.fromarray(ArucoDetector().generate(marker_id, side_px))


def make_print_sheets(
    items: list[tuple[str, str]],
    generator: QRCodeGenerator,
    qr_cm: float = 5.0,
    dpi: int = 300,
    aruco_ids: dict[str, int] | None = None,
    aruco_cm: float = 3.0,
    base_url: str | None = None,
) -> list[Image.Image]:
    """Monta folhas A4 com todos os QR Codes em tamanho real (quantas forem precisas).

    ``qr_cm`` é o lado de cada QR impresso (incluindo a margem branca).
    Com ``aruco_ids`` (Fase 4), o ArUco de cada elemento é impresso à direita
    do QR; ``aruco_cm`` é o lado da parte preta (= ``aruco.marker_length_m``).
    Cole os dois juntos na maquete, no mesmo plano. Com ``base_url``, cada QR
    leva o link do site (ver :func:`qr_payload`).
    """
    aruco_ids = aruco_ids or {}
    page_w, page_h = int(21.0 / 2.54 * dpi), int(29.7 / 2.54 * dpi)
    side = int(qr_cm / 2.54 * dpi)
    margin = int(1.0 / 2.54 * dpi)
    gap = margin // 2  # espaço entre colunas
    aruco_px = int(aruco_cm / 2.54 * dpi)
    aruco_gap = margin // 3
    aruco_w = (aruco_gap + aruco_px + 2 * (aruco_px // 8)) if aruco_ids else 0  # ArUco + margem branca
    item_w = side + aruco_w
    usable_w, usable_h = page_w - 2 * margin, page_h - 2 * margin
    cols = max(1, (usable_w + gap) // (item_w + gap))
    cell_w = usable_w // cols
    font = load_font(int(dpi * 0.16), bold=True)
    small = load_font(int(dpi * 0.09))
    cell_h = side + int(font.size * 2.2)
    rows = max(1, usable_h // cell_h)
    per_page = cols * rows

    pages: list[Image.Image] = []
    for first in range(0, len(items), per_page):
        sheet = Image.new("L", (page_w, page_h), 255)
        draw = ImageDraw.Draw(sheet)
        for i, (data, label) in enumerate(items[first : first + per_page]):
            row, col = divmod(i, cols)
            x = margin + col * cell_w + (cell_w - item_w) // 2
            y = margin + row * cell_h
            qr_img = generator.make_qr(qr_payload(data, base_url))
            sheet.paste(qr_img.resize((side, side), Image.Resampling.NEAREST), (x, y))
            if data in aruco_ids:
                marker = _aruco_image(aruco_ids[data], aruco_px)
                ax, ay = x + side + aruco_gap, y + (side - marker.height) // 2
                sheet.paste(marker, (ax, ay))
                caption = f"ArUco {aruco_ids[data]}"
                cx = ax + (marker.width - draw.textlength(caption, font=small)) / 2
                draw.text((cx, ay + marker.height), caption, fill=0, font=small)
            tw = draw.textlength(label, font=font)
            draw.text((x + (side - tw) / 2, y + side + 4), label, fill=0, font=font)
            for dx in range(0, item_w, 24):  # linha de corte pontilhada (QR + ArUco)
                draw.line([(x + dx, y - 6), (x + dx + 10, y - 6)], fill=170)
        pages.append(sheet)
    return pages


def build_demo_board(
    items: list[tuple[str, str]],
    generator: QRCodeGenerator | None = None,
    size: tuple[int, int] = (1600, 1000),
    qr_px: int = 210,
    aruco_ids: dict[str, int] | None = None,
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

    aruco_ids = aruco_ids or {}
    aruco_side = int(qr_px * 0.5)  # parte preta; como na folha impressa (3 cm ao lado de 5 cm)
    aruco_total = aruco_side + 2 * (aruco_side // 8) + 12 if aruco_ids else 0
    cols = 4
    gap_x = w // cols
    for i, (data, _label) in enumerate(items):
        qr = np.array(generator.make_qr(data).resize((qr_px, qr_px), Image.Resampling.NEAREST))
        qr_bgr = cv2.cvtColor(qr, cv2.COLOR_GRAY2BGR)
        row, col = divmod(i, cols)
        x = col * gap_x + (gap_x - qr_px - aruco_total) // 2
        y = 120 + row * (h // 2) if row == 0 else h // 2 + 110
        board[y : y + qr_px, x : x + qr_px] = qr_bgr
        if data in aruco_ids:  # Fase 4: ArUco colado à direita do QR
            marker = np.array(_aruco_image(aruco_ids[data], aruco_side))
            mh, mw = marker.shape
            ax, ay = x + qr_px + 12, y + (qr_px - mh) // 2
            board[ay : ay + mh, ax : ax + mw] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    return board
