// Imagem do painel em tela cheia: os infográficos da maquete têm muito texto e
// ficam pequenos demais no painel. Toque na imagem do painel -> abre aqui;
// toque na imagem aberta -> amplia no ponto tocado (arrasta com o dedo).

export const ZOOM = 2.5; // ampliação do segundo toque (em relação a "caber na tela")

/**
 * Rolagem que deixa no centro da tela o ponto tocado depois de ampliar.
 * `fx`/`fy` = posição do toque na imagem (0..1); tamanhos em pixels.
 * O resultado fica entre 0 e o máximo que a área consegue rolar.
 */
export function zoomScroll(fx, fy, contentW, contentH, viewW, viewH) {
  const clamp = (v, max) => Math.min(Math.max(v, 0), Math.max(max, 0));
  return {
    left: Math.round(clamp(fx * contentW - viewW / 2, contentW - viewW)),
    top: Math.round(clamp(fy * contentH - viewH / 2, contentH - viewH)),
  };
}

/** Liga a janela `#visualizador` do index.html. Devolve `{ open(src, titulo), close() }`. */
export function createImageViewer(doc = document) {
  const box = doc.getElementById("visualizador");
  const area = doc.getElementById("visualizador-area");
  const img = doc.getElementById("visualizador-imagem");
  const closeButton = doc.getElementById("visualizador-fechar");

  const setZoom = (on, fx = 0.5, fy = 0.5) => {
    box.classList.toggle("ampliado", on);
    if (!on) {
      img.style.width = img.style.height = "";
      area.scrollTo(0, 0);
      return;
    }
    // tamanho "cabe na tela" × ZOOM, mantendo a proporção
    const fit = Math.min(area.clientWidth / img.naturalWidth, area.clientHeight / img.naturalHeight);
    const w = img.naturalWidth * fit * ZOOM;
    const h = img.naturalHeight * fit * ZOOM;
    img.style.width = `${w}px`;
    img.style.height = `${h}px`;
    const s = zoomScroll(fx, fy, w, h, area.clientWidth, area.clientHeight);
    area.scrollTo(s.left, s.top);
  };

  const close = () => {
    box.hidden = true;
    setZoom(false);
    img.removeAttribute("src");
  };

  img.addEventListener("click", (e) => {
    e.stopPropagation(); // não fecha a janela
    if (box.classList.contains("ampliado")) return setZoom(false);
    const r = img.getBoundingClientRect();
    setZoom(true, (e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height);
  });
  closeButton.addEventListener("click", close);
  box.addEventListener("click", (e) => {
    if (e.target === box || e.target === area) close(); // toque fora da imagem
  });
  doc.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !box.hidden) close();
  });

  return {
    open(src, titulo = "") {
      setZoom(false);
      img.src = src;
      img.alt = titulo ? `Imagem: ${titulo}` : "";
      box.hidden = false;
      closeButton.focus();
    },
    close,
  };
}
