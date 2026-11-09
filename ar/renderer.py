"""Composição final do quadro: contornos, painéis AR, HUD e modo DEBUG."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ar.animations import FadeIn
from ar.objects import ARObjectFactory, RenderContext
from ar.overlay import draw_text
from core.content import ContentManager
from qr.markers import MarkerStatus
from vision.aruco import ArucoMarker
from vision.perspective import perspective_info
from vision.tracking import TrackedMarker

GREEN = (80, 220, 80)
RED = (60, 60, 230)
ORANGE = (0, 165, 255)
YELLOW = (0, 220, 255)
WHITE = (255, 255, 255)
GRAY = (160, 160, 160)


@dataclass
class FrameStats:
    """Informações técnicas exibidas no rodapé/DEBUG."""

    fps: float = 0.0
    detected: int = 0
    last_qr: str | None = None
    source: str = ""
    resolution: tuple[int, int] = (0, 0)
    qr_backend: str = ""
    warning: str | None = None
    aruco: list[ArucoMarker] = field(default_factory=list)


class ARRenderer:
    """Desenha tudo que é sobreposto ao vídeo.

    Args:
        contents: gerenciador dos conteúdos JSON.
        ar_cfg: seção ``"ar"`` do config.json.
        debug: liga o modo DEBUG (pode ser alternado com a tecla D).
        max_missing_frames: usado para o "fade-out" de marcadores perdidos.
        assets_dir: pasta ``assets/`` (imagens dos painéis, Fase 2).
    """

    def __init__(
        self,
        contents: ContentManager,
        ar_cfg: dict[str, Any],
        debug: bool = False,
        max_missing_frames: int = 10,
        assets_dir: str | Path | None = None,
    ) -> None:
        self.contents = contents
        self.enabled = bool(ar_cfg.get("enabled", True))
        self.debug = debug
        self.max_missing = max(1, max_missing_frames)
        self.base_ctx = RenderContext(
            opacity=float(ar_cfg.get("panel_opacity", 0.9)),
            mode=str(ar_cfg.get("mode", "perspective")),
            panel_width=float(ar_cfg.get("panel_width", 3.2)),
            panel_gap=float(ar_cfg.get("panel_gap", 0.25)),
            min_panel_width_px=int(ar_cfg.get("min_panel_width_px", 260)),
        )
        self.max_panels = int(ar_cfg.get("max_panels", 3))  # 0 = sem limite
        self.fade_in = FadeIn(float(ar_cfg.get("fade_in_seconds", 0.3)))
        self.factory = ARObjectFactory(assets_dir=assets_dir)

    # ------------------------------------------------------------------ #
    def render(self, frame: np.ndarray, tracks: list[TrackedMarker], stats: FrameStats, now: float) -> None:
        """Desenha (no próprio ``frame``) marcadores, painéis e HUD."""
        for track in tracks:
            self._draw_outline(frame, track)
        if self.enabled:
            # Painéis evitam cobrir QRs identificados (um QR coberto deixa de ser lido).
            # QRs ilegíveis ficam de fora: o detector às vezes os devolve com cantos absurdos.
            readable = [t for t in tracks if t.marker.status != MarkerStatus.UNREADABLE]
            for track in self._panel_tracks(tracks, frame.shape):
                others = tuple(_box(t) for t in readable if t is not track)
                self._draw_ar(frame, track, now, others)
        for track in tracks:
            self._draw_tag(frame, track)
            if self.debug:
                self._draw_marker_debug(frame, track)
        if self.debug:
            self._draw_debug_panel(frame, stats)
        self._draw_hud(frame, stats)

    # ------------------------------------------------------------------ #
    def _status_color(self, track: TrackedMarker) -> tuple[int, int, int]:
        m = track.marker
        if m.status == MarkerStatus.OK:
            return GREEN if self.contents.get(m.element_id) else RED
        return ORANGE if m.status == MarkerStatus.INVALID else YELLOW

    def _draw_outline(self, frame: np.ndarray, track: TrackedMarker) -> None:
        pts = np.round(track.marker.corners).astype(np.int32).reshape(-1, 1, 2)
        color = self._status_color(track) if track.visible else GRAY
        cv2.polylines(frame, [pts], True, color, 3 if track.visible else 1, cv2.LINE_AA)

    def _panel_tracks(self, tracks: list[TrackedMarker], shape: tuple[int, ...]) -> list[TrackedMarker]:
        """Escolhe quais marcadores ganham painel: os ``max_panels`` mais
        próximos do centro da imagem (o aluno "mira" o que quer ler).
        Retorna do mais distante ao mais próximo, para o principal ficar por cima.
        """
        h, w = shape[:2]
        with_content = [t for t in tracks if self.contents.get(t.marker.element_id)]
        with_content.sort(key=lambda t: np.hypot(t.marker.center[0] - w / 2, t.marker.center[1] - h / 2))
        chosen = with_content[: self.max_panels] if self.max_panels > 0 else with_content
        return chosen[::-1]

    def _draw_ar(
        self,
        frame: np.ndarray,
        track: TrackedMarker,
        now: float,
        obstacles: tuple[tuple[float, float, float, float], ...] = (),
    ) -> None:
        content = self.contents.get(track.marker.element_id)
        if content is None:
            return
        fade_out = 1.0 - track.missing_frames / (self.max_missing + 1)
        elapsed = now - track.first_seen
        opacity = self.base_ctx.opacity * self.fade_in.value(elapsed) * fade_out
        ctx = replace(self.base_ctx, opacity=opacity, obstacles=obstacles, elapsed=elapsed)
        if ctx.opacity > 0.02:
            self.factory.get(content).render(frame, track.marker, ctx)

    def _draw_tag(self, frame: np.ndarray, track: TrackedMarker) -> None:
        """Etiqueta curta logo abaixo do QR (nome ou mensagem de erro)."""
        m = track.marker
        if m.status == MarkerStatus.OK:
            content = self.contents.get(m.element_id)
            text = f"{content.titulo}" if content else f"Conteúdo desconhecido: {m.element_id}"
        elif m.status == MarkerStatus.INVALID:
            text = "QR inválido (não é um elemento da maquete)"
        else:
            text = "QR parcialmente visível — aproxime ou centralize"
        if not track.visible:
            text += " (procurando...)"
        x = int(m.center[0])
        y = int(m.corners[:, 1].max()) + 6
        bg = self._status_color(track) if track.visible else (60, 60, 60)
        draw_text(frame, text, (x, y), size=18, color=WHITE, bg=bg, bold=True, anchor="ct")

    def _draw_marker_debug(self, frame: np.ndarray, track: TrackedMarker) -> None:
        m = track.marker
        cx, cy = map(int, m.center)
        cv2.circle(frame, (cx, cy), 5, (255, 0, 255), -1, cv2.LINE_AA)
        for i, (x, y) in enumerate(m.corners):
            cv2.circle(frame, (int(x), int(y)), 4, (0, 255, 255), -1, cv2.LINE_AA)
            cv2.putText(
                frame, str(i), (int(x) + 5, int(y) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA
            )
        w, h = m.size
        info = perspective_info(m.corners)
        lines = [
            f"#{track.track_id} {m.label} [{m.status.value}]",
            f"CENTER: {cx}, {cy}",
            f"SIZE: {w:.0f}x{h:.0f}  ANG: {m.angle:.0f}°",
            f"SKEW: {info['skew_x']:.2f} / {info['skew_y']:.2f}",
        ]
        x1 = int(m.corners[:, 0].max()) + 8
        draw_text(frame, "\n".join(lines), (x1, int(m.corners[:, 1].min())), size=14, color=(255, 255, 0), bg=(0, 0, 0))

    def _draw_debug_panel(self, frame: np.ndarray, stats: FrameStats) -> None:
        w, h = stats.resolution
        lines = [
            "DEBUG: ON",
            f"Fonte: {stats.source}  {w}x{h}",
            f"Detector QR: {stats.qr_backend}",
            f"FPS: {stats.fps:.1f}",
            f"QR detectados: {stats.detected}",
            f"ArUco detectados: {len(stats.aruco)}",
        ]
        for a in stats.aruco[:4]:
            dist = f"{a.distance_m * 100:.0f} cm" if a.distance_m is not None else "-"
            ang = a.euler_deg
            ang_txt = f" rot=({ang[0]:.0f},{ang[1]:.0f},{ang[2]:.0f})" if ang else ""
            lines.append(f"  ArUco {a.marker_id}: dist={dist}{ang_txt}")
        draw_text(frame, "\n".join(lines), (10, 10), size=16, color=(0, 255, 0), bg=(0, 0, 0))

    def _draw_hud(self, frame: np.ndarray, stats: FrameStats) -> None:
        fh, fw = frame.shape[:2]
        last = stats.last_qr or "-"
        hud = f"QR: {last}   |   Detectados: {stats.detected}   |   FPS: {stats.fps:.1f}"
        draw_text(frame, hud, (10, fh - 10), size=18, color=WHITE, bg=(0, 0, 0), anchor="lb")
        draw_text(
            frame,
            "ESC sair  ·  D debug  ·  S captura",
            (fw - 330, fh - 10),
            size=15,
            color=(220, 220, 220),
            bg=(0, 0, 0),
            anchor="lb",
        )
        if stats.warning:
            # embaixo (acima do rodapé): no topo cobriria os títulos dos painéis
            draw_text(
                frame,
                f"Aviso: {stats.warning}",
                (fw // 2, fh - 50),
                size=16,
                color=WHITE,
                bg=(0, 110, 200),
                anchor="cb",
            )

    # ------------------------------------------------------------------ #
    @staticmethod
    def message_screen(size: tuple[int, int], title: str, message: str) -> np.ndarray:
        """Tela de aviso (ex.: câmera não encontrada) — a aplicação continua aberta."""
        w, h = size
        frame = np.full((h, w, 3), (40, 30, 30), np.uint8)
        draw_text(frame, title, (w // 2, h // 2 - 70), size=34, color=(80, 180, 255), bg=None, bold=True, anchor="ct")
        wrapped = _wrap_simple(message, 70)
        draw_text(frame, wrapped, (w // 2, h // 2 - 10), size=20, color=WHITE, bg=None, anchor="ct")
        draw_text(
            frame,
            "Tentando novamente automaticamente...  (ESC para sair)",
            (w // 2, h - 60),
            size=16,
            color=(180, 180, 180),
            bg=None,
            anchor="ct",
        )
        return frame


def _wrap_simple(text: str, width: int) -> str:
    words, lines, cur = text.split(), [], ""
    for word in words:
        if len(cur) + len(word) + 1 > width and cur:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    lines.append(cur)
    return "\n".join(lines)


def _box(track: TrackedMarker) -> tuple[float, float, float, float]:
    """Retângulo (x0, y0, x1, y1) que contém o QR do rastro."""
    (x0, y0), (x1, y1) = track.marker.corners.min(axis=0), track.marker.corners.max(axis=0)
    return float(x0), float(y0), float(x1), float(y1)
