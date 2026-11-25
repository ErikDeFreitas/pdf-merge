"""Tela do Mesclador de PDFs: escolhe a pasta, mescla cada fatura e mostra o resultado."""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QLabel, QWidget
from tcm_ui import icons
from tcm_ui.components import (
    BarraProgresso, Botao, Campo, CampoPesquisa, CampoTexto, Cartao, CartaoIndicador, Etiqueta,
    GradeResponsiva, Modal, Pagina, Selecao, Tabela, Texto, repolir,
)
from tcm_ui.modulo import Contexto
from tcm_ui.themes import ESPACO, TAMANHOS, tema

from mesclador import mesclagem
from mesclador.mesclagem import Status
from mesclador.worker import MesclarWorker

TOM_STATUS = {
    Status.OK: "sucesso",
    Status.AVISO: "aviso",
    Status.PULADA: "perigo",
    Status.ERRO: "perigo",
}

COL_STATUS = 0
ROLE_RESULTADO = Qt.UserRole + 1  # Qt.UserRole é do filtro de texto da Tabela


def abrir(caminho: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(caminho)))


def _linha(*itens, espaco: int = ESPACO["sm"]) -> QHBoxLayout:
    """Layout horizontal; None vira espaço elástico, int vira espaço fixo."""
    caixa = QHBoxLayout()
    caixa.setSpacing(espaco)
    for item in itens:
        if item is None:
            caixa.addStretch(1)
        elif isinstance(item, int):
            caixa.addSpacing(item)
        else:
            caixa.addWidget(item)
    return caixa


class DialogoDetalhes(Modal):
    """Detalhes de uma fatura: o que aconteceu e quais arquivos entraram (ou não) no PDF."""

    def __init__(self, r: mesclagem.Resultado, versao: str, parent=None):
        super().__init__(f"Fatura {r.pasta} · {r.status.value}", "", parent, TOM_STATUS[r.status])
        self._r, self._versao = r, versao

        if r.caminho:  # caminho longo: abrevia no meio (o completo fica no tooltip e no "Copiar")
            caminho = Texto("", "suave")
            largura = TAMANHOS["modal"] - 2 * ESPACO["xl"]
            caminho.setText(caminho.fontMetrics().elidedText(str(r.caminho), Qt.TextElideMode.ElideMiddle, largura))
            caminho.setToolTip(str(r.caminho))
            self.corpo.addWidget(caminho)

        problemas = list(r.mensagens)
        if r.nds_desconsideradas:
            problemas.append(f"ND sem Fiscal desconsiderada: {', '.join(r.nds_desconsideradas)}.")
        self.corpo.addWidget(Texto("O que aconteceu", "rotulo"))
        if r.saida:
            texto = Texto(f"PDF gerado: {r.saida.name} · {r.total_paginas} páginas ({r.composicao()})")
        else:
            texto = Texto("PDF não gerado.")
        texto.setWordWrap(True)
        self.corpo.addWidget(texto)
        for msg in problemas:
            item = Texto(f"•  {msg[:1].upper()}{msg[1:]}")
            item.setWordWrap(True)
            self.corpo.addWidget(item)
        if not problemas:
            self.corpo.addWidget(Texto("Nenhum problema encontrado.", "suave"))

        self.corpo.addSpacing(ESPACO["sm"])
        self.corpo.addWidget(Texto("Arquivos da pasta", "rotulo"))
        for nome in r.arquivos:
            usado = nome in r.usados
            icone = QLabel()
            icone.setPixmap(icons.pixmap("arquivo", tema.tokens()["texto_suave"], TAMANHOS["icone"]))
            self.corpo.addLayout(_linha(
                icone, Texto(nome), None,
                Etiqueta("Usado" if usado else "Não usado", "sucesso" if usado else "aviso"),
            ))
        if not r.arquivos:
            self.corpo.addWidget(Texto("Nenhum arquivo na pasta.", "suave"))

        self.btn_copiar = self.adicionar_botao(Botao("Copiar detalhes", "secundario", icone="copiar"))
        self.btn_copiar.setToolTip("Copia o texto completo para colar numa mensagem de suporte")
        self.btn_copiar.clicked.connect(self._copiar)
        if r.caminho:
            btn_pasta = self.adicionar_botao(Botao("Abrir pasta", "secundario", icone="pasta"))
            btn_pasta.clicked.connect(lambda: abrir(r.caminho))
        self.adicionar_botao(Botao("Fechar")).clicked.connect(self.accept)

    def _copiar(self) -> None:
        cabecalho = f"Mesclador de PDFs {self._versao} · {datetime.now():%d/%m/%Y %H:%M}"
        QApplication.clipboard().setText(f"{cabecalho}\n{self._r.relatorio()}")
        self.btn_copiar.setText(" Copiado!")
        self.btn_copiar.definir_icone("check")
        QTimer.singleShot(2000, self._restaurar_copiar)

    def _restaurar_copiar(self) -> None:
        self.btn_copiar.setText(" Copiar detalhes")
        self.btn_copiar.definir_icone("copiar")


class TelaMesclar(Pagina):
    """Página única do Mesclador (o antigo MesclarPage, sem janela, barra lateral e cabeçalho)."""

    def __init__(self, contexto: Contexto, pasta_inicial: str = ""):
        super().__init__()
        self.contexto = contexto
        self._thread: QThread | None = None
        self._worker: MesclarWorker | None = None
        self._execucao: mesclagem.Execucao | None = None
        self._contagem = {s: 0 for s in Status}

        # --- Origem -------------------------------------------------------
        self.input_pasta = CampoTexto("Selecione a pasta que contém uma subpasta por fatura")
        self.input_pasta.returnPressed.connect(self._iniciar)
        # Conta as faturas assim que a pasta é escolhida ou digitada.
        self._timer_contagem = QTimer(self, singleShot=True, interval=300)
        self._timer_contagem.timeout.connect(self._contar_faturas)
        self.input_pasta.textChanged.connect(self._timer_contagem.start)
        self.btn_procurar = Botao("Procurar", "secundario", icone="pasta")
        self.btn_procurar.clicked.connect(self._procurar)
        linha_pasta = QWidget()
        caixa = _linha(self.input_pasta, self.btn_procurar)
        caixa.setContentsMargins(0, 0, 0, 0)
        linha_pasta.setLayout(caixa)
        self.campo_pasta = Campo("Pasta principal", linha_pasta,
                                 "Os PDFs mesclados são salvos na própria pasta principal.")

        self.btn_mesclar = Botao("Mesclar tudo", "primario", icone="executar")
        self.btn_mesclar.clicked.connect(self._iniciar)
        self.btn_cancelar = Botao("Cancelar", "perigo", icone="fechar")
        self.btn_cancelar.clicked.connect(self._cancelar)
        self.btn_cancelar.hide()
        self.btn_limpar = Botao("Limpar", "secundario", icone="borracha")
        self.btn_limpar.setToolTip("Limpa a pasta, os indicadores e a tabela")
        self.btn_limpar.clicked.connect(self.limpar)
        self.progresso = BarraProgresso()
        self.progresso.hide()
        self.lbl_progresso = Texto("", "suave")

        origem = Cartao(
            "Origem",
            "Cada subpasta é uma fatura: PDF da fatura com os CT-es, mais 2 (CVA), "
            "3 (Solicitação), 4 (Maps) e 7 (Ocorrência) quando houver.",
        )
        origem.corpo.addWidget(self.campo_pasta)
        origem.corpo.addWidget(self.progresso)
        origem.corpo.addLayout(_linha(self.btn_mesclar, self.btn_cancelar, self.btn_limpar, ESPACO["sm"],
                                      self.lbl_progresso, None))

        # --- Indicadores --------------------------------------------------
        self.ind_total = CartaoIndicador("Faturas", "—", "pastas", "primaria")
        self.ind_ok = CartaoIndicador("Geradas", "—", "check_circulo", "sucesso")
        self.ind_aviso = CartaoIndicador("Com aviso", "—", "alerta", "aviso")
        self.ind_falha = CartaoIndicador("Não geradas", "—", "x_circulo", "perigo")
        indicadores = GradeResponsiva(200)
        for ind in (self.ind_total, self.ind_ok, self.ind_aviso, self.ind_falha):
            indicadores.adicionar(ind)

        # --- Resultado ----------------------------------------------------
        self.busca = CampoPesquisa("Buscar por pasta ou detalhe")
        self.busca.textChanged.connect(self._filtrar)
        self.filtro = Selecao(["Todos os status"] + [s.value for s in Status])
        self.filtro.setMinimumWidth(180)
        self.filtro.currentIndexChanged.connect(self._filtrar)

        self.tabela = Tabela(["Status", "Pasta", "Tipo", "Páginas", "Detalhes"], coluna_flexivel=4)
        self.tabela.setMinimumHeight(320)
        self.tabela.cellDoubleClicked.connect(self._abrir_linha)

        self.btn_saida = Botao("Abrir pasta", "secundario", "sm", icone="link_externo")
        self.btn_saida.clicked.connect(lambda: self._execucao and abrir(self._execucao.pasta_principal))
        self.btn_saida.setEnabled(False)

        resultado = Cartao(
            "Resultado",
            "Clique no status para ver os detalhes. Clique duas vezes na linha para abrir o PDF gerado.",
        )
        resultado.adicionar_acao(self.btn_saida)
        resultado.corpo.addLayout(_linha(self.busca, self.filtro))
        resultado.corpo.addWidget(self.tabela)

        self.conteudo.addWidget(origem)
        self.conteudo.addWidget(indicadores)
        self.conteudo.addWidget(resultado, 1)
        if pasta_inicial:
            self.input_pasta.setText(pasta_inicial)

        # Ao fechar o programa a thread tem de terminar antes de o processo acabar
        # (a confirmação já vem do pode_fechar na JanelaPrincipal). A conexão com um método
        # de QObject some sozinha quando a tela é destruída.
        QApplication.instance().aboutToQuit.connect(self._encerrar)

    # --- Estado ---------------------------------------------------------
    @property
    def rodando(self) -> bool:
        return self._thread is not None

    def _erro_pasta(self, mensagem: str | None) -> None:
        self.campo_pasta.definir_erro(mensagem)
        self.input_pasta.setProperty("erro", bool(mensagem))  # borda vermelha no próprio campo de texto
        repolir(self.input_pasta)

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
        self.ind_ok.definir_valor(str(n[Status.OK] + n[Status.AVISO]))
        self.ind_aviso.definir_valor(str(n[Status.AVISO]))
        self.ind_falha.definir_valor(str(n[Status.PULADA] + n[Status.ERRO]))

    def _zerar_resultados(self) -> None:
        self._execucao = None
        self._contagem = {s: 0 for s in Status}
        self.tabela.setRowCount(0)
        for ind in (self.ind_ok, self.ind_aviso, self.ind_falha):
            ind.definir_valor("—")
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
            self.ind_total.definir_valor("—")
            self.lbl_progresso.setText("")
            return
        self._erro_pasta(None)
        self._zerar_resultados()
        try:
            total = len(mesclagem.listar_subpastas(pasta))
        except OSError:
            total = 0
        self.ind_total.definir_valor(str(total))
        if total:
            plural = "s" if total > 1 else ""
            self.lbl_progresso.setText(f"{total} fatura{plural} encontrada{plural}. Pronto para mesclar.")
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
        self._erro_pasta(None)
        self._zerar_resultados()
        self.ind_total.definir_valor("—")
        self.lbl_progresso.setText("")
        self.busca.clear()
        self.filtro.setCurrentIndex(0)

    def _procurar(self) -> None:
        inicial = self.input_pasta.text() or str(Path.home())
        pasta = QFileDialog.getExistingDirectory(self.contexto.janela, "Escolha a pasta principal", inicial)
        if pasta:
            self.input_pasta.setText(str(Path(pasta)))
            self._erro_pasta(None)

    def _iniciar(self) -> None:
        if self.rodando:
            return
        pasta = self.input_pasta.text().strip().strip('"')
        if not pasta:
            self._erro_pasta("Selecione a pasta principal.")
            return
        if not Path(pasta).is_dir():
            self._erro_pasta("Pasta não encontrada. Confira o caminho.")
            return
        self._erro_pasta(None)
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
        self._thread.finished.connect(self._ao_terminar_thread)
        self._thread.start()

    def _cancelar(self) -> None:
        if not self.rodando:
            return
        if Modal.confirmar(
            self.contexto.janela, "Cancelar processamento?",
            "O processamento para depois da pasta atual. Os PDFs já gerados continuam salvos.",
            texto_ok="Cancelar processamento", destrutivo=True,
            texto_cancelar="Continuar",
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

    def _encerrar(self) -> None:
        self.parar()
        self.aguardar()

    # --- Sinais do worker -----------------------------------------------
    def _ao_iniciar_pasta(self, indice: int, total: int, nome: str) -> None:
        if self.progresso.maximum() != total:
            self.progresso.setRange(0, total)
            self.ind_total.definir_valor(str(total))
        self.progresso.setValue(indice)
        if self.btn_cancelar.isEnabled():
            self.lbl_progresso.setText(f"Processando {indice + 1} de {total}: {nome}")

    def _ao_concluir_pasta(self, r: mesclagem.Resultado) -> None:
        self._contagem[r.status] += 1
        self._atualizar_indicadores()
        self.progresso.setValue(self.progresso.value() + 1)
        etiqueta = Etiqueta(r.status.value, TOM_STATUS[r.status], clicavel=True,
                            dica="Clique para ver os detalhes")
        etiqueta.clicada.connect(lambda r=r: self._mostrar_detalhes(r))
        linha = self.tabela.adicionar_linha(
            [etiqueta, r.pasta, r.tipo or "—", r.total_paginas or "—", r.descricao()])
        self.tabela.item(linha, COL_STATUS).setData(ROLE_RESULTADO, r)
        self._filtrar_linha(linha)

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
        Modal.informar(self.contexto.janela, "Não foi possível processar", mensagem, tom="perigo")

    def _ao_terminar_thread(self) -> None:
        if self._thread is not None:
            self._thread.wait()  # `finished` sai de dentro da thread: espera ela acabar de vez antes de soltar
            self._thread.deleteLater()
        self._thread = None
        self._worker = None
        self._set_rodando(False)

    # --- Tabela ---------------------------------------------------------
    def _resultado(self, linha: int) -> mesclagem.Resultado | None:
        item = self.tabela.item(linha, COL_STATUS)
        return item.data(ROLE_RESULTADO) if item else None

    def _filtrar_linha(self, linha: int) -> None:
        r = self._resultado(linha)
        if r is None:
            return
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
        from mesclador import __version__
        DialogoDetalhes(r, __version__, self.contexto.janela).exec()

    def _abrir_linha(self, linha: int, _coluna: int) -> None:
        r = self._resultado(linha)
        if r and r.saida and r.saida.exists():
            abrir(r.saida)
