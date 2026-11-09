// Homografia (perspectiva) em JavaScript puro — mesma ideia de vision/perspective.py:
// o QR é o quadrado unitário (0,0)-(1,1) e tudo "no plano da maquete" é
// projetado na tela com a mesma matriz H. Sem dependências (testável no Node).

export const UNIT_SQUARE = [[0, 0], [1, 0], [1, 1], [0, 1]];

/** Cantos de um retângulo na ordem TL, TR, BR, BL. */
export function rectCorners(w, h, x = 0, y = 0) {
  return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
}

/**
 * Homografia 3x3 (lista de 9 números, por linhas) que leva os 4 pontos `src`
 * nos 4 pontos `dst`. Devolve `null` se os pontos forem degenerados.
 */
export function homography(src, dst) {
  // 8 equações, 8 incógnitas (h22 = 1), resolvidas por eliminação de Gauss.
  const A = [];
  for (let i = 0; i < 4; i++) {
    const [x, y] = src[i];
    const [u, v] = dst[i];
    A.push([x, y, 1, 0, 0, 0, -u * x, -u * y, u]);
    A.push([0, 0, 0, x, y, 1, -v * x, -v * y, v]);
  }
  for (let col = 0; col < 8; col++) {
    let pivot = col;
    for (let r = col + 1; r < 8; r++) if (Math.abs(A[r][col]) > Math.abs(A[pivot][col])) pivot = r;
    if (Math.abs(A[pivot][col]) < 1e-12) return null;
    [A[col], A[pivot]] = [A[pivot], A[col]];
    for (let r = 0; r < 8; r++) {
      if (r === col) continue;
      const f = A[r][col] / A[col][col];
      for (let c = col; c < 9; c++) A[r][c] -= f * A[col][c];
    }
  }
  const h = A.map((row, i) => row[8] / row[i]);
  return [...h, 1];
}

/** Aplica H a um ponto [x, y]. */
export function applyH(H, [x, y]) {
  const w = H[6] * x + H[7] * y + H[8];
  return [(H[0] * x + H[1] * y + H[2]) / w, (H[3] * x + H[4] * y + H[5]) / w];
}

export function projectAll(H, points) {
  return points.map((p) => applyH(H, p));
}

/** Inversa de uma matriz 3x3 (por linhas); `null` se singular. */
export function invert3(m) {
  const [a, b, c, d, e, f, g, h, i] = m;
  const A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
  const det = a * A + b * B + c * C;
  if (Math.abs(det) < 1e-15) return null;
  const inv = [A, -(b * i - c * h), b * f - c * e, B, a * i - c * g, -(a * f - c * d), C, -(a * h - b * g), a * e - b * d];
  return inv.map((v) => v / det);
}

/**
 * Converte H (que leva o retângulo do elemento HTML, com origem no canto
 * superior esquerdo, ao quadrilátero na tela) nos 16 números do CSS
 * `matrix3d(...)` (ordem de colunas). Use com `transform-origin: 0 0`.
 */
export function cssMatrix3d(H) {
  const [a, b, c, d, e, f, g, h, i] = H;
  return [a, d, 0, g, b, e, 0, h, 0, 0, 1, 0, c, f, 0, i];
}

/** `true` se o quadrilátero (4 pontos em ordem) for convexo e não cruzado. */
export function quadIsConvex(q) {
  let sign = 0;
  for (let i = 0; i < 4; i++) {
    const [x0, y0] = q[i], [x1, y1] = q[(i + 1) % 4], [x2, y2] = q[(i + 2) % 4];
    const cross = (x1 - x0) * (y2 - y1) - (y1 - y0) * (x2 - x1);
    if (Math.abs(cross) < 1e-9) return false;
    const s = Math.sign(cross);
    if (sign === 0) sign = s;
    else if (s !== sign) return false;
  }
  return true;
}

export const dist = ([x0, y0], [x1, y1]) => Math.hypot(x1 - x0, y1 - y0);

export function center(q) {
  return [q.reduce((s, p) => s + p[0], 0) / q.length, q.reduce((s, p) => s + p[1], 0) / q.length];
}
