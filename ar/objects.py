"""Objetos de realidade aumentada ancorados a um marcador.

Todo conteúdo exibido sobre a maquete é um :class:`ARObject`. Hoje existe
o :class:`TextPanel` (Fase 1) e o :class:`ImagePanel` (Fase 2). As próximas
fases criam novas subclasses — ``AnimatedSprite`` (Fase 3), ``Model3D``
(Fase 6) — e registram no :class:`ARObjectFactory`; o renderer não muda.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ar.overlay import render_panel
from core.assets import AssetError, load_image, resolve_asset
from core.content import ElementContent
from qr.markers import QRMarker
from vision.perspective import marker_homography, project_points, quad_is_valid, rect_corners, warp_onto

log = logging.getLogger(__name__)

#: Altura máxima do painel "billboard", em fração da altura da tela.
BILLBOARD_MAX_HEIGHT = 0.5
#: O billboard pode encolher até esta fração para caber num espaço livre.
MIN_BILLBOARD_SCALE = 0.7


@dataclass
class RenderContext:
    """Parâmetros de desenho compartilhados por todos os objetos AR."""

    opacity: float = 1.0
    mode: str = "perspective"  # perspective | billboard
    panel_width: float = 3.2  # em lados do QR
    panel_gap: float = 0.25  # em lados do QR
    min_panel_width_px: int = 260
    #: retângulos (x0, y0, x1, y1) que o painel billboard deve evitar cobrir (outros QRs)
    obstacles: tuple[tuple[float, float, float, float], ...] = ()


class ARObject(ABC):
    """Conteúdo digital desenhado em relação a um marcador."""

    @abstractmethod
    def render(self, frame: np.ndarray, marker: QRMarker, ctx: RenderContext) -> np.ndarray | None:
        """Desenha no quadro. Retorna o quadrilátero ocupado (ou ``None``)."""


class TextPanel(ARObject):
    """Painel com ícone, título e descrição "preso" acima do QR Code.

    * modo ``perspective``: o painel fica no mesmo plano do QR (homografia),
      inclinando e girando junto com ele;
    * modo ``billboard`` (ou quando o QR está muito pequeno/inclinado para
      o texto ser legível): o painel fica de frente para a tela, mas
      continua acompanhando a posição do QR.
    """

    def __init__(self, content: ElementContent, resolution: int = 640) -> None:
        self.content = content
        self.image = self._build_image(resolution)
        h, w = self.image.shape[:2]
        self.aspect = h / w

    def render(self, frame: np.ndarray, marker: QRMarker, ctx: RenderContext) -> np.ndarray | None:
        quad = None
        if ctx.mode == "perspective":
            quad = self._perspective_quad(marker, ctx, frame.shape)
        if quad is None:
            quad = self._billboard_quad(marker, ctx, frame.shape)
        return quad if warp_onto(frame, self.image, quad, ctx.opacity) else None

    def _build_image(self, resolution: int) -> np.ndarray:
        """Imagem BGRA do painel (renderizada uma única vez)."""
        return render_panel(self.content, resolution)

    def _perspective_quad(self, marker: QRMarker, ctx: RenderContext, shape: tuple[int, ...]) -> np.ndarray | None:
        H = marker_homography(marker.corners)
        w = ctx.panel_width
        h = w * self.aspect
        # Coordenadas do marcador: QR = quadrado (0,0)-(1,1); y negativo = acima.
        local = rect_corners(w, h, x=0.5 - w / 2, y=-ctx.panel_gap - h)
        quad = project_points(H, local)
        if not quad_is_valid(quad, shape):
            return None
        top, bottom = np.linalg.norm(quad[1] - quad[0]), np.linalg.norm(quad[2] - quad[3])
        if min(top, bottom) < ctx.min_panel_width_px or max(top, bottom) / max(min(top, bottom), 1) > 2.5:
            return None  # pequeno ou distorcido demais para ler
        if min(quad[0][1], quad[1][1]) < 0:
            return None  # borda de cima (título) fora da tela: billboard se reposiciona
        return quad

    def _billboard_quad(self, marker: QRMarker, ctx: RenderContext, shape: tuple[int, ...]) -> np.ndarray:
        fh, fw = shape[:2]
        qr_w = max(marker.size)
        w = float(np.clip(qr_w * ctx.panel_width, ctx.min_panel_width_px, fw * 0.45))
        w = min(w, fh * BILLBOARD_MAX_HEIGHT / self.aspect)  # painéis altos (com imagem) cabem na tela
        h = w * self.aspect
        gap = qr_w * ctx.panel_gap
        cx, cy = marker.center
        (qx0, qy0), (qx1, qy1) = marker.corners.min(axis=0), marker.corners.max(axis=0)
        own = (float(qx0), float(qy0), float(qx1), float(qy1))

        def place(side: str) -> Rect:
            """Painel encostado num lado do QR, encolhido (até MIN_BILLBOARD_SCALE)
            para caber no espaço livre e deslizado para dentro da tela."""
            room = {"above": qy0 - gap, "below": fh - qy1 - gap, "right": fw - qx1 - gap, "left": qx0 - gap}[side]
            limit = h if side in ("above", "below") else w
            s = float(np.clip(room / limit, MIN_BILLBOARD_SCALE, 1.0))
            pw, ph = w * s, h * s
            x = {"right": qx1 + gap, "left": qx0 - gap - pw}.get(side, cx - pw / 2)
            y = {"above": qy0 - gap - ph, "below": qy1 + gap}.get(side, cy - ph / 2)
            return float(np.clip(x, 0, max(fw - pw, 0))), float(np.clip(y, 0, max(fh - ph, 0))), pw, ph

        def cost(r: Rect) -> float:
            # Um QR coberto deixa de ser lido e o painel dele pisca: cobrir o
            # próprio QR pesa muito mais que um vizinho; encolher custa pouco.
            return 1000 * _overlap(r, own) + sum(_overlap(r, o) for o in ctx.obstacles) + (w - r[2]) * h * 0.01

        # Em caso de empate, vale a ordem: acima, abaixo, à direita, à esquerda.
        x, y, pw, ph = min((place(side) for side in ("above", "below", "right", "left")), key=cost)
        return rect_corners(pw, ph, x, y)


#: Retângulo (x, y, largura, altura).
Rect = tuple[float, float, float, float]


def _overlap(rect: Rect, box: tuple[float, float, float, float]) -> float:
    """Área de interseção entre ``rect`` (x, y, w, h) e ``box`` (x0, y0, x1, y1)."""
    x, y, w, h = rect
    dx = min(x + w, box[2]) - max(x, box[0])
    dy = min(y + h, box[3]) - max(y, box[1])
    return max(dx, 0.0) * max(dy, 0.0)


class ImagePanel(TextPanel):
    """Painel com imagem entre o título e a descrição (Fase 2).

    Mesmo posicionamento do :class:`TextPanel` (perspectiva ou billboard);
    só a imagem do painel muda.
    """

    def __init__(self, content: ElementContent, picture: np.ndarray, resolution: int = 640) -> None:
        self.picture = picture
        super().__init__(content, resolution)

    def _build_image(self, resolution: int) -> np.ndarray:
        return render_panel(self.content, resolution, self.picture)


class ARObjectFactory:
    """Cria o objeto AR adequado para cada conteúdo (com cache).

    Args:
        resolution: largura, em pixels, com que cada painel é renderizado.
        assets_dir: pasta ``assets/``; sem ela, imagens são ignoradas.
    """

    def __init__(self, resolution: int = 640, assets_dir: str | Path | None = None) -> None:
        self.resolution = resolution
        self.assets_dir = Path(assets_dir) if assets_dir is not None else None
        self._cache: dict[str, ARObject] = {}

    def get(self, content: ElementContent) -> ARObject:
        obj = self._cache.get(content.id)
        if obj is None:
            obj = self._create(content)
            self._cache[content.id] = obj
        return obj

    def _create(self, content: ElementContent) -> ARObject:
        # Fase 3+: if content.animacao: AnimatedSprite(...); if content.modelo: Model3D(...)
        if content.imagem and self.assets_dir is not None:
            try:
                picture = load_image(resolve_asset(self.assets_dir, content.imagem), max_side=self.resolution * 2)
                return ImagePanel(content, picture, self.resolution)
            except AssetError as exc:
                # Já avisado pelo ContentManager no início; aqui só garantimos o fallback.
                log.warning("%s: imagem ignorada (%s); usando painel só com texto.", content.id, exc)
        return TextPanel(content, self.resolution)

    def clear(self) -> None:
        self._cache.clear()
