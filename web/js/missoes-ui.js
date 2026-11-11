// Tela do modo Missões: barra com a pista, quiz, álbum de figurinhas e tela final.
// A lógica (fila, estrelas, progresso) está em missoes.js.
// Segurança: todo texto vem do JSON do professor e entra só por textContent.

import { isLight } from "./cores.js";
import { Missions, shuffledOptions } from "./missoes.js";

const STORAGE_KEY = "maquete-ar:missoes:v1";
const $ = (id) => document.getElementById(id);

// localStorage pode falhar (aba anônima, bloqueado): o jogo funciona, só não lembra.
function load() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
  } catch {
    return null;
  }
}
function save(missions) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(missions.toJSON()));
  } catch {
    /* sem armazenamento: o progresso vale só até fechar a página */
  }
}

const starsText = (n) => "⭐".repeat(n);

export function createMissionsUi(elementos) {
  const missions = new Missions(elementos, load());
  const bar = $("missao");
  const quizBox = $("quiz");
  const albumBox = $("album");
  let found = null; // elemento achado, esperando o aluno tocar em "Responder"
  let otherUntil = 0; // mostra "esse é o X" por alguns instantes
  let otherId = null;

  // ------------------------------------------------------------ barra da pista
  function renderBar(status) {
    $("missao-progresso").textContent = missions.finished
      ? `🏆 ${missions.doneCount}/${missions.total} figurinhas`
      : `🎯 Missão ${missions.doneCount + 1} de ${missions.total}`;
    $("missao-pista").textContent = missions.finished
      ? "Você completou todas as missões!"
      : elementos[missions.current].missao;
    const st = $("missao-status");
    st.textContent = status.text;
    st.className = status.kind || "";
    $("responder").hidden = !found;
  }

  function statusFor(result, t) {
    if (missions.finished) return { text: "Abra o álbum para ver suas figurinhas." };
    if (found) {
      return { text: `Você achou: ${elementos[found].titulo}! Leia o painel e toque em Responder.`, kind: "ok" };
    }
    if (result === "outro") {
      otherUntil = t + 2.5;
    }
    if (otherId && t < otherUntil) {
      return { text: `Não é esse! Você está vendo: ${elementos[otherId].titulo}. Leia a pista de novo.`, kind: "aviso" };
    }
    if (result === "mirando") return { text: "Isso! Segure firme…", kind: "ok" };
    return { text: "Procure na maquete e aponte a câmera para o QR Code." };
  }

  /** Chamado a cada detecção com o elemento mirado (ou null). */
  function update(id, t) {
    if (!quizBox.hidden || !albumBox.hidden) return; // jogo pausado com janela aberta
    let result = null;
    if (!found && !missions.finished) {
      result = missions.observe(id, t);
      if (result === "achou") found = missions.current;
      if (result === "outro") otherId = id;
    }
    renderBar(statusFor(result, t));
  }

  // ------------------------------------------------------------ quiz
  function openQuiz() {
    if (!found) return;
    const data = elementos[found];
    paintHeader($("quiz-cabecalho"), data);
    $("quiz-pergunta").textContent = data.quiz.pergunta;
    const list = $("quiz-alternativas");
    list.replaceChildren(
      ...shuffledOptions(data.quiz).map(({ text, index }) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "alternativa";
        b.textContent = text;
        b.onclick = () => answer(index, b);
        return b;
      }),
    );
    $("quiz-resultado").hidden = true;
    $("quiz-continuar").hidden = true;
    quizBox.hidden = false;
  }

  function answer(index, button) {
    const data = elementos[found];
    const r = missions.answer(index);
    if (!r) return;
    save(missions);
    for (const b of $("quiz-alternativas").children) b.disabled = true;
    button.classList.add(r.correct ? "certa" : "errada");
    const box = $("quiz-resultado");
    if (r.correct) {
      $("quiz-resultado-titulo").textContent = `✅ Acertou! ${starsText(r.stars)}`;
      $("quiz-resultado-texto").textContent = data.quiz.explicacao || "";
      $("quiz-resultado-extra").textContent = `Você ganhou a figurinha: ${data.icone || ""} ${data.titulo}`.trim();
      $("quiz-continuar").textContent = missions.finished ? "Ver meu álbum" : "Próxima missão";
    } else {
      // "perde a vez": não revela a resposta certa, a missão volta mais tarde
      $("quiz-resultado-titulo").textContent = "❌ Não foi dessa vez";
      $("quiz-resultado-texto").textContent = "Leia o painel com atenção. Essa missão volta mais tarde!";
      $("quiz-resultado-extra").textContent = "";
      $("quiz-continuar").textContent = "Continuar";
    }
    box.className = r.correct ? "certo" : "errado";
    box.hidden = false;
    $("quiz-continuar").hidden = false;
    $("quiz-continuar").focus();
  }

  function closeQuiz() {
    quizBox.hidden = true;
    found = null;
    otherId = null;
    if (missions.finished) openAlbum();
    renderBar(statusFor(null, 0));
  }

  // ------------------------------------------------------------ álbum
  function openAlbum() {
    $("album-titulo").textContent = missions.finished ? "🏆 Parabéns!" : "📒 Meu álbum";
    $("album-resumo").textContent = missions.finished
      ? `Você completou todas as missões e juntou ${missions.totalStars} de ${missions.total * 3} estrelas!`
      : `${missions.doneCount} de ${missions.total} figurinhas · ${missions.totalStars} ⭐`;
    $("album-grade").replaceChildren(
      ...missions.ids.map((id) => {
        const data = elementos[id];
        const got = missions.done[id];
        const card = document.createElement("div");
        card.className = got ? "figurinha" : "figurinha vazia";
        if (got) card.style.setProperty("--cor", data.cor);
        const icon = document.createElement("span");
        icon.className = "fig-icone";
        icon.textContent = got ? data.icone || "★" : "?";
        const name = document.createElement("span");
        name.className = "fig-nome";
        name.textContent = got ? data.titulo : "???";
        const stars = document.createElement("span");
        stars.className = "fig-estrelas";
        stars.textContent = got ? starsText(got) : "";
        card.append(icon, name, stars);
        return card;
      }),
    );
    resetButton.textContent = "Recomeçar";
    resetArmed = false;
    albumBox.hidden = false;
  }

  // Recomeçar pede um segundo toque (sem confirm(), que trava a página em alguns celulares).
  const resetButton = $("album-recomecar");
  let resetArmed = false;
  resetButton.onclick = () => {
    if (!resetArmed) {
      resetArmed = true;
      resetButton.textContent = "Toque de novo para apagar tudo";
      return;
    }
    missions.reset();
    save(missions);
    found = null;
    otherId = null;
    albumBox.hidden = true;
    renderBar(statusFor(null, 0));
  };

  $("responder").onclick = openQuiz;
  $("quiz-continuar").onclick = closeQuiz;
  $("abrir-album").onclick = openAlbum;
  $("album-fechar").onclick = () => (albumBox.hidden = true);

  return {
    available: missions.total > 0,
    start() {
      document.body.classList.add("modo-missoes");
      bar.hidden = false;
      renderBar(statusFor(null, 0));
    },
    update,
  };
}

/** Cabeçalho colorido igual ao do painel (ícone + título). */
function paintHeader(header, data) {
  header.style.setProperty("--cor", data.cor);
  header.style.setProperty("--cor-titulo", isLight(data.cor) ? "#141414" : "#ffffff");
  header.querySelector(".icone").textContent = data.icone || "";
  header.querySelector(".titulo").textContent = data.titulo;
}
