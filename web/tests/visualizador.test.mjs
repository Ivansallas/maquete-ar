// Testes da conta de rolagem da imagem ampliada (a parte de tela é verificada no navegador).
import { test } from "node:test";
import assert from "node:assert/strict";
import { zoomScroll } from "../js/visualizador.js";

test("centraliza o ponto tocado", () => {
  assert.deepEqual(zoomScroll(0.5, 0.5, 1000, 800, 400, 300), { left: 300, top: 250 });
});

test("não rola para antes do começo da imagem", () => {
  assert.deepEqual(zoomScroll(0, 0, 1000, 800, 400, 300), { left: 0, top: 0 });
});

test("não rola para depois do fim da imagem", () => {
  assert.deepEqual(zoomScroll(1, 1, 1000, 800, 400, 300), { left: 600, top: 500 });
});

test("imagem menor que a tela não rola", () => {
  assert.deepEqual(zoomScroll(0.9, 0.9, 300, 200, 400, 300), { left: 0, top: 0 });
});
