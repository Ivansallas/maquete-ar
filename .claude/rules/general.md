# General Conventions

- **Language split**: user-facing text (UI messages, content JSON, README, CLI
  output) in Brazilian Portuguese; identifiers follow the existing code (class
  names in English, domain words in Portuguese where already used, e.g.
  `titulo`, `descricao`). Docstrings/comments in Portuguese (didactic project).
- **Type hints on every function**; `mypy` must pass.
- **Commits**: Conventional Commits — `feat:`, `fix:`, `docs:`, `test:`,
  `refactor:`, `chore:` (e.g. `feat(ar): painel com imagem`).
- **Branches** (once Git is set up): `feat/<short-name>`, `fix/<short-name>`.
- Formatting/import order are enforced by `ruff format` / `ruff check` — don't
  hand-format against them.
