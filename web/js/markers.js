// Leitura do texto do QR, fusão QR + ArUco e rastreamento — versão JavaScript
// de qr/markers.py, vision/fusion.py e vision/tracking.py (mesmas regras).
// Sem dependências (testável no Node).

import { UNIT_SQUARE, applyH, center, dist, homography, invert3, projectAll } from "./geometry.js";

const ID_PATTERN = /^[a-z0-9_]{1,40}$/;
const MAX_QR_TEXT = 256;

/**
 * Texto do QR -> id do elemento, ou `null`.
 * Aceita o id puro ("trator") ou um link http(s) com `?e=trator`.
 * O link NUNCA é aberto: só o parâmetro `e` é lido e validado.
 */
export function parseQrText(raw) {
  if (typeof raw !== "string" || !raw || raw.length > MAX_QR_TEXT) return null;
  let text = raw.trim();
  if (text.includes("://")) {
    let url;
    try {
      url = new URL(text);
    } catch {
      return null;
    }
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    const values = url.searchParams.getAll("e");
    if (values.length !== 1) return null;
    text = values[0];
  }
  text = text.toLowerCase();
  return ID_PATTERN.test(text) ? text : null;
}

/** Distância máxima (em lados do ArUco) para aceitar o aprendizado QR <-> ArUco. */
const MAX_LEARN_DISTANCE = 8;

/**
 * Completa os QRs lidos com os ArUcos dos elementos (ver vision/fusion.py).
 * Marcadores: `{ id, corners: [[x,y] x4], viaAruco }`.
 */
export class Fusion {
  constructor(arucoMap, smoothing = 0.8) {
    this.arucoMap = new Map(Object.entries(arucoMap).map(([k, v]) => [Number(k), v]));
    this.smoothing = smoothing;
    this.learned = new Map(); // elemento -> cantos do QR no espaço do ArUco
  }

  update(qrs, arucos) {
    const byElement = new Map();
    for (const a of arucos) {
      const id = this.arucoMap.get(a.id);
      if (id) byElement.set(id, a);
    }
    const read = new Set(qrs.map((q) => q.id));
    for (const q of qrs) if (byElement.has(q.id)) this.#learn(q.id, q.corners, byElement.get(q.id));

    const out = qrs.map((q) => ({ id: q.id, corners: q.corners, viaAruco: false }));
    for (const [id, a] of byElement) {
      if (read.has(id)) continue; // o QR foi lido: ele manda
      const H = homography(UNIT_SQUARE, a.corners);
      if (!H) continue;
      const corners = projectAll(H, this.learned.get(id) ?? UNIT_SQUARE);
      if (corners.flat().every(Number.isFinite)) out.push({ id, corners, viaAruco: true });
    }
    return out;
  }

  /** Cantos previstos do QR do elemento a partir dos cantos do ArUco, ou `null` se ainda não aprendeu. */
  predict(id, arucoCorners) {
    const local = this.learned.get(id);
    const H = local && homography(UNIT_SQUARE, arucoCorners);
    return H ? projectAll(H, local) : null;
  }

  #learn(id, qrCorners, aruco) {
    const H = homography(UNIT_SQUARE, aruco.corners);
    const inv = H && invert3(H);
    if (!inv) return;
    const local = projectAll(inv, qrCorners);
    const far = local.some(([x, y]) => Math.max(Math.abs(x - 0.5), Math.abs(y - 0.5)) > MAX_LEARN_DISTANCE);
    if (far || !local.flat().every(Number.isFinite)) return;
    const prev = this.learned.get(id);
    const a = this.smoothing;
    this.learned.set(id, prev ? prev.map((p, i) => [a * p[0] + (1 - a) * local[i][0], a * p[1] + (1 - a) * local[i][1]]) : local);
  }
}

/**
 * Suaviza os cantos entre quadros e mantém o elemento por `keepSeconds`
 * depois que ele some (o painel não pisca). Um rastro por elemento.
 */
export class Tracker {
  constructor({ smoothing = 0.5, keepSeconds = 0.6 } = {}) {
    this.smoothing = smoothing;
    this.keepSeconds = keepSeconds;
    this.tracks = new Map();
  }

  update(markers, now) {
    const seen = new Set();
    for (const m of markers) {
      seen.add(m.id);
      const t = this.tracks.get(m.id);
      if (!t) {
        this.tracks.set(m.id, { id: m.id, corners: m.corners, firstSeen: now, lastSeen: now, viaAruco: m.viaAruco });
        continue;
      }
      const size = Math.max(dist(m.corners[0], m.corners[1]), dist(m.corners[0], m.corners[3]), 1);
      const a = dist(center(m.corners), center(t.corners)) > 0.5 * size ? 0 : this.smoothing; // salto: não atrasar
      t.corners = t.corners.map((p, i) => [a * p[0] + (1 - a) * m.corners[i][0], a * p[1] + (1 - a) * m.corners[i][1]]);
      t.lastSeen = now;
      t.viaAruco = m.viaAruco;
    }
    const out = [];
    for (const [id, t] of this.tracks) {
      if (now - t.lastSeen > this.keepSeconds) {
        this.tracks.delete(id);
        continue;
      }
      out.push({ ...t, visible: seen.has(id), age: now - t.firstSeen, missing: now - t.lastSeen });
    }
    return out;
  }
}

export { applyH };
