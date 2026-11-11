// Lógica do modo Missões (caça ao tesouro com quiz), sem nada de tela:
// fila de missões sorteada, "errou perde a vez", estrelas e progresso salvo.
// A tela fica em missoes-ui.js. Testes: web/tests/missoes.test.mjs.

/** Tempo mirando o elemento certo até abrir o quiz (evita abrir por acaso). */
export const HOLD_SECONDS = 1;

/** Estrelas pela tentativa em que acertou: 1ª = 3, 2ª = 2, depois = 1. */
export function starsFor(attempts) {
  return attempts <= 1 ? 3 : attempts === 2 ? 2 : 1;
}

/** Cópia embaralhada (Fisher-Yates). `random` pode ser trocado nos testes. */
export function shuffle(list, random = Math.random) {
  const out = [...list];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/** Alternativas em ordem nova a cada tentativa (ninguém decora a posição). */
export function shuffledOptions(quiz, random = Math.random) {
  return shuffle(
    quiz.alternativas.map((text, index) => ({ text, index })),
    random,
  );
}

export class Missions {
  /**
   * @param {Record<string, {missao?: string|null, quiz?: object|null}>} elementos
   * @param {unknown} saved progresso salvo (toJSON); qualquer coisa estranha é ignorada
   */
  constructor(elementos, saved = null, random = Math.random) {
    this.elementos = elementos;
    this.random = random;
    this.ids = Object.keys(elementos)
      .filter((id) => elementos[id].missao && elementos[id].quiz)
      .sort();
    this.reset();
    this.restore(saved);
  }

  reset() {
    this.queue = shuffle(this.ids, this.random); // missões que faltam; a primeira é a atual
    this.done = {}; // id -> estrelas (a "figurinha")
    this.attempts = {}; // id -> tentativas de resposta
    this.since = null; // { id, t } desde quando o aluno mira o alvo
  }

  /** Retoma um progresso salvo, validando tudo (o localStorage pode ter lixo). */
  restore(saved) {
    if (!saved || typeof saved !== "object" || !Array.isArray(saved.queue)) return;
    const valid = new Set(this.ids);
    const done = {};
    for (const [id, stars] of Object.entries(saved.done ?? {})) {
      if (valid.has(id) && [1, 2, 3].includes(stars)) done[id] = stars;
    }
    const queue = [...new Set(saved.queue)].filter((id) => valid.has(id) && !(id in done));
    // elementos novos (o professor adicionou missões) entram no fim, sorteados
    const missing = this.ids.filter((id) => !(id in done) && !queue.includes(id));
    const attempts = {};
    for (const [id, n] of Object.entries(saved.attempts ?? {})) {
      if (valid.has(id) && Number.isInteger(n) && n > 0) attempts[id] = n;
    }
    this.queue = [...queue, ...shuffle(missing, this.random)];
    this.done = done;
    this.attempts = attempts;
  }

  toJSON() {
    return { queue: this.queue, done: this.done, attempts: this.attempts };
  }

  get current() {
    return this.queue[0] ?? null;
  }
  get total() {
    return this.ids.length;
  }
  get doneCount() {
    return Object.keys(this.done).length;
  }
  get finished() {
    return this.total > 0 && this.queue.length === 0;
  }
  get totalStars() {
    return Object.values(this.done).reduce((a, b) => a + b, 0);
  }

  /**
   * Chamado a cada detecção com o elemento que o aluno está mirando (ou null).
   * Devolve "achou" quando mira o alvo por HOLD_SECONDS, "mirando" enquanto
   * isso, "outro" se é um elemento diferente da missão, ou null.
   */
  observe(id, t) {
    if (!id || !this.current) {
      this.since = null;
      return null;
    }
    if (id !== this.current) {
      this.since = null;
      return "outro";
    }
    if (!this.since || this.since.id !== id) this.since = { id, t };
    return t - this.since.t >= HOLD_SECONDS ? "achou" : "mirando";
  }

  /** Responde o quiz da missão atual. Errou: perde a vez (vai para o fim da fila). */
  answer(index) {
    const id = this.current;
    if (!id) return null;
    this.since = null;
    const n = (this.attempts[id] ?? 0) + 1;
    this.attempts[id] = n;
    if (index === this.elementos[id].quiz.correta) {
      const stars = starsFor(n);
      this.done[id] = stars;
      this.queue.shift();
      return { correct: true, stars, id };
    }
    this.queue.push(this.queue.shift());
    return { correct: false, stars: 0, id };
  }
}
