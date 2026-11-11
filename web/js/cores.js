// Cor de texto legível sobre a cor do elemento (título do painel, quiz, álbum).

/** true se a cor "#rrggbb" é clara (texto escuro por cima). */
export function isLight(hex) {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  return 0.299 * r + 0.587 * g + 0.114 * b > 160;
}
