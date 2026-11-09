// Maquete AR no celular: câmera -> QR (jsQR) + ArUco (js-aruco2) -> fusão ->
// rastreamento -> painel HTML em perspectiva (ou cartão fixo embaixo).
// Mesmas regras do programa do PC (ver agent_docs/architecture.md).

import { UNIT_SQUARE, center, cssMatrix3d, dist, homography, projectAll, quadIsConvex, rectCorners } from "./geometry.js";
import { Fusion, Tracker, parseQrText } from "./markers.js";

// Mesmos parâmetros do config.json do PC (seção "ar").
const PANEL_WIDTH_SIDES = 3.2; // largura do painel em "lados do QR"
const PANEL_GAP_SIDES = 0.25; // distância entre QR e painel
const MIN_PANEL_PX = 200; // abaixo disso o texto fica pequeno demais: usa o cartão
const MAX_DISTORTION = 2.5; // razão entre bordas opostas acima disso: usa o cartão
const DETECT_MAX_WIDTH = 960; // a detecção roda numa cópia reduzida (ArUco precisa de ~50 px nela)
const DETECT_INTERVAL_MS = 60; // ~16 detecções por segundo (poupa bateria)
const CARD_KEEP_SECONDS = 6; // cartão continua na tela depois que o QR some (para ler)

const $ = (id) => document.getElementById(id);
const video = $("camera");
const testImage = $("imagem-teste");
const outlines = $("contornos");
const arLayer = $("camada-ar");
const card = $("cartao");
const hint = $("dica");
const params = new URLSearchParams(location.search);
// ?debug=1 mostra na tela o que foi detectado e os erros (diagnóstico em celular real)
const DEBUG = params.get("debug") === "1";
const debugInfo = { frames: 0, qr: "-", aruco: 0, size: "-", error: "", attempts: [] };
if (DEBUG) {
  addEventListener("error", (e) => (debugInfo.error = String(e.message)));
  addEventListener("unhandledrejection", (e) => (debugInfo.error = String(e.reason)));
}

const state = {
  content: null, // { elementos: {id: {...}}, aruco: {"7": "trator"} }
  source: null, // <video> ou <img> de teste
  fusion: null,
  tracker: new Tracker({ smoothing: 0.5, keepSeconds: 0.6 }),
  arucoDetector: null,
  canvas: document.createElement("canvas"),
  lastDetect: 0,
  panels: new Map(), // id -> { el, w, h }
  cardId: null,
  cardUntil: 0,
  qrSide: new Map(), // elemento -> lado do ArUco onde o QR foi achado (esquerda/direita/acima/abaixo)
  lastProblem: null, // { text, until }
};

// ------------------------------------------------------------------ conteúdo
async function loadContent() {
  const response = await fetch("data/conteudo.json", { cache: "no-cache" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

/** Monta o painel de um elemento. Só textContent/atributos: nada vira HTML. */
function buildPanel(id) {
  const data = state.content.elementos[id];
  const el = $("modelo-painel").content.firstElementChild.cloneNode(true);
  el.style.setProperty("--cor", data.cor);
  el.style.setProperty("--cor-titulo", isLight(data.cor) ? "#141414" : "#ffffff");
  el.querySelector(".icone").textContent = data.icone || "";
  el.querySelector(".titulo").textContent = data.titulo;
  el.querySelector(".descricao").textContent = data.descricao;
  const media = data.animacao || data.imagem; // animação tem prioridade; GIF anima sozinho
  const img = el.querySelector(".midia");
  if (media) {
    img.hidden = false;
    img.src = media;
    img.onerror = () => (img.hidden = true); // arquivo com problema: fica só o texto
  }
  return el;
}

function isLight(hex) {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  return 0.299 * r + 0.587 * g + 0.114 * b > 160;
}

/** Painel em perspectiva (criado uma vez por elemento e medido no tamanho natural). */
function arPanel(id) {
  let p = state.panels.get(id);
  if (!p) {
    const el = buildPanel(id);
    el.style.opacity = "0";
    arLayer.append(el);
    p = { el, w: 0, h: 0 };
    const measure = () => {
      p.w = el.offsetWidth;
      p.h = el.offsetHeight;
    };
    measure();
    el.querySelector(".midia").addEventListener("load", measure);
    state.panels.set(id, p);
  }
  return p;
}

function showCard(id) {
  if (state.cardId === id && !card.hidden) return;
  state.cardId = id;
  card.replaceChildren(buildPanel(id));
  const close = document.createElement("button");
  close.className = "fechar";
  close.type = "button";
  close.setAttribute("aria-label", "Fechar");
  close.textContent = "×";
  close.onclick = () => {
    card.hidden = true;
    state.cardUntil = 0;
  };
  card.append(close);
  card.hidden = false;
}

// ------------------------------------------------------------------ câmera
async function startCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Este navegador não permite usar a câmera. Use o Chrome ou o Safari atualizados.");
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
  });
  video.srcObject = stream;
  await video.play();
  return video;
}

async function startTestImage() {
  testImage.hidden = false;
  video.hidden = true;
  await new Promise((resolve, reject) => {
    testImage.onload = resolve;
    testImage.onerror = () => reject(new Error("Imagem de teste não encontrada (data/teste.png)."));
    testImage.src = "data/teste.png";
  });
  return testImage;
}

function sourceSize(src) {
  return src instanceof HTMLVideoElement ? [src.videoWidth, src.videoHeight] : [src.naturalWidth, src.naturalHeight];
}

/** Converte pixels da imagem de detecção em pixels da tela (mesma regra do object-fit: cover). */
function toScreen(points, detectScale, [sw, sh]) {
  const W = innerWidth, H = innerHeight;
  const s = Math.max(W / sw, H / sh);
  const ox = (W - sw * s) / 2, oy = (H - sh * s) / 2;
  return points.map(([x, y]) => [(x / detectScale) * s + ox, (y / detectScale) * s + oy]);
}

// ------------------------------------------------------------------ detecção
function detect(now) {
  const src = state.source;
  const [sw, sh] = sourceSize(src);
  if (!sw || !sh) return;
  const maxWidth = DEBUG && Number(params.get("detw")) > 0 ? Number(params.get("detw")) : DETECT_MAX_WIDTH;
  const scale = Math.min(1, maxWidth / sw);
  const w = Math.round(sw * scale), h = Math.round(sh * scale);
  const c = state.canvas;
  if (c.width !== w || c.height !== h) Object.assign(c, { width: w, height: h });
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(src, 0, 0, w, h);
  const image = ctx.getImageData(0, 0, w, h);

  const rawArucos = state.arucoDetector.detect(image);
  const qrs = readQrs(ctx, image, rawArucos, now);
  const scr = (pts) => toScreen(pts, scale, [sw, sh]);
  const arucos = rawArucos.map((m) => ({ id: m.id, corners: scr(m.corners.map((p) => [p.x, p.y])) }));

  const tracks = state.tracker.update(
    state.fusion.update(
      qrs.map((q) => ({ id: q.id, corners: scr(q.corners) })),
      arucos,
    ),
    now / 1000,
  );
  if (DEBUG) {
    debugInfo.frames++;
    debugInfo.qr = qrs.map((q) => q.id).join(",") || "-";
    debugInfo.aruco = arucos.map((a) => a.id).join(",") || "0";
    debugInfo.size = `${w}x${h}`;
  }
  render(tracks, now);
}

/**
 * Lê os QR Codes do quadro. O jsQR lê um QR por vez e se confunde quando há
 * vários na imagem (mistura os "olhos" de QRs diferentes). Por isso, se a
 * imagem inteira falhar, tentamos recortes: o centro (para onde o aluno mira)
 * e a vizinhança de cada ArUco encontrado (o QR está colado ao lado dele).
 * Devolve `[{ id, corners }]` em pixels da imagem de detecção.
 */
function readQrs(ctx, frameImage, rawArucos, now) {
  let image = frameImage;
  const { width: w, height: h } = image;
  const found = new Map();
  if (DEBUG) debugInfo.attempts = [];
  // O ArUco (quadrado preto com borda) parece um "olho" de QR e confunde o jsQR:
  // pintamos de branco os ArUcos já encontrados, só nesta cópia interna da imagem.
  if (rawArucos.length) {
    ctx.fillStyle = "#fff";
    for (const m of rawArucos) {
      const c = center(m.corners.map((p) => [p.x, p.y]));
      ctx.beginPath();
      m.corners.forEach((p, i) => {
        const x = c[0] + (p.x - c[0]) * 1.25, y = c[1] + (p.y - c[1]) * 1.25; // +25%: cobre a borda
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.closePath();
      ctx.fill();
    }
    image = ctx.getImageData(0, 0, w, h);
  }
  const attempt = (x, y, cw, ch) => {
    x = Math.max(0, Math.round(x));
    y = Math.max(0, Math.round(y));
    cw = Math.min(w - x, Math.round(cw));
    ch = Math.min(h - y, Math.round(ch));
    if (DEBUG) debugInfo.attempts.push(`${x},${y},${cw}x${ch}`);
    if (cw < 40 || ch < 40) return;
    const data = x === 0 && y === 0 && cw === w && ch === h ? image : ctx.getImageData(x, y, cw, ch);
    const code = window.jsQR(data.data, cw, ch, { inversionAttempts: "dontInvert" });
    if (!code) return;
    const id = parseQrText(code.data);
    if (!id || !state.content.elementos[id]) {
      problem(id ? `Elemento não cadastrado: ${id}` : "Este QR Code não é da maquete", now);
      return;
    }
    const L = code.location;
    const pts = [L.topLeftCorner, L.topRightCorner, L.bottomRightCorner, L.bottomLeftCorner];
    if (!found.has(id)) found.set(id, { id, corners: pts.map((p) => [p.x + x, p.y + y]) });
  };

  attempt(0, 0, w, h);
  if (found.size === 0) attempt(w * 0.2, h * 0.15, w * 0.6, h * 0.7); // centro
  // vizinhança dos ArUcos ainda sem QR lido (no máximo 3 por quadro: bateria)
  const byCenter = rawArucos
    .map((m) => ({ m, c: center(m.corners.map((p) => [p.x, p.y])) }))
    .filter(({ m }) => !found.has(state.content.aruco[String(m.id)]))
    .sort((a, b) => dist(a.c, [w / 2, h / 2]) - dist(b.c, [w / 2, h / 2]))
    .slice(0, 3);
  state.frame = (state.frame || 0) + 1;
  for (const { m, c } of byCenter) {
    const id = state.content.aruco[String(m.id)];
    if (!id || found.has(id)) continue;
    const corners = m.corners.map((p) => [p.x, p.y]);
    // 1) já aprendido: recorte justo onde o QR está (com 25% de folga)
    const predicted = state.fusion.predict(id, corners);
    if (predicted) {
      const xs = predicted.map((p) => p[0]), ys = predicted.map((p) => p[1]);
      const pad = 0.25 * Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
      attempt(Math.min(...xs) - pad, Math.min(...ys) - pad, Math.max(...xs) - Math.min(...xs) + 2 * pad, Math.max(...ys) - Math.min(...ys) + 2 * pad);
      continue;
    }
    // 2) ainda não: o QR está colado em UM lado do ArUco. Um recorte que pegue
    // dois lados acaba pegando o QR do vizinho, e com 2 QRs o jsQR falha.
    // Tenta o lado que já deu certo (padrão: esquerda, como na folha impressa)
    // e, a cada quadro, mais um lado em rodízio.
    const side = Math.max(...corners.map((p, i) => dist(p, corners[(i + 1) % 4])));
    const S = 2.8 * side; // QR impresso tem ~1,7 lado de ArUco; folga para a margem branca
    const boxes = {
      esquerda: [c[0] - 0.6 * side - S, c[1] - S / 2],
      direita: [c[0] + 0.6 * side, c[1] - S / 2],
      acima: [c[0] - S / 2, c[1] - 0.6 * side - S],
      abaixo: [c[0] - S / 2, c[1] + 0.6 * side],
    };
    const preferred = state.qrSide.get(id) ?? "esquerda";
    const rotating = Object.keys(boxes)[state.frame % 4];
    for (const where of new Set([preferred, rotating])) {
      attempt(boxes[where][0], boxes[where][1], S, S);
      if (found.has(id)) {
        state.qrSide.set(id, where);
        break;
      }
    }
  }
  return [...found.values()];
}

function problem(text, now) {
  state.lastProblem = { text, until: now + 2500 };
}

// ------------------------------------------------------------------ desenho
function render(tracks, now) {
  // contornos
  outlines.replaceChildren(
    ...tracks.map((t) => {
      const poly = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
      poly.setAttribute("points", t.corners.map((p) => p.join(",")).join(" "));
      if (!t.visible) poly.classList.add("perdido");
      return poly;
    }),
  );

  // o aluno "mira": vale o elemento mais perto do centro da tela
  const mid = [innerWidth / 2, innerHeight / 2];
  const main = tracks.slice().sort((a, b) => dist(center(a.corners), mid) - dist(center(b.corners), mid))[0];

  let placed = null;
  if (main) {
    const p = arPanel(main.id);
    const quad = perspectiveQuad(main.corners, p);
    if (quad) {
      const H = homography(rectCorners(p.w, p.h), quad);
      if (H) {
        p.el.style.transform = `matrix3d(${cssMatrix3d(H).join(",")})`;
        p.el.style.opacity = main.visible ? "1" : "0.6";
        placed = main.id;
        card.hidden = true;
      }
    }
    if (!placed) {
      showCard(main.id); // não cabe em perspectiva: cartão legível embaixo
      state.cardUntil = now / 1000 + CARD_KEEP_SECONDS;
    }
  }
  for (const [id, p] of state.panels) if (id !== placed) p.el.style.opacity = "0";
  if (!main && !card.hidden && now / 1000 > state.cardUntil) card.hidden = true;

  // dica no topo
  if (state.lastProblem && now < state.lastProblem.until) setHint(state.lastProblem.text, true);
  else if (main) setHint(state.content.elementos[main.id].titulo + (main.viaAruco ? " (pelo marcador)" : ""));
  else setHint("Aponte a câmera para um QR Code da maquete");
}

/** Quadrilátero do painel acima do QR, ou null se não ficar legível/inteiro na tela. */
function perspectiveQuad(corners, p) {
  if (!p.w || !p.h) return null;
  const Hm = homography(UNIT_SQUARE, corners);
  if (!Hm) return null;
  const w = PANEL_WIDTH_SIDES, h = w * (p.h / p.w);
  const quad = projectAll(Hm, rectCorners(w, h, 0.5 - w / 2, -PANEL_GAP_SIDES - h));
  if (!quadIsConvex(quad)) return null;
  const top = dist(quad[0], quad[1]), bottom = dist(quad[3], quad[2]);
  if (Math.min(top, bottom) < MIN_PANEL_PX || Math.max(top, bottom) / Math.min(top, bottom) > MAX_DISTORTION) return null;
  const inside = quad.every(([x, y]) => x >= 0 && y >= 0 && x <= innerWidth && y <= innerHeight);
  return inside ? quad : null;
}

function setHint(text, warn = false) {
  if (DEBUG) {
    const d = debugInfo;
    text = `${text} | quadros ${d.frames} | ${d.size} | QR: ${d.qr} | ArUco: ${d.aruco} | tentativas: ${d.attempts.join(" ")}${d.error ? " | ERRO: " + d.error : ""}`;
  }
  if (hint.textContent !== text) hint.textContent = text;
  hint.classList.toggle("aviso", warn);
}

function loop(now) {
  if (now - state.lastDetect >= DETECT_INTERVAL_MS) {
    state.lastDetect = now;
    try {
      detect(now);
    } catch (err) {
      console.error(err); // um quadro ruim não pode travar a página
      if (DEBUG) {
        debugInfo.error = String(err && err.stack ? err.stack.split("\n").slice(0, 2).join(" ") : err);
        setHint("falha na detecção");
      }
    }
  }
  requestAnimationFrame(loop);
}

// ------------------------------------------------------------------ início
async function main() {
  const button = $("abrir-camera");
  const error = $("inicio-erro");
  try {
    state.content = await loadContent();
  } catch (err) {
    hint.textContent = "Não foi possível carregar o conteúdo. Verifique a internet e recarregue a página.";
    error.textContent = hint.textContent;
    error.hidden = false;
    console.error(err);
    return;
  }
  state.fusion = new Fusion(state.content.aruco);
  state.arucoDetector = new window.AR.Detector({ dictionaryName: "ARUCO_4X4_1000", maxHammingDistance: 1 });

  // aberto pelo QR (link ?e=<id>): mostra o elemento já, mesmo antes da câmera
  const fromLink = parseQrText(params.get("e") ?? "");
  if (fromLink && state.content.elementos[fromLink]) {
    const p = $("inicio-elemento");
    p.textContent = `Você está no elemento: ${state.content.elementos[fromLink].titulo}`;
    p.hidden = false;
  }

  const start = async () => {
    button.disabled = true;
    error.hidden = true;
    try {
      state.source = params.get("teste") === "1" ? await startTestImage() : await startCamera();
      $("inicio").hidden = true;
      if (fromLink && state.content.elementos[fromLink]) {
        showCard(fromLink);
        state.cardUntil = performance.now() / 1000 + CARD_KEEP_SECONDS;
      }
      requestAnimationFrame(loop);
    } catch (err) {
      console.error(err);
      error.textContent =
        err && err.name === "NotAllowedError"
          ? "A câmera foi bloqueada. Toque no cadeado ao lado do endereço, permita a câmera e tente de novo."
          : err && err.name === "NotFoundError"
            ? "Nenhuma câmera encontrada neste aparelho."
            : String(err.message || err);
      error.hidden = false;
      button.disabled = false;
      if (fromLink && state.content.elementos[fromLink]) showCard(fromLink); // pelo menos o conteúdo
    }
  };
  button.onclick = start;
  button.disabled = false;
  hint.textContent = "";
  if (params.get("teste") === "1") start(); // modo de teste: sem toque
}

main();
