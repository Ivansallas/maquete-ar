# Maquete AR

Realidade aumentada para uma maquete escolar de comunidade urbana/rural.
Uma webcam filma a maquete; cada elemento (agricultura, pecuária, trator...)
tem um **QR Code** e um **marcador ArUco** colados ao lado. O programa
reconhece o elemento e mostra um painel educativo — com texto, imagem ou
animação — que acompanha o marcador na tela, inclusive inclinado e em
perspectiva.

Funciona offline, num PC com Windows e uma webcam USB. Nenhuma imagem da
câmera é gravada ou enviada.

## Requisitos

- Windows 10/11 (também roda em Linux/macOS)
- Python 3.11 ou mais novo (desenvolvido com 3.12)
- Webcam USB (opcional para testar: existe um modo demonstração)
- Impressora para os marcadores

## Instalação

No terminal, dentro da pasta do projeto:

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

> Linux/macOS: troque `.venv\Scripts\` por `.venv/bin/` em todos os comandos.

## Preparar a maquete

1. Gere os marcadores:

   ```
   .venv\Scripts\python scripts\gerar_qrcodes.py
   ```

   Isso cria em `qrcodes/` a folha `folha_impressao_A4.png` (e páginas
   extras `_2`, `_3`... se houver muitos elementos), com cada QR (5 cm) e o
   ArUco do mesmo elemento (3 cm) lado a lado.

2. Imprima em **100% / "tamanho real"** (sem "ajustar à página").
3. Recorte cada dupla e cole **o QR e o ArUco juntos, no mesmo plano**, perto
   do elemento correspondente na maquete. Não dobre nem cubra a margem branca.

> Depois de impressos, **não mude** o `id` nem o número `aruco` de um
> elemento — os marcadores colados deixariam de corresponder ao conteúdo.

## Usar em aula

```
.venv\Scripts\python app.py
```

Aponte a câmera para a maquete. Os painéis aparecem para os elementos mais
próximos do centro da imagem — o aluno "mira" o que quer ler.

| Tecla | Ação |
|---|---|
| `ESC` ou `Q` | Sair |
| `D` | Liga/desliga o modo DEBUG (informações técnicas) |
| `S` | Salva uma captura da tela em `screenshots/` |

O programa **não fecha sozinho**: câmera desconectada, arquivo com erro ou
QR estranho viram avisos na tela, e ele continua tentando.

| Mensagem na etiqueta | Significado |
|---|---|
| Nome do elemento (verde) | Reconhecido |
| QR parcialmente visível — aproxime ou centralize | QR encontrado, mas não lido |
| QR inválido | QR que não é de um elemento da maquete |
| Conteúdo desconhecido: … | QR válido sem arquivo em `content/` |

**Sem câmera?** Para testar ou apresentar:

```
.venv\Scripts\python app.py --demo                              # maquete virtual animada
.venv\Scripts\python app.py --source qrcodes\demo_maquete.png   # imagem ou vídeo
.venv\Scripts\python app.py --source 1                          # outra câmera
```

## Editar o conteúdo

Cada elemento é um arquivo em `content/` — o professor pode mudar os textos
sem mexer em código. Exemplo (`content/pecuaria.json`):

```json
{
    "id": "pecuaria",
    "titulo": "Pecuária",
    "icone": "🐄",
    "descricao": "Criação de animais como bois, vacas, porcos, galinhas e cabras para produção de carne, leite, ovos, couro e lã.",
    "cor": "brown",
    "aruco": 5
}
```

| Campo | Obrigatório | Descrição |
|---|---|---|
| `id` | sim | Igual ao nome do arquivo; só `a-z`, `0-9` e `_`. É o texto do QR. |
| `titulo` | sim | Título do painel. |
| `descricao` | sim | 2–3 frases curtas (~200 caracteres) para caber na tela. |
| `icone` | não | Um emoji. |
| `cor` | não | `green`, `darkgreen`, `brown`, `orange`, `gray`, `blue`, `red`, `yellow`, `purple`, `cyan`, `white` ou `#RRGGBB`. |
| `aruco` | não | Número do ArUco do elemento (0–999, sem repetir). |
| `imagem` | não | Imagem do painel, relativa a `assets/` (ex.: `"images/trator.jpg"`). PNG, JPG, WEBP ou BMP, até 15 MB. |
| `animacao` | não | GIF, WebP ou PNG animado, relativo a `assets/` (ex.: `"animations/plantio.gif"`). Toca em loop; prefira até ~10 s. |

- Se `animacao` e `imagem` existirem, a animação é usada e a imagem serve de
  reserva. Arquivo ausente ou corrompido não some com o elemento: aparece um
  aviso e o painel é mostrado só com o que funcionar.
- Use apenas imagens que a escola tem direito de usar (fotos próprias,
  licenças livres).
- Os 8 elementos básicos (agricultura, comércio, indústria, infraestrutura,
  meio ambiente, pecuária, residência, trator) devem sempre existir.

**Novo elemento:** crie `content/<id>.json` com o próximo número `aruco`
livre (os básicos usam 0–7), rode `scripts\gerar_qrcodes.py` e imprima a
nova dupla.

## Configuração

`config.json` traz as opções; qualquer chave omitida usa o padrão de
`core/config.py`. As mais usadas:

| Chave | Para quê |
|---|---|
| `camera.index` | Qual webcam usar (0 = primeira). |
| `camera.mirror` | Espelhar a imagem. |
| `debug` | Começar com o modo DEBUG ligado. |
| `ar.max_panels` | Quantos painéis ao mesmo tempo (0 = todos). Com imagens/animações, 1–2 deixa a tela mais limpa. |
| `ar.mode` | `perspective` (painel inclina com o marcador) ou `billboard` (sempre de frente). |
| `window.fullscreen` | Abrir em tela cheia. |
| `aruco.marker_length_m` | Lado do ArUco impresso em metros (padrão 0,03). |

## Problemas comuns

| Problema | O que fazer |
|---|---|
| "Câmera indisponível" | Rode `.venv\Scripts\python scripts\testar_camera.py --list` e ponha o índice certo em `camera.index`. Feche Teams/Zoom/navegador que estejam usando a câmera. |
| QR não é lido | Aproxime a câmera, melhore a luz e evite reflexos. O ArUco ao lado costuma ser reconhecido de mais longe. |
| Painel no lugar errado logo no início | Mostre o QR e o ArUco juntos e de perto por um instante: o programa aprende a posição do QR em relação ao ArUco. |
| Aviso "arquivo(s) de conteúdo com erro" | Veja a mensagem no terminal: indica o arquivo e o campo com problema. |
| Acentos estranhos no terminal | Use o Windows Terminal; o programa já configura UTF-8. |

## Desenvolvimento

```
.venv\Scripts\python -m pytest -q                                       # testes (sem câmera)
.venv\Scripts\ruff check . && .venv\Scripts\ruff format . && .venv\Scripts\mypy
.venv\Scripts\python app.py --demo --headless --frames 60 --save out.png  # roda sem janela e salva o quadro
```

```
app.py      ponto de entrada (câmera → QR + ArUco → fusão → rastreamento → painéis)
core/       configuração, conteúdo JSON, carga segura de imagens/animações
camera/     webcam, arquivo, modo demo, calibração
qr/         leitura, validação e geração dos QR Codes
vision/     homografia, rastreamento, ArUco, fusão QR + ArUco
ar/         painéis, textos, animações, composição do quadro
content/    um JSON por elemento
assets/     images/, animations/ (e pastas para as próximas fases)
scripts/    gerar_qrcodes.py, gerar_aruco.py, testar_camera.py
tests/      testes automatizados
```

Decisões de arquitetura, regras de negócio, segurança e padrões de código
estão em [`agent_docs/`](agent_docs/) e [`CLAUDE.md`](CLAUDE.md). Commits seguem
Conventional Commits (`feat:`, `fix:`, `docs:`...).

## Etapas do projeto

| Fase | Conteúdo | Situação |
|---|---|---|
| 1 | QR Code + painel de texto em perspectiva | ✅ |
| 2 | Imagens nos painéis | ✅ |
| 3 | Animações (GIF/WebP/APNG) | ✅ |
| 4 | ArUco por elemento, fundido com o QR | ✅ |
| 5 | Reconhecimento de objetos (YOLO) | — |
| 6 | Modelos 3D | — |
| 7 | Realidade aumentada completa | — |
