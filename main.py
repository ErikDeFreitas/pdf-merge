"""
Mesclador de PDFs — aplicação desktop (PySide6).

Uso:   python main.py                  -> abre a janela
       python main.py "C:\\Pasta"       -> abre a janela com a pasta preenchida
       python -m core "C:\\Pasta"       -> modo terminal, sem janela
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThread, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QStackedWidget, QWidget

from core import mesclagem
from core.mesclagem import Status
from core.worker import MesclarWorker
from ui import components as c
from ui import icons
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


# ---------------------------------------------------------------------------
# Página: Mesclar PDFs
# ---------------------------------------------------------------------------
class MesclarPage(c.Page):
    def __init__(self, settings: QSettings, pasta_inicial: str = ""):
        super().__init__()
        self._settings = settings
        self._thread: QThread | None = None
        self._worker: MesclarWorker | None = None
        self._execucao: mesclagem.Execucao | None = None
        self._contagem = {s: 0 for s in Status}

        # --- Origem -------------------------------------------------------
        self.input_pasta = c.Input("Selecione a pasta que contém uma subpasta por fatura")
        self.input_pasta.setText(pasta_inicial or settings.value("ultima_pasta", ""))
        self.input_pasta.returnPressed.connect(self._iniciar)
        self.btn_procurar = c.Button("Procurar", "secondary", icon="folder-open")
        self.btn_procurar.clicked.connect(self._procurar)
        self.campo_pasta = c.FormField(
            "Pasta principal",
            c.hbox(self.input_pasta, self.btn_procurar, spacing=SPACE["sm"]),
            hint=f"Os PDFs mesclados são salvos em {mesclagem.PASTA_SAIDA}, dentro da pasta principal.",
            target=self.input_pasta,
        )

        self.btn_mesclar = c.Button("Mesclar tudo", "primary", icon="play")
        self.btn_mesclar.clicked.connect(self._iniciar)
        self.btn_cancelar = c.Button("Cancelar", "danger", icon="x")
        self.btn_cancelar.clicked.connect(self._cancelar)
        self.btn_cancelar.hide()
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
            c.hbox(self.btn_mesclar, self.btn_cancelar, SPACE["sm"], self.lbl_progresso, None),
        )

        # --- Indicadores --------------------------------------------------
        self.stat_total = c.StatCard("Pastas", "—", "folders", "primary")
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

        self.btn_saida = c.Button("Abrir pasta de saída", "secondary", "sm", icon="external-link")
        self.btn_saida.clicked.connect(lambda: self._execucao and abrir(self._execucao.pasta_saida))
        self.btn_relatorio = c.Button("Ver relatório", "secondary", "sm", icon="file-text")
        self.btn_relatorio.clicked.connect(lambda: self._execucao and abrir(self._execucao.relatorio))
        self.btn_saida.setEnabled(False)
        self.btn_relatorio.setEnabled(False)

        resultado = c.Card("Resultado", "Clique duas vezes em uma linha para abrir o PDF gerado.")
        resultado.add_header_action(self.btn_relatorio)
        resultado.add_header_action(self.btn_saida)
        resultado.add(c.hbox(self.busca, self.filtro, spacing=SPACE["sm"]), self.tabela)

        self.add(origem, indicadores, resultado, stretch_last=True)

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
        if rodando:
            self.progresso.show()

    def _atualizar_indicadores(self) -> None:
        n = self._contagem
        self.stat_ok.set_value(n[Status.OK] + n[Status.AVISO])
        self.stat_aviso.set_value(n[Status.AVISO])
        self.stat_falha.set_value(n[Status.PULADA] + n[Status.ERRO])

    # --- Ações ----------------------------------------------------------
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
        self._settings.setValue("ultima_pasta", pasta)

        self._execucao = None
        self._contagem = {s: 0 for s in Status}
        self.tabela.clear_rows()
        for stat in (self.stat_total, self.stat_ok, self.stat_aviso, self.stat_falha):
            stat.set_value("—")
        self.btn_saida.setEnabled(False)
        self.btn_relatorio.setEnabled(False)
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
        badge = c.Badge(r.status.value, STATUS_TONE[r.status])
        self.tabela.add_row(
            [badge, r.pasta, r.tipo or "—", r.total_paginas or "—", r.descricao()],
            data=r,
        )
        self._filtrar_linha(self.tabela.rowCount() - 1)

    def _ao_concluir(self, execucao: mesclagem.Execucao) -> None:
        self._execucao = execucao
        self.progresso.setValue(self.progresso.maximum())
        self.btn_saida.setEnabled(True)
        self.btn_relatorio.setEnabled(execucao.relatorio is not None)
        falhas = execucao.contar(Status.PULADA, Status.ERRO)
        texto = f"{execucao.geradas} de {execucao.total} pastas geradas"
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

    def _abrir_linha(self, linha: int, _coluna: int) -> None:
        r: mesclagem.Resultado = self.tabela.row_data(linha)
        if r and r.saida and r.saida.exists():
            abrir(r.saida)


# ---------------------------------------------------------------------------
# Página: Componentes (vitrine do Design System)
# ---------------------------------------------------------------------------
class ComponentesPage(c.Page):
    def __init__(self):
        super().__init__()

        # Botões
        botoes = c.Card("Botões", "Variantes, tamanhos (32 / 40 / 48px) e estados.")
        botoes.add(
            c.hbox(c.Button("Primário"), c.Button("Secundário", "secondary"),
                   c.Button("Excluir", "danger", icon="trash"), c.Button("Fantasma", "ghost"),
                   c.IconButton("plus", "Adicionar"), None, spacing=SPACE["sm"]),
            c.hbox(c.Button("Pequeno", size="sm"), c.Button("Padrão", icon="plus"),
                   c.Button("Grande", size="lg", icon="play"), None, spacing=SPACE["sm"]),
        )
        desabilitados = [c.Button("Primário"), c.Button("Secundário", "secondary"),
                         c.Button("Excluir", "danger", icon="trash")]
        for b in desabilitados:
            b.setEnabled(False)
        botoes.add(c.hbox(*desabilitados, None, spacing=SPACE["sm"]))

        # Formulário
        nome = c.Input("Ex.: Transportadora Exemplo")
        email = c.Input("nome@empresa.com.br")
        campo_email = c.FormField("E-mail", email, "Usado para enviar o relatório.")
        campo_email.set_error("Informe um e-mail válido.")
        desabilitado = c.Input("Campo desabilitado")
        desabilitado.setEnabled(False)
        formulario = c.Card("Formulário", "Inputs 42px, foco com borda azul e estado de erro.")
        formulario.add(
            c.hbox(c.FormField("Nome", nome), c.FormField("Tipo", c.Select(
                ["Dedicado", "Dedicado ND", "EXT / EME", "EXT ND / EME ND"])), spacing=SPACE["lg"]),
            c.hbox(campo_email, c.FormField("Desabilitado", desabilitado), spacing=SPACE["lg"]),
            c.FormField("Pesquisa", c.SearchInput("Buscar faturas")),
            c.FormField("Observações", c.TextArea("Escreva uma observação…")),
            c.hbox(c.Checkbox("Abrir a pasta ao terminar", True), c.Checkbox("Gerar relatório"),
                   None, spacing=SPACE["xl"]),
            c.hbox(None, c.Button("Cancelar", "secondary"), c.Button("Salvar"), spacing=SPACE["sm"]),
        )

        # Badges + indicadores
        badges = c.Card("Badges")
        badges.add(c.hbox(c.Badge("Neutro"), c.Badge("Info", "primary"), c.Badge("OK", "success"),
                          c.Badge("Aviso", "warning"), c.Badge("Erro", "danger"), None,
                          spacing=SPACE["sm"]))
        stats = c.hbox(c.StatCard("Faturas", "128", "folders"),
                       c.StatCard("Concluídas", "120", "check-circle", "success"),
                       c.StatCard("Falhas", "8", "x-circle", "danger"), spacing=SPACE["lg"])

        # Tabela
        tabela = c.DataTable(["Status", "Fatura", "Tipo", "Páginas", "Detalhes"])
        tabela.set_column_widths({0: 120, 1: 120, 2: 150, 3: 90})
        for status, fatura, tipo, pags, det in [
            ("OK", "85067", "Dedicado", 9, "85067.pdf: 2 fatura, 1 CVA, 6 CT-e"),
            ("Aviso", "85071", "EXT / EME", 14, "PDFs ignorados: copia.pdf"),
            ("Pulada", "85090", "—", "—", "CVA (2.pdf) não encontrado."),
        ]:
            tom = {"OK": "success", "Aviso": "warning"}.get(status, "danger")
            tabela.add_row([c.Badge(status, tom), fatura, tipo, pags, det])
        tabela.setMinimumHeight(4 * SIZE["table_row"] + 2)
        card_tabela = c.Card("Tabela", "Linhas de 44px, seleção por linha e badges de status.")
        card_tabela.add(tabela)

        # Modais
        modais = c.Card("Modais", "Largura padrão de 480px.")
        b_info = c.Button("Abrir modal", "secondary", icon="info")
        b_info.clicked.connect(lambda: c.Modal.alert(
            self, "Processamento concluído", "120 de 128 pastas foram geradas com sucesso.", "success"))
        b_conf = c.Button("Excluir relatório", "danger", icon="trash")
        b_conf.clicked.connect(lambda: c.Modal.confirm(
            self, "Excluir relatório?", "Esta ação não pode ser desfeita.",
            confirm_text="Excluir", destructive=True))
        modais.add(c.hbox(b_info, b_conf, None, spacing=SPACE["sm"]))

        self.add(botoes, formulario, badges, stats, card_tabela, modais)


# ---------------------------------------------------------------------------
# Janela principal
# ---------------------------------------------------------------------------
PAGINAS = [
    ("Mesclar PDFs", "layers", "Junte fatura, CVA, CT-es e anexos em um único PDF por pasta."),
    ("Componentes", "grid", "Vitrine do Design System: botões, campos, tabelas e modais."),
]


class MainWindow(QMainWindow):
    def __init__(self, pasta_inicial: str = ""):
        super().__init__()
        self.setWindowTitle("Mesclador de PDFs")
        self.resize(1240, 800)
        self.setMinimumSize(980, 640)
        self._atualizar_icone_janela()
        theme_manager.changed.connect(self._atualizar_icone_janela)

        settings = QSettings(ORGANIZACAO, APLICACAO)
        self.pagina_mesclar = MesclarPage(settings, pasta_inicial)

        self.sidebar = c.Sidebar("Mesclador")
        for titulo, icone, _ in PAGINAS:
            self.sidebar.add_item(titulo, icone)
        self.sidebar.footer.addWidget(c.Label(f"Versão {__version__}", "hint"))
        self.sidebar.selected.connect(self._ir_para)

        self.header = c.Header()
        self.header.add_action(c.ThemeToggle())

        self.stack = QStackedWidget()
        self.stack.addWidget(self.pagina_mesclar)
        self.stack.addWidget(ComponentesPage())

        raiz = QWidget()
        raiz.setObjectName("AppRoot")
        raiz.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        raiz.setLayout(c.hbox(self.sidebar, c.vbox(self.header, self.stack, spacing=0), spacing=0))
        self.setCentralWidget(raiz)
        self._ir_para(0)

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

    pasta = sys.argv[1] if len(sys.argv) > 1 and Path(sys.argv[1]).is_dir() else ""
    janela = MainWindow(pasta)
    janela.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
