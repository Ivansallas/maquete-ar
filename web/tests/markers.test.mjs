// Testes da leitura do texto do QR, da fusão QR + ArUco e do rastreamento.
import { test } from "node:test";
import assert from "node:assert/strict";
import { Fusion, Tracker, parseQrText } from "../js/markers.js";

const square = (x, y, s) => [[x, y], [x + s, y], [x + s, y + s], [x, y + s]];
const near = (a, b, eps = 0.5) =>
  a.forEach((p, i) => p.forEach((v, k) => assert.ok(Math.abs(v - b[i][k]) < eps, `${v} vs ${b[i][k]}`)));

// ---------------------------------------------------------------- texto do QR
const URL = "https://professora.github.io/maquete-ar/";
for (const [texto, esperado] of [
  ["trator", "trator"],
  [`${URL}?e=trator`, "trator"],
  [`${URL}?e=meio_ambiente`, "meio_ambiente"],
  ["HTTPS://Exemplo.org/?e=Trator", "trator"],
  [`${URL}?e=../hack`, null],
  [URL, null],
  ["javascript:alert(1)?e=trator", null],
  [`${URL}?e=a&e=b`, null],
  ["<img src=x onerror=alert(1)>", null],
  ["x".repeat(300), null],
  ["", null],
]) {
  test(`parseQrText(${JSON.stringify(texto).slice(0, 40)}) = ${esperado}`, () => {
    assert.equal(parseQrText(texto), esperado);
  });
}

// ---------------------------------------------------------------- fusão
const qr = (id, x, y, s = 200) => ({ id, corners: square(x, y, s) });
const aruco = (id, x, y, s = 80) => ({ id, corners: square(x, y, s) });

test("ArUco sozinho vira o elemento (antes de aprender: o próprio quadrado)", () => {
  const f = new Fusion({ 7: "trator" });
  const out = f.update([], [aruco(7, 400, 300)]);
  assert.equal(out.length, 1);
  assert.equal(out[0].id, "trator");
  assert.equal(out[0].viaAruco, true);
  near(out[0].corners, square(400, 300, 80));
});

test("aprende a posição do QR e usa quando ele some", () => {
  const f = new Fusion({ 7: "trator" });
  f.update([qr("trator", 100, 100)], [aruco(7, 320, 160)]);
  const out = f.update([], [aruco(7, 370, 160)]);
  near(out[0].corners, square(150, 100, 200));
});

test("QR lido tem prioridade (sem duplicar)", () => {
  const f = new Fusion({ 7: "trator" });
  const out = f.update([qr("trator", 100, 100)], [aruco(7, 320, 160)]);
  assert.deepEqual(out.map((m) => [m.id, m.viaAruco]), [["trator", false]]);
});

test("ArUco desconhecido é ignorado; associação absurda não é aprendida", () => {
  const f = new Fusion({ 7: "trator" });
  assert.deepEqual(f.update([], [aruco(42, 0, 0)]), []);
  f.update([qr("trator", 0, 0)], [aruco(7, 1200, 650, 20)]);
  near(f.update([], [aruco(7, 1200, 650, 20)])[0].corners, square(1200, 650, 20));
});

// ---------------------------------------------------------------- rastreamento
test("rastreador suaviza, mantém por um tempo e depois esquece", () => {
  const t = new Tracker({ smoothing: 0.5, keepSeconds: 0.5 });
  t.update([qr("trator", 0, 0)], 0);
  const [a] = t.update([qr("trator", 20, 0)], 0.03);
  assert.ok(a.corners[0][0] > 5 && a.corners[0][0] < 15, "suavizado entre 0 e 20");
  assert.equal(a.visible, true);
  const [b] = t.update([], 0.3);
  assert.equal(b.visible, false);
  assert.deepEqual(t.update([], 1.0), []);
});

test("salto grande não é suavizado (não arrasta o painel)", () => {
  const t = new Tracker({ smoothing: 0.5, keepSeconds: 0.5 });
  t.update([qr("trator", 0, 0)], 0);
  const [a] = t.update([qr("trator", 500, 0)], 0.03);
  assert.equal(Math.round(a.corners[0][0]), 500);
});

test("idade conta desde que o elemento apareceu (anima/fade-in)", () => {
  const t = new Tracker({ smoothing: 0, keepSeconds: 0.5 });
  t.update([qr("trator", 0, 0)], 10);
  const [a] = t.update([qr("trator", 0, 0)], 12);
  assert.equal(a.age, 2);
});

test("predict: onde está o QR, a partir do ArUco (só depois de aprender)", () => {
  const f = new Fusion({ 7: "trator" });
  assert.equal(f.predict("trator", square(320, 160, 80)), null);
  f.update([qr("trator", 100, 100)], [aruco(7, 320, 160)]);
  // o aprendizado vale em qualquer escala de coordenadas (tela ou imagem de detecção)
  near(f.predict("trator", square(160, 80, 40)), square(50, 50, 100));
});
