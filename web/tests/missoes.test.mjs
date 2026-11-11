// Testes da lógica do modo Missões (ordem, quiz, "perde a vez", estrelas, progresso salvo).
import { test } from "node:test";
import assert from "node:assert/strict";
import { HOLD_SECONDS, Missions, shuffle, shuffledOptions, starsFor } from "../js/missoes.js";

const quiz = (correta = 0) => ({ pergunta: "?", alternativas: ["a", "b", "c"], correta, explicacao: "e" });
const ELEMENTOS = {
  agricultura: { titulo: "Agricultura", missao: "m1", quiz: quiz(0) },
  pecuaria: { titulo: "Pecuária", missao: "m2", quiz: quiz(1) },
  trator: { titulo: "Trator", missao: "m3", quiz: quiz(2) },
  comercio: { titulo: "Comércio", missao: null, quiz: null }, // sem missão: fica de fora
};
// "aleatório" previsível: sempre 0 => o embaralhamento gira a lista de um jeito fixo
const fixed = () => 0;

test("só elementos com missão e quiz entram; ordem sorteada", () => {
  const m = new Missions(ELEMENTOS, null, fixed);
  assert.equal(m.total, 3);
  assert.deepEqual([...m.queue].sort(), ["agricultura", "pecuaria", "trator"]);
  assert.ok(!m.queue.includes("comercio"));
  assert.equal(m.current, m.queue[0]);
});

test("embaralhar não perde nem repete itens e não altera a lista original", () => {
  const list = ["a", "b", "c", "d", "e"];
  const out = shuffle(list);
  assert.deepEqual([...out].sort(), list);
  assert.deepEqual(list, ["a", "b", "c", "d", "e"]);
});

test("estrelas: 3 de primeira, 2 na segunda, 1 depois", () => {
  assert.deepEqual([1, 2, 3, 7].map(starsFor), [3, 2, 1, 1]);
});

test("acertar dá a figurinha com estrelas e passa para a próxima missão", () => {
  const m = new Missions(ELEMENTOS, null, fixed);
  const alvo = m.current;
  const r = m.answer(ELEMENTOS[alvo].quiz.correta);
  assert.deepEqual(r, { correct: true, stars: 3, id: alvo });
  assert.equal(m.done[alvo], 3);
  assert.notEqual(m.current, alvo);
  assert.equal(m.doneCount, 1);
});

test("errar perde a vez: a missão vai para o fim da fila", () => {
  const m = new Missions(ELEMENTOS, null, fixed);
  const [primeiro, segundo] = m.queue;
  const errada = (ELEMENTOS[primeiro].quiz.correta + 1) % 3;
  assert.deepEqual(m.answer(errada), { correct: false, stars: 0, id: primeiro });
  assert.equal(m.current, segundo);
  assert.equal(m.queue.at(-1), primeiro);
  assert.equal(m.done[primeiro], undefined);
  // quando voltar e acertar, vale 2 estrelas (segunda tentativa)
  while (m.current !== primeiro) m.answer(ELEMENTOS[m.current].quiz.correta);
  assert.equal(m.answer(ELEMENTOS[primeiro].quiz.correta).stars, 2);
});

test("terminar todas as missões", () => {
  const m = new Missions(ELEMENTOS, null, fixed);
  while (m.current) m.answer(ELEMENTOS[m.current].quiz.correta);
  assert.ok(m.finished);
  assert.equal(m.current, null);
  assert.equal(m.answer(0), null); // nada para responder
  assert.equal(m.totalStars, 9);
});

test("progresso salvo é retomado; itens inválidos ou removidos são descartados", () => {
  const m = new Missions(ELEMENTOS, null, fixed);
  const alvo = m.current;
  m.answer(ELEMENTOS[alvo].quiz.correta);
  const saved = JSON.parse(JSON.stringify(m.toJSON()));
  const r = new Missions(ELEMENTOS, saved, fixed);
  assert.deepEqual(r.queue, m.queue);
  assert.deepEqual(r.done, m.done);

  const sujo = { queue: ["trator", "nave", "trator", 5], done: { agricultura: 3, comercio: 3, x: 1, pecuaria: "9" }, attempts: { trator: 2 } };
  const s = new Missions(ELEMENTOS, sujo, fixed);
  assert.deepEqual(s.done, { agricultura: 3 }); // comercio não tem missão; "9" não é estrela válida
  assert.deepEqual([...s.queue].sort(), ["pecuaria", "trator"]); // pecuaria (nova) entra na fila
  assert.equal(s.queue[0], "trator");
  assert.equal(s.attempts.trator, 2);
});

test("progresso salvo quebrado começa do zero", () => {
  for (const saved of ["lixo", 42, [], { queue: "x" }]) {
    const m = new Missions(ELEMENTOS, saved, fixed);
    assert.equal(m.total, 3);
    assert.equal(m.doneCount, 0);
    assert.equal(m.queue.length, 3);
  }
});

test("recomeçar zera o progresso", () => {
  const m = new Missions(ELEMENTOS, null, fixed);
  m.answer(ELEMENTOS[m.current].quiz.correta);
  m.reset();
  assert.equal(m.doneCount, 0);
  assert.equal(m.queue.length, 3);
  assert.deepEqual(m.attempts, {});
});

test("é preciso mirar o alvo por um tempo para abrir o quiz", () => {
  const m = new Missions(ELEMENTOS, null, fixed);
  const alvo = m.current;
  const outro = m.queue[1];
  assert.equal(m.observe(null, 0), null);
  assert.equal(m.observe(outro, 0), "outro");
  assert.equal(m.observe(alvo, 1), "mirando");
  assert.equal(m.observe(alvo, 1 + HOLD_SECONDS / 2), "mirando");
  assert.equal(m.observe(outro, 1 + HOLD_SECONDS * 0.6), "outro"); // perdeu a mira: recomeça
  assert.equal(m.observe(alvo, 3), "mirando");
  assert.equal(m.observe(alvo, 3 + HOLD_SECONDS), "achou");
});

test("alternativas embaralhadas mantêm o índice original", () => {
  const opts = shuffledOptions(quiz(1));
  assert.equal(opts.length, 3);
  assert.deepEqual(opts.map((o) => o.index).sort(), [0, 1, 2]);
  for (const o of opts) assert.equal(o.text, ["a", "b", "c"][o.index]);
});
