"""Missões com quiz: validação dos campos ``missao``/``quiz`` e exportação para o site."""

from __future__ import annotations

import json

import pytest

from conftest import ROOT
from core.content import ContentManager, ElementContent

QUIZ = {
    "pergunta": "Para que serve o trator?",
    "alternativas": ["Preparar o solo", "Ordenhar vacas", "Vender produtos"],
    "correta": 0,
    "explicacao": "Ele puxa o arado.",
}
BASE = {"id": "trator", "titulo": "Trator", "descricao": "Máquina agrícola."}


def write(path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_missao_valida():
    item = ElementContent.from_dict({**BASE, "missao": "  Encontre a máquina.  ", "quiz": QUIZ})
    assert item.missao == "Encontre a máquina."
    assert item.quiz is not None
    assert item.quiz.pergunta == "Para que serve o trator?"
    assert item.quiz.alternativas == ("Preparar o solo", "Ordenhar vacas", "Vender produtos")
    assert item.quiz.correta == 0 and item.quiz.explicacao == "Ele puxa o arado."
    assert item.avisos == () and item.extras == {}


def test_sem_missao_nao_gera_aviso():
    item = ElementContent.from_dict(BASE)
    assert item.missao is None and item.quiz is None and item.avisos == ()


def test_explicacao_e_opcional():
    quiz = {k: v for k, v in QUIZ.items() if k != "explicacao"}
    item = ElementContent.from_dict({**BASE, "missao": "m", "quiz": quiz})
    assert item.quiz is not None and item.quiz.explicacao == ""


@pytest.mark.parametrize(
    ("missao", "quiz", "trecho"),
    [
        ("Encontre.", None, "quiz"),  # missão sem pergunta
        (None, QUIZ, "missao"),  # pergunta sem missão
        ("", QUIZ, "missao"),
        ("Encontre.", "texto", "quiz"),
        ("Encontre.", {**QUIZ, "pergunta": " "}, "pergunta"),
        ("Encontre.", {**QUIZ, "alternativas": ["só uma"]}, "alternativas"),
        ("Encontre.", {**QUIZ, "alternativas": ["a", "b", "c", "d", "e"]}, "alternativas"),
        ("Encontre.", {**QUIZ, "alternativas": ["a", 2, "c"]}, "alternativas"),
        ("Encontre.", {**QUIZ, "alternativas": ["a", "", "c"]}, "alternativas"),
        ("Encontre.", {**QUIZ, "correta": 3}, "correta"),
        ("Encontre.", {**QUIZ, "correta": -1}, "correta"),
        ("Encontre.", {**QUIZ, "correta": True}, "correta"),
        ("Encontre.", {**QUIZ, "correta": "0"}, "correta"),
        ("Encontre.", {**QUIZ, "explicacao": 5}, "explicacao"),
    ],
)
def test_missao_invalida_vira_aviso_e_o_elemento_continua(missao, quiz, trecho):
    data = dict(BASE)
    if missao is not None:
        data["missao"] = missao
    if quiz is not None:
        data["quiz"] = quiz
    item = ElementContent.from_dict(data)
    assert item.titulo == "Trator"  # o painel continua funcionando
    assert item.missao is None and item.quiz is None
    assert len(item.avisos) == 1 and trecho in item.avisos[0]


def test_aviso_de_missao_aparece_nos_erros_do_carregamento(tmp_path):
    write(tmp_path / "trator.json", {**BASE, "missao": "m", "quiz": {**QUIZ, "correta": 9}})
    cm = ContentManager(tmp_path)
    assert cm.ids == ["trator"]
    assert len(cm.errors) == 1 and "trator.json" in cm.errors[0] and "correta" in cm.errors[0]


def test_conteudo_do_projeto_tem_missao_em_todos_os_elementos():
    cm = ContentManager(ROOT / "content")
    assert cm.errors == []
    for cid in cm.ids:
        item = cm.get(cid)
        assert item is not None and item.missao and item.quiz, cid
        assert len(item.quiz.alternativas) == 3, cid  # padrão do projeto: 3 alternativas


def test_exportacao_inclui_missao_e_quiz(tmp_path):
    from scripts.exportar_web import export_site

    content = tmp_path / "content"
    content.mkdir()
    write(content / "trator.json", {**BASE, "missao": "Encontre.", "quiz": QUIZ})
    write(content / "pecuaria.json", {"id": "pecuaria", "titulo": "Pecuária", "descricao": "d"})
    out = tmp_path / "site"
    export_site(out, content_dir=content, assets_dir=tmp_path / "assets")
    els = json.loads((out / "data" / "conteudo.json").read_text(encoding="utf-8"))["elementos"]
    assert els["trator"]["missao"] == "Encontre."
    assert els["trator"]["quiz"] == QUIZ
    assert els["pecuaria"]["missao"] is None and els["pecuaria"]["quiz"] is None
