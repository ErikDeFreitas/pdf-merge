"""
Mesclador de PDFs — aplicação desktop (PySide6).

Uso:   python main.py                  -> abre a janela
       python main.py "C:\\Pasta"       -> abre a janela com a pasta preenchida
       python -m core "C:\\Pasta"       -> modo terminal, sem janela
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QStackedWidget, QWidget

from core import atualizacao, mesclagem
from core.mesclagem import Status
from core.worker import MesclarWorker
from ui import components as c
from ui import icons
from ui.atualizacao import VerificadorAtualizacao
from ui.themes import APLICACAO, ORGANIZACAO, SIZE, SPACE, theme_manager
from version import __version__

STATUS_TONE = {
    Status.OK: "success",
    Status.AVISO: "warning",
    Status.PULADA: "danger",
    Status.ERRO: "danger",
}


def abrir(caminho: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(caminho)))


class DetalhesModal(c.Modal):
    """Detalhes de uma fatura: o que aconteceu e quais arquivos entraram (ou não) no PDF."""

    def __init__(self, r: mesclagem.Resultado, parent=None):
        tone = STATUS_TONE[r.status]
        icone = {"success": "check-circle", "warning": "alert-triangle"}.get(tone, "x-circle")
        super().__init__(f"Fatura {r.pasta} · {r.status.value}", "", icone, tone, parent)
        self._r = r

        if r.caminho:  # caminho longo: abrevia no meio (o completo fica no tooltip e no "Copiar")
            caminho = c.Label("", "muted")
            largura = SIZE["modal"] - 2 * SPACE["xl"]
            caminho.setText(caminho.fontMetrics().elidedText(str(r.caminho), Qt.TextElideMode.ElideMiddle, largura))
            caminho.setToolTip(str(r.caminho))
            self.body.addWidget(caminho)

        problemas = list(r.mensagens)
        if r.nds_desconsideradas:
            problemas.append(f"ND sem Fiscal desconsiderada: {', '.join(r.nds_desconsideradas)}.")
        self.body.addWidget(c.Label("O que aconteceu", "label"))
        if r.saida:
            self.body.addWidget(c.Label(
                f"PDF gerado: {r.saida.name} · {r.total_paginas} páginas ({r.composicao()})", wrap=True))
        else:
            self.body.addWidget(c.Label("PDF não gerado.", wrap=True))
        for msg in problemas:
            self.body.addWidget(c.Label(f"•  {msg[:1].upper()}{msg[1:]}", wrap=True))
        if not problemas:
            self.body.addWidget(c.Label("Nenhum problema encontrado.", "muted"))

        self.body.addSpacing(SPACE["sm"])
        self.body.addWidget(c.Label("Arquivos da pasta", "label"))
        for nome in r.arquivos:
            usado = nome in r.usados
            self.body.addLayout(c.hbox(
                c.Icon("file-text", "text_muted", SIZE["icon_sm"]), c.Label(nome), None,
                c.Badge("Usado" if usado else "Não usado", "success" if usado else "warning"),
                spacing=SPACE["sm"],
            ))
        if not r.arquivos:
            self.body.addWidget(c.Label("Nenhum arquivo na pasta.", "muted"))

        self.btn_copiar = c.Button("Copiar detalhes", "secondary", icon="copy")
        self.btn_copiar.setToolTip("Copia o texto completo para colar numa mensagem de suporte")
        self.btn_copiar.clicked.connect(self._copiar)
        self.footer.addWidget(self.btn_copiar)
        if r.caminho:
            btn_pasta = c.Button("Abrir pasta", "secondary", icon="folder-open")
            btn_pasta.clicked.connect(lambda: abrir(r.caminho))
            self.footer.addWidget(btn_pasta)
        self.add_button("Fechar", "primary", accept=True)

    def _copiar(self) -> None:
        cabecalho = f"Mesclador de PDFs {__version__} · {datetime.now():%d/%m/%Y %H:%M}"
        QApplication.clipboard().setText(f"{cabecalho}\n{self._r.relatorio()}")
        self.btn_copiar.setText("Copiado!")
        self.btn_copiar.set_icon_name("check")
        QTimer.singleShot(2000, self._restaurar_copiar)

    def _restaurar_copiar(self) -> None:
        self.btn_copiar.setText("Copiar detalhes")
        self.btn_copiar.set_icon_name("copy")


# ---------------------------------------------------------------------------
# Página: Mesclar PDFs
# ---------------------------------------------------------------------------
class MesclarPage(c.Page):
    def __init__(self, pasta_inicial: str = ""):
        super().__init__()
        self._thread: QThread | None = None
        self._worker: MesclarWorker | None = None
        self._execucao: mesclagem.Execucao | None = None
        self._contagem = {s: 0 for s in Status}

        # --- Origem -------------------------------------------------------
        self.input_pasta = c.Input("Selecione a pasta que contém uma subpasta por fatura")
        self.input_pasta.returnPressed.connect(self._iniciar)
        # Conta as faturas assim que a pasta é escolhida ou digitada.
        self._timer_contagem = QTimer(self, singleShot=True, interval=300)
        self._timer_contagem.timeout.connect(self._contar_faturas)
        self.input_pasta.textChanged.connect(self._timer_contagem.start)
        self.btn_procurar = c.Button("Procurar", "secondary", icon="folder-open")
        self.btn_procurar.clicked.connect(self._procurar)
        self.campo_pasta = c.FormField(
            "Pasta principal",
            c.hbox(self.input_pasta, self.btn_procurar, spacing=SPACE["sm"]),
            hint="Os PDFs mesclados são salvos na própria pasta principal.",
            target=self.input_pasta,
        )

        self.btn_mesclar = c.Button("Mesclar tudo", "primary", icon="play")
        self.btn_mesclar.clicked.connect(self._iniciar)
        self.btn_cancelar = c.Button("Cancelar", "danger", icon="x")
        self.btn_cancelar.clicked.connect(self._cancelar)
        self.btn_cancelar.hide()
        self.btn_limpar = c.Button("Limpar", "secondary", icon="eraser")
        self.btn_limpar.setToolTip("Limpa a pasta, os indicadores e a tabela")
        self.btn_limpar.clicked.connect(self.limpar)
        self.progresso = c.ProgressBar()
        self.progresso.hide()
        self.lbl_progresso = c.Label("", "muted")

        origem = c.Card(
            "Origem",
            "Cada subpasta é uma fatura: PDF da fatura com os CT-es, mais 2 (CVA), "
            "3 (Solicitação), 4 (Maps) e 7 (Ocorrência) quando houver.",
        )
        origem.add(
            self.campo_pasta,
            self.progresso,
            c.hbox(self.btn_mesclar, self.btn_cancelar, self.btn_limpar, SPACE["sm"],
                   self.lbl_progresso, None, spacing=SPACE["sm"]),
        )

        # --- Indicadores --------------------------------------------------
        self.stat_total = c.StatCard("Faturas", "—", "folders", "primary")
        self.stat_ok = c.StatCard("Geradas", "—", "check-circle", "success")
        self.stat_aviso = c.StatCard("Com aviso", "—", "alert-triangle", "warning")
        self.stat_falha = c.StatCard("Não geradas", "—", "x-circle", "danger")
        indicadores = c.hbox(self.stat_total, self.stat_ok, self.stat_aviso, self.stat_falha,
                             spacing=SPACE["lg"])

        # --- Resultado ----------------------------------------------------
        self.busca = c.SearchInput("Buscar por pasta ou detalhe")
        self.busca.textChanged.connect(self._filtrar)
        self.filtro = c.Select(["Todos os status"] + [s.value for s in Status])
        self.filtro.setMinimumWidth(180)
        self.filtro.currentIndexChanged.connect(self._filtrar)

        self.tabela = c.DataTable(["Status", "Pasta", "Tipo", "Páginas", "Detalhes"])
        self.tabela.set_column_widths({0: 120, 1: 140, 2: 150, 3: 90})
        self.tabela.setMinimumHeight(320)
        self.tabela.cellDoubleClicked.connect(self._abrir_linha)

        self.btn_saida = c.Button("Abrir pasta", "secondary", "sm", icon="external-link")
        self.btn_saida.clicked.connect(lambda: self._execucao and abrir(self._execucao.pasta_principal))
        self.btn_saida.setEnabled(False)

        resultado = c.Card(
            "Resultado",
            "Clique no status para ver os detalhes. Clique duas vezes na linha para abrir o PDF gerado.",
        )
        resultado.add_header_action(self.btn_saida)
        resultado.add(c.hbox(self.busca, self.filtro, spacing=SPACE["sm"]), self.tabela)

        self.add(origem, indicadores, resultado, stretch_last=True)
        if pasta_inicial:
            self.input_pasta.setText(pasta_inicial)

    # --- Estado ---------------------------------------------------------
    @property
    def rodando(self) -> bool:
        return self._thread is not None

    def _set_rodando(self, rodando: bool) -> None:
        self.btn_mesclar.setEnabled(not rodando)
        self.btn_procurar.setEnabled(not rodando)
        self.input_pasta.setReadOnly(rodando)
        self.btn_cancelar.setVisible(rodando)
        self.btn_cancelar.setEnabled(True)
        self.btn_limpar.setVisible(not rodando)
        if rodando:
            self.progresso.show()

    def _atualizar_indicadores(self) -> None:
        n = self._contagem
        self.stat_ok.set_value(n[Status.OK] + n[Status.AVISO])
        self.stat_aviso.set_value(n[Status.AVISO])
        self.stat_falha.set_value(n[Status.PULADA] + n[Status.ERRO])

    def _zerar_resultados(self) -> None:
        self._execucao = None
        self._contagem = {s: 0 for s in Status}
        self.tabela.clear_rows()
        for stat in (self.stat_ok, self.stat_aviso, self.stat_falha):
            stat.set_value("—")
        self.btn_saida.setEnabled(False)
        self.progresso.hide()
        self.progresso.reset()

    def _contar_faturas(self) -> None:
        """Mostra quantas faturas (subpastas) a pasta tem, antes de mesclar."""
        if self.rodando:
            return
        texto = self.input_pasta.text().strip().strip('"')
        pasta = Path(texto) if texto else None
        if pasta is None or not pasta.is_dir():
            self.stat_total.set_value("—")
            self.lbl_progresso.setText("")
            return
        self.campo_pasta.set_error(None)
        self._zerar_resultados()
        try:
            total = len(mesclagem.listar_subpastas(pasta))
        except OSError:
            total = 0
        self.stat_total.set_value(total)
        if total:
            self.lbl_progresso.setText(f"{total} fatura{'s' if total > 1 else ''} encontrada{'s' if total > 1 else ''}. Pronto para mesclar.")
        else:
            self.lbl_progresso.setText("Nenhuma subpasta de fatura nesta pasta.")

    # --- Ações ----------------------------------------------------------
    def limpar(self) -> None:
        if self.rodando:
            return
        self._timer_contagem.stop()
        self.input_pasta.blockSignals(True)
        self.input_pasta.clear()
        self.input_pasta.blockSignals(False)
        self.campo_pasta.set_error(None)
        self._zerar_resultados()
        self.stat_total.set_value("—")
        self.lbl_progresso.setText("")
        self.busca.clear()
        self.filtro.setCurrentIndex(0)

    def _procurar(self) -> None:
        inicial = self.input_pasta.text() or str(Path.home())
        pasta = QFileDialog.getExistingDirectory(self, "Escolha a pasta principal", inicial)
        if pasta:
            self.input_pasta.setText(str(Path(pasta)))
            self.campo_pasta.set_error(None)

    def _iniciar(self) -> None:
        if self.rodando:
            return
        pasta = self.input_pasta.text().strip().strip('"')
        if not pasta:
            self.campo_pasta.set_error("Selecione a pasta principal.")
            return
        if not Path(pasta).is_dir():
            self.campo_pasta.set_error("Pasta não encontrada. Confira o caminho.")
            return
        self.campo_pasta.set_error(None)
        self._timer_contagem.stop()

        self._zerar_resultados()
        self.progresso.setRange(0, 0)  # indeterminado até saber o total
        self.lbl_progresso.setText("Preparando…")
        self._set_rodando(True)

        self._thread = QThread(self)
        self._worker = MesclarWorker(pasta)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.iniciou_pasta.connect(self._ao_iniciar_pasta)
        self._worker.pasta_concluida.connect(self._ao_concluir_pasta)
        self._worker.concluido.connect(self._ao_concluir)
        self._worker.falhou.connect(self._ao_falhar)
        self._worker.concluido.connect(self._thread.quit)
        self._worker.falhou.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._ao_terminar_thread)
        self._thread.start()

    def _cancelar(self) -> None:
        if not self.rodando:
            return
        if c.Modal.confirm(
            self, "Cancelar processamento?",
            "O processamento para depois da pasta atual. Os PDFs já gerados continuam salvos.",
            confirm_text="Cancelar processamento", cancel_text="Continuar", destructive=True,
        ):
            self.parar()

    def parar(self) -> None:
        if self._worker:
            self._worker.cancelar()
            self.btn_cancelar.setEnabled(False)
            self.lbl_progresso.setText("Cancelando após a pasta atual…")

    def aguardar(self) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait()

    # --- Sinais do worker -----------------------------------------------
    def _ao_iniciar_pasta(self, indice: int, total: int, nome: str) -> None:
        if self.progresso.maximum() != total:
            self.progresso.setRange(0, total)
            self.stat_total.set_value(total)
        self.progresso.setValue(indice)
        if self.btn_cancelar.isEnabled():
            self.lbl_progresso.setText(f"Processando {indice + 1} de {total}: {nome}")

    def _ao_concluir_pasta(self, r: mesclagem.Resultado) -> None:
        self._contagem[r.status] += 1
        self._atualizar_indicadores()
        self.progresso.setValue(self.progresso.value() + 1)
        badge = c.Badge(r.status.value, STATUS_TONE[r.status], clickable=True,
                        tooltip="Clique para ver os detalhes")
        badge.clicked.connect(lambda r=r: self._mostrar_detalhes(r))
        self.tabela.add_row(
            [badge, r.pasta, r.tipo or "—", r.total_paginas or "—", r.descricao()],
            data=r,
        )
        self._filtrar_linha(self.tabela.rowCount() - 1)

    def _ao_concluir(self, execucao: mesclagem.Execucao) -> None:
        self._execucao = execucao
        self.progresso.setValue(self.progresso.maximum())
        self.btn_saida.setEnabled(True)
        falhas = execucao.contar(Status.PULADA, Status.ERRO)
        texto = f"{execucao.geradas} de {execucao.total} faturas geradas"
        if execucao.cancelada:
            texto = f"Cancelado: {texto}"
        elif falhas:
            texto += f" · {falhas} não gerada{'s' if falhas > 1 else ''}, veja os detalhes"
        else:
            texto = f"Concluído: {texto}"
        self.lbl_progresso.setText(texto)

    def _ao_falhar(self, mensagem: str) -> None:
        self.progresso.hide()
        self.lbl_progresso.setText("")
        c.Modal.alert(self, "Não foi possível processar", mensagem, tone="danger")

    def _ao_terminar_thread(self) -> None:
        self._thread = None
        self._worker = None
        self._set_rodando(False)

    # --- Tabela ---------------------------------------------------------
    def _filtrar_linha(self, linha: int) -> None:
        r: mesclagem.Resultado = self.tabela.row_data(linha)
        termo = self.busca.text().strip().lower()
        status = self.filtro.currentText() if self.filtro.currentIndex() > 0 else None
        visivel = (status is None or r.status.value == status) and (
            not termo or termo in f"{r.pasta} {r.tipo} {r.descricao()}".lower()
        )
        self.tabela.setRowHidden(linha, not visivel)

    def _filtrar(self, *_) -> None:
        for linha in range(self.tabela.rowCount()):
            self._filtrar_linha(linha)

    def _mostrar_detalhes(self, r: mesclagem.Resultado) -> None:
        DetalhesModal(r, self).exec()

    def _abrir_linha(self, linha: int, _coluna: int) -> None:
        r: mesclagem.Resultado = self.tabela.row_data(linha)
        if r and r.saida and r.saida.exists():
            abrir(r.saida)


# ---------------------------------------------------------------------------
# Janela principal
# ---------------------------------------------------------------------------
PAGINAS = [
    ("Mesclar PDFs", "layers", "Junte fatura, CVA, CT-es e anexos em um único PDF por pasta."),
]


class MainWindow(QMainWindow):
    def __init__(self, pasta_inicial: str = ""):
        super().__init__()
        self.setWindowTitle("Mesclador de PDFs")
        self.resize(1240, 800)
        self.setMinimumSize(980, 640)
        self._atualizar_icone_janela()
        theme_manager.changed.connect(self._atualizar_icone_janela)

        self.pagina_mesclar = MesclarPage(pasta_inicial)

        self.sidebar = c.Sidebar("Mesclador")
        for titulo, icone, _ in PAGINAS:
            self.sidebar.add_item(titulo, icone)
        self.sidebar.footer.addWidget(c.Label(f"Versão {__version__}", "hint"))
        self.sidebar.selected.connect(self._ir_para)

        self.header = c.Header()
        self.header.add_action(c.ThemeToggle())

        self.stack = QStackedWidget()
        self.stack.addWidget(self.pagina_mesclar)

        raiz = QWidget()
        raiz.setObjectName("AppRoot")
        raiz.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        raiz.setLayout(c.hbox(self.sidebar, c.vbox(self.header, self.stack, spacing=0), spacing=0))
        self.setCentralWidget(raiz)
        self._ir_para(0)

        # Procura versão nova no GitHub logo depois de abrir (só no .exe).
        self.atualizacao = VerificadorAtualizacao(self, __version__, lambda: self.pagina_mesclar.rodando)
        QTimer.singleShot(1500, self.atualizacao.iniciar)

    def _ir_para(self, indice: int) -> None:
        titulo, _, subtitulo = PAGINAS[indice]
        self.stack.setCurrentIndex(indice)
        self.header.set_title(titulo, subtitulo)
        self.sidebar.set_current(indice)

    def _atualizar_icone_janela(self, *_) -> None:
        self.setWindowIcon(icons.icon("layers", theme_manager.color("primary"), 64))

    def closeEvent(self, event) -> None:  # noqa: N802
        pagina = self.pagina_mesclar
        if pagina.rodando:
            if not c.Modal.confirm(
                self, "Sair durante o processamento?",
                "O processamento será interrompido depois da pasta atual.",
                confirm_text="Sair", cancel_text="Continuar", destructive=True,
            ):
                event.ignore()
                return
            pagina.parar()
            pagina.aguardar()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName(ORGANIZACAO)
    app.setApplicationName(APLICACAO)
    app.setApplicationVersion(__version__)
    theme_manager.apply()
    atualizacao.limpar_antigo()  # remove o .exe.old deixado pela última atualização

    pasta = sys.argv[1] if len(sys.argv) > 1 and Path(sys.argv[1]).is_dir() else ""
    janela = MainWindow(pasta)
    janela.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
