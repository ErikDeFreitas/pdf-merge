"""Aviso de nova versão: modal do Design System com barra de progresso do download."""
from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QWidget

from core import atualizacao
from core.worker import BaixarAtualizacaoWorker
from ui import components as c
from ui.themes import SPACE


def _mb(n: int) -> str:
    return f"{n / 1_048_576:.1f}".replace(".", ",") + " MB"


class AtualizacaoModal(c.Modal):
    def __init__(self, release: atualizacao.Release, versao_atual: str, exe: Path | None,
                 parent: QWidget | None = None):
        super().__init__("Nova versão disponível", "", "download", "primary", parent)
        self._release, self._exe = release, exe
        self._thread: QThread | None = None
        self._worker: BaixarAtualizacaoWorker | None = None
        self._fechar_ao_parar = False

        versoes = c.hbox(c.Badge(f"Atual {versao_atual}", "neutral"), c.Label("→", "muted"),
                         c.Badge(f"Nova {release.versao}", "primary"), None, spacing=SPACE["sm"])
        texto = c.Label(
            "Há uma versão mais nova do Mesclador de PDFs. Ao atualizar, o programa baixa a nova "
            "versão, confere a assinatura (SHA-256) e reabre sozinho. Seus arquivos não são alterados.",
            "muted", wrap=True)

        self.barra = c.ProgressBar()
        self.barra.setRange(0, 1000)
        self.lbl_progresso = c.Label("", "hint")
        self.lbl_percentual = c.Label("", "label")
        self.lbl_percentual.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.bloco_progresso = QWidget()
        self.bloco_progresso.setLayout(c.vbox(
            self.barra, c.hbox(self.lbl_progresso, None, self.lbl_percentual, spacing=SPACE["sm"]),
            spacing=SPACE["sm"]))
        self.bloco_progresso.hide()

        self.lbl_erro = c.Label("", "hint", wrap=True)
        c.set_prop(self.lbl_erro, "error", True)
        self.lbl_erro.hide()

        for w in (versoes, texto, self.bloco_progresso, self.lbl_erro):
            self.body.addWidget(w) if isinstance(w, QWidget) else self.body.addLayout(w)

        self.btn_depois = c.Button("Agora não", "secondary")
        self.btn_depois.clicked.connect(self.reject)
        self.btn_atualizar = c.Button("Atualizar", "primary", icon="download")
        self.btn_atualizar.setDefault(True)
        self.btn_atualizar.clicked.connect(self._atualizar)
        self.footer.addWidget(self.btn_depois)
        self.footer.addWidget(self.btn_atualizar)

    # ----------------------------------------------------------------- download
    @property
    def baixando(self) -> bool:
        return self._thread is not None

    def _atualizar(self) -> None:
        if self._exe is None:  # rodando pelo Python: só abre a página da Release
            QDesktopServices.openUrl(QUrl(self._release.pagina))
            self.accept()
            return
        self.lbl_erro.hide()
        self.bloco_progresso.show()
        self.barra.setValue(0)
        self.lbl_progresso.setText("Conectando ao GitHub…")
        self.lbl_percentual.setText("")
        self.btn_atualizar.setEnabled(False)
        self.btn_atualizar.setText("Baixando…")
        self.btn_depois.setText("Cancelar")

        self._thread = QThread(self)
        self._worker = BaixarAtualizacaoWorker(self._release, self._exe)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progresso.connect(self._ao_progresso)
        self._worker.concluido.connect(self._ao_concluir)
        self._worker.falhou.connect(self._ao_falhar)
        self._worker.concluido.connect(self._thread.quit)
        self._worker.falhou.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._ao_parar)
        self._thread.start()

    def _ao_progresso(self, lido: int, total: int) -> None:
        if total > 0:
            self.barra.setRange(0, 1000)
            self.barra.setValue(int(lido * 1000 / total))
            self.lbl_progresso.setText(f"Baixando {_mb(lido)} de {_mb(total)}")
            self.lbl_percentual.setText(f"{lido * 100 // total}%")
        else:
            self.barra.setRange(0, 0)  # tamanho desconhecido: barra animada
            self.lbl_progresso.setText(f"Baixando {_mb(lido)}")

    def _ao_concluir(self, novo: str) -> None:
        self.barra.setRange(0, 1000)
        self.barra.setValue(1000)
        self.lbl_percentual.setText("100%")
        self.lbl_progresso.setText("Assinatura conferida. Instalando…")
        self.btn_depois.setEnabled(False)
        try:
            atualizacao.instalar(Path(novo), self._exe)
        except atualizacao.FalhaAtualizacao as e:
            self._ao_falhar(str(e))
            return
        self.lbl_progresso.setText("Atualizado. Reabrindo…")
        QTimer.singleShot(600, self._reiniciar)

    def _reiniciar(self) -> None:
        # Nova instância independente do .exe (onefile do PyInstaller precisa do RESET).
        env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([str(self._exe)], env=env, creationflags=flags, close_fds=True,
                         cwd=str(self._exe.parent))
        QApplication.quit()

    def _ao_falhar(self, mensagem: str) -> None:
        if self._fechar_ao_parar:
            return
        self.bloco_progresso.hide()
        self.lbl_erro.setText(mensagem)
        self.lbl_erro.show()
        self.btn_atualizar.setEnabled(True)
        self.btn_atualizar.setText("Tentar de novo")
        self.btn_depois.setEnabled(True)
        self.btn_depois.setText("Agora não")

    def _ao_parar(self) -> None:
        self._thread.deleteLater()
        self._thread = self._worker = None
        if self._fechar_ao_parar:
            super().reject()

    def reject(self) -> None:  # "Agora não", "Cancelar", Esc ou X
        if self.baixando:
            self._fechar_ao_parar = True
            self.btn_depois.setEnabled(False)
            self.lbl_progresso.setText("Cancelando…")
            self._worker.cancelar()
            return
        super().reject()


class _Aviso(QObject):
    encontrada = Signal(object)


class VerificadorAtualizacao(QObject):
    """Consulta o GitHub em segundo plano e mostra o modal se houver versão nova.

    Só roda no .exe (no Python de desenvolvimento não há o que substituir). Sem internet,
    nada aparece. Se uma mesclagem estiver rodando, espera ela terminar para avisar.
    """

    def __init__(self, janela: QWidget, versao_atual: str, ocupado=lambda: False):
        super().__init__(janela)
        self._janela, self._versao, self._ocupado = janela, versao_atual, ocupado
        self._aviso = _Aviso(self)
        self._aviso.encontrada.connect(self._mostrar)

    def iniciar(self, forcar: bool = False) -> None:
        if atualizacao.executavel_atual() is None and not forcar:
            return

        def consultar() -> None:
            release = atualizacao.buscar_ultima()
            if atualizacao.tem_atualizacao(self._versao, release):
                self._aviso.encontrada.emit(release)

        threading.Thread(target=consultar, daemon=True).start()

    def _mostrar(self, release: atualizacao.Release) -> None:
        if self._ocupado():
            QTimer.singleShot(3000, lambda: self._mostrar(release))
            return
        AtualizacaoModal(release, self._versao, atualizacao.executavel_atual(), self._janela).exec()
