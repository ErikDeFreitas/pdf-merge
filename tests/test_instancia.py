import logging

import pytest
from PySide6.QtWidgets import QApplication, QWidget
from tcm_ui.modulo import Contexto

from mesclador import dados, instancia
from mesclador.instancia import Mesclador


@pytest.fixture
def inst(qtbot):
    janela = QWidget()
    qtbot.addWidget(janela)
    objeto = Mesclador(Contexto("TCMSP\\teste", dados.PASTA, "avulso", logging.getLogger("t"), janela))
    yield objeto
    if objeto.tela is not None:
        qtbot.addWidget(objeto.tela)


def test_widget_e_criado_uma_vez(inst):
    assert inst.widget("mesclar") is inst.widget("mesclar")


def test_pagina_desconhecida(inst):
    with pytest.raises(KeyError):
        inst.widget("outra")


def test_sem_acoes_no_cabecalho(inst):
    assert inst.acoes_cabecalho("mesclar") == []


def test_pasta_inicial_vai_para_a_tela(inst, tmp_path, monkeypatch):
    monkeypatch.setattr(instancia, "PASTA_INICIAL", str(tmp_path))
    assert inst.widget("mesclar").input_pasta.text() == str(tmp_path)


def test_pode_fechar_so_sem_mesclagem(inst):
    assert inst.pode_fechar()  # antes de abrir a tela
    tela = inst.widget("mesclar")
    assert inst.pode_fechar()
    tela._thread = object()  # simula mesclagem em andamento
    assert not inst.pode_fechar()
    tela._thread = None


def test_ao_sair_do_programa_para_e_espera_a_thread(inst, monkeypatch):
    tela = inst.widget("mesclar")
    chamadas = []
    monkeypatch.setattr(tela, "parar", lambda: chamadas.append("parar"))
    monkeypatch.setattr(tela, "aguardar", lambda: chamadas.append("aguardar"))
    QApplication.instance().aboutToQuit.emit()
    assert chamadas == ["parar", "aguardar"]
