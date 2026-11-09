"""Rastreamento simples dos QR Codes entre quadros.

Sem rastreamento, o painel "pisca" sempre que um quadro falha na leitura
(desfoque, reflexo, mão na frente). O :class:`MarkerTracker`:

* associa cada detecção ao mesmo marcador do quadro anterior;
* suaviza os cantos (média móvel exponencial) para reduzir tremores;
* mantém o marcador por alguns quadros quando ele some momentaneamente.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np

from qr.markers import MarkerStatus, QRMarker


@dataclass
class TrackedMarker:
    """Um marcador acompanhado ao longo do tempo."""

    track_id: int
    marker: QRMarker
    first_seen: float
    last_seen: float
    missing_frames: int = 0
    hits: int = 1

    @property
    def visible(self) -> bool:
        """``True`` se o QR foi encontrado no quadro atual."""
        return self.missing_frames == 0

    @property
    def key(self) -> str:
        return self.marker.element_id or self.marker.text or f"?{self.track_id}"


class MarkerTracker:
    """Associa detecções entre quadros e suaviza a posição dos cantos.

    Args:
        smoothing: 0 = sem suavização; próximo de 1 = muito suave (mais atraso).
        max_missing_frames: por quantos quadros manter um marcador perdido.
    """

    def __init__(self, smoothing: float = 0.5, max_missing_frames: int = 10) -> None:
        self.smoothing = float(min(max(smoothing, 0.0), 0.95))
        self.max_missing_frames = max(0, int(max_missing_frames))
        self._tracks: list[TrackedMarker] = []
        self._ids = itertools.count(1)

    def reset(self) -> None:
        self._tracks.clear()

    @property
    def tracks(self) -> list[TrackedMarker]:
        return list(self._tracks)

    def update(self, detections: list[QRMarker], now: float) -> list[TrackedMarker]:
        """Atualiza os rastros com as detecções do quadro atual."""
        unmatched = list(self._tracks)
        updated: list[TrackedMarker] = []

        for det in detections:
            track = self._match(det, unmatched)
            if track is None:
                track = TrackedMarker(next(self._ids), det, first_seen=now, last_seen=now)
            else:
                unmatched.remove(track)
                self._merge(track, det, now)
            updated.append(track)

        for track in unmatched:  # não vistos neste quadro
            track.missing_frames += 1
            if track.missing_frames <= self.max_missing_frames and track.marker.status != MarkerStatus.UNREADABLE:
                updated.append(track)

        self._tracks = updated
        return list(updated)

    # ------------------------------------------------------------------ #
    #: Variação máxima de tamanho (para mais ou para menos) entre um QR ilegível
    #: e o rastro com que ele é associado.
    MAX_UNREADABLE_SIZE_RATIO = 1.5

    def _match(self, det: QRMarker, candidates: list[TrackedMarker]) -> TrackedMarker | None:
        """Escolhe o rastro mais próximo compatível com a detecção."""
        best, best_dist = None, float("inf")
        cx, cy = det.center
        size = max(det.size)
        unreadable_now = det.status == MarkerStatus.UNREADABLE
        for track in candidates:
            prev = track.marker
            prev_size = max(max(prev.size), 1.0)
            # QR ilegível neste quadro pode ser o mesmo QR lido antes
            if not (det.text == prev.text or unreadable_now):
                continue
            if unreadable_now:
                # O detector às vezes devolve um "QR ilegível" com cantos absurdos
                # (bem maior que o QR real). Sem texto para confirmar a identidade,
                # só aceitamos se o tamanho for compatível e a distância for medida
                # pelo tamanho do rastro conhecido, não da detecção suspeita.
                ratio = size / prev_size
                if not (1 / self.MAX_UNREADABLE_SIZE_RATIO <= ratio <= self.MAX_UNREADABLE_SIZE_RATIO):
                    continue
                limit = 1.5 * prev_size + 40
            else:
                limit = 1.5 * max(size, prev_size) + 40
            px, py = prev.center
            dist = float(np.hypot(cx - px, cy - py))
            if dist < limit and dist < best_dist:
                best, best_dist = track, dist
        return best

    def _merge(self, track: TrackedMarker, det: QRMarker, now: float) -> None:
        prev = track.marker
        a = self.smoothing
        jump = np.hypot(*(np.array(det.center) - np.array(prev.center)))
        if jump > 0.5 * max(det.size):  # movimento rápido: não atrasar
            a = 0.0
        corners = a * prev.corners + (1.0 - a) * det.corners
        if det.status == MarkerStatus.UNREADABLE:
            # mantém o texto já conhecido; só atualiza a posição
            track.marker = QRMarker(prev.text, corners.astype(np.float32), prev.element_id, prev.status)
        else:
            track.marker = QRMarker(det.text, corners.astype(np.float32), det.element_id, det.status)
        track.last_seen = now
        track.missing_frames = 0
        track.hits += 1
