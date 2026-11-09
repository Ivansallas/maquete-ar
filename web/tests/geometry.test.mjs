// Testes da geometria (homografia) usada para colar o painel no QR.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  UNIT_SQUARE,
  applyH,
  cssMatrix3d,
  homography,
  invert3,
  projectAll,
  quadIsConvex,
  rectCorners,
} from "../js/geometry.js";

const close = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);

test("homografia leva os 4 pontos de origem aos de destino", () => {
  const dst = [[100, 100], [220, 110], [230, 240], [90, 220]];
  const H = homography(UNIT_SQUARE, dst);
  UNIT_SQUARE.forEach((p, i) => {
    const [x, y] = applyH(H, p);
    close(x, dst[i][0], 1e-6);
    close(y, dst[i][1], 1e-6);
  });
});

test("inversa desfaz a homografia", () => {
  const H = homography(UNIT_SQUARE, [[10, 20], [300, 40], [280, 260], [30, 240]]);
  const back = applyH(invert3(H), applyH(H, [0.3, 0.7]));
  close(back[0], 0.3, 1e-9);
  close(back[1], 0.7, 1e-9);
});

test("homografia degenerada devolve null", () => {
  assert.equal(homography(UNIT_SQUARE, [[0, 0], [0, 0], [0, 0], [0, 0]]), null);
});

test("matrix3d do CSS mapeia o retângulo do elemento no quadrilátero", () => {
  const quad = [[50, 60], [350, 80], [330, 300], [40, 280]];
  const H = homography(rectCorners(300, 200), quad);
  const m = cssMatrix3d(H);
  // CSS: ponto (x, y, 0, 1) multiplicado pela matriz em ordem de colunas
  const apply = (x, y) => {
    const X = m[0] * x + m[4] * y + m[12];
    const Y = m[1] * x + m[5] * y + m[13];
    const W = m[3] * x + m[7] * y + m[15];
    return [X / W, Y / W];
  };
  rectCorners(300, 200).forEach((p, i) => {
    const [x, y] = apply(...p);
    close(x, quad[i][0], 1e-6);
    close(y, quad[i][1], 1e-6);
  });
});

test("convexidade", () => {
  assert.equal(quadIsConvex([[0, 0], [10, 0], [10, 10], [0, 10]]), true);
  assert.equal(quadIsConvex([[0, 0], [10, 10], [10, 0], [0, 10]]), false); // cruzado
});

test("projectAll aplica em lista", () => {
  const H = homography(UNIT_SQUARE, rectCorners(2, 2, 5, 5));
  assert.deepEqual(projectAll(H, [[0.5, 0.5]]).map((p) => p.map(Math.round)), [[6, 6]]);
});
