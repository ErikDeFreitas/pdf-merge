import logging
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from tcm_ui.components import Etiqueta
from tcm_ui.modulo import Contexto

from mesclador import dados, tela as modulo_tela
from mesclador.mesclagem import Status
from mesclador.tela import DialogoDetalhes, TelaMesclar

from test_mesclagem import _fatura, _pdf


@pytest.fixture
def contexto(qtbot):
    janela = QWidget()
    qtbot.addWidget(janela)
    return Contexto("TCMSP\\teste", dados.PASTA, "avulso", logging.getLogger("t"), janela)


@pytest.fixture
def tela(qtbot, contexto):
    t = TelaMesclar(contexto)
    qtbot.addWidget(t)
    return t


@pytest.fixture
def pasta_faturas(tmp_path):
    base = tmp_path / "faturas"
    _fatura(base / "100")
    _fatura(base / "300")
    (base / "200").mkdir()
    _pdf(base / "200" / "2.pdf", None)  # sem PDF da fatura: pulada
    return base


def mesclar(qtbot, tela, pasta):
    tela.input_pasta.setText(str(pasta))
    tela._iniciar()
    qtbot.waitUntil(lambda: not tela.rodando, timeout=30000)


def test_pasta_inexistente_mostra_erro_no_campo(tela, tmp_path):
    tela.input_pasta.setText(str(tmp_path / "nao_existe"))
    tela._iniciar()
    assert tela.input_pasta.property("erro") is True
    assert not tela.rodando


def test_sem_pasta_pede_a_pasta(tela):
    tela._iniciar()
    assert tela.input_pasta.property("erro") is True


def test_mesclar_preenche_tabela_e_indicadores(qtbot, tela, pasta_faturas):
    mesclar(qtbot, tela, pasta_faturas)
    assert tela.tabela.rowCount() == 3
    assert tela.ind_total._valor.text() == "3"
    assert tela.ind_ok._valor.text() == "2"
    assert tela.ind_aviso._valor.text() == "0"
    assert tela.ind_falha._valor.text() == "1"
    assert (pasta_faturas / "100.pdf").exists()
    assert tela.btn_saida.isEnabled()
    assert "2 de 3 faturas geradas" in tela.lbl_progresso.text()
    resultado = tela.tabela.item(0, 0).data(Qt.UserRole + 1)
    assert resultado.pasta == "100" and resultado.status == Status.OK


def test_clicar_no_status_abre_o_dialogo(qtbot, tela, pasta_faturas, monkeypatch):
    abertos = []
    monkeypatch.setattr(DialogoDetalhes, "exec", lambda self: abertos.append(self) or 0)
    mesclar(qtbot, tela, pasta_faturas)
    etiqueta = tela.tabela.cellWidget(0, 0).findChild(Etiqueta)
    etiqueta.clicada.emit()
    assert len(abertos) == 1
    assert abertos[0].windowTitle() == "Fatura 100 · OK"


def test_filtro_por_status_esconde_linhas(qtbot, tela, pasta_faturas):
    mesclar(qtbot, tela, pasta_faturas)
    tela.filtro.setCurrentIndex(tela.filtro.findText(Status.PULADA.value))
    assert [tela.tabela.isRowHidden(i) for i in range(3)] == [True, False, True]
    tela.filtro.setCurrentIndex(0)
    assert not any(tela.tabela.isRowHidden(i) for i in range(3))


def test_busca_filtra_por_texto(qtbot, tela, pasta_faturas):
    mesclar(qtbot, tela, pasta_faturas)
    tela.busca.setText("300")
    assert [tela.tabela.isRowHidden(i) for i in range(3)] == [True, True, False]


def test_limpar_zera_tudo(qtbot, tela, pasta_faturas):
    mesclar(qtbot, tela, pasta_faturas)
    tela.limpar()
    assert tela.tabela.rowCount() == 0
    assert tela.input_pasta.text() == ""
    assert tela.ind_total._valor.text() == "—"
    assert not tela.btn_saida.isEnabled()


def test_duplo_clique_abre_o_pdf_gerado(qtbot, tela, pasta_faturas, monkeypatch):
    abertos = []
    monkeypatch.setattr(modulo_tela, "abrir", lambda caminho: abertos.append(caminho))
    mesclar(qtbot, tela, pasta_faturas)
    tela._abrir_linha(0, 1)
    assert abertos == [pasta_faturas / "100.pdf"]


def test_dialogo_de_detalhes_copia_com_a_versao(qtbot, contexto, pasta_faturas):
    from PySide6.QtWidgets import QApplication
    import mesclador
    from mesclador import mesclagem
    r = mesclagem.processar(pasta_faturas).resultados[0]
    dialogo = DialogoDetalhes(r, mesclador.__version__, contexto.janela)
    qtbot.addWidget(dialogo)
    dialogo._copiar()
    assert QApplication.clipboard().text().startswith(f"Mesclador de PDFs {mesclador.__version__} · ")
    assert dialogo.btn_copiar.text().strip() == "Copiado!"


def test_fechar_durante_mesclagem_real_para_e_solta_a_thread(qtbot, tela, tmp_path, monkeypatch):
    import threading
    import time

    from PySide6.QtWidgets import QApplication
    from mesclador import mesclagem

    base = tmp_path / "muitas"
    for numero in range(100, 105):
        _fatura(base / str(numero))
    original = mesclagem.mesclar_pasta
    primeira_pronta = threading.Event()

    def mesclar_e_segurar(*args, **kwargs):
        resultado = original(*args, **kwargs)
        if not primeira_pronta.is_set():
            primeira_pronta.set()
            # segura a thread até o cancelamento chegar: garante que ainda restam pastas
            limite = time.monotonic() + 20
            while not tela._worker._cancelar and time.monotonic() < limite:
                time.sleep(0.005)
        return resultado

    monkeypatch.setattr(mesclagem, "mesclar_pasta", mesclar_e_segurar)
    tela.input_pasta.setText(str(base))
    tela._iniciar()
    thread = tela._thread
    assert thread is not None
    qtbot.waitUntil(primeira_pronta.is_set, timeout=30000)
    QApplication.instance().aboutToQuit.emit()  # o que acontece ao fechar o programa
    assert thread.isFinished()
    qtbot.waitUntil(lambda: not tela.rodando, timeout=30000)
    assert tela.tabela.rowCount() == 1  # parou depois da pasta atual; as outras 4 não rodaram
    assert not list(base.rglob("*.tmp"))
