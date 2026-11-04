"""Executa a mesclagem fora da thread da interface, para a janela nunca travar."""
from PySide6.QtCore import QObject, Signal, Slot

from core import atualizacao, mesclagem


class MesclarWorker(QObject):
    iniciou_pasta = Signal(int, int, str)  # índice, total, nome
    pasta_concluida = Signal(object)        # mesclagem.Resultado
    concluido = Signal(object)              # mesclagem.Execucao
    falhou = Signal(str)

    def __init__(self, pasta: str):
        super().__init__()
        self._pasta = pasta
        self._cancelar = False

    def cancelar(self) -> None:
        self._cancelar = True

    @Slot()
    def run(self) -> None:
        try:
            execucao = mesclagem.processar(
                self._pasta,
                ao_iniciar=self.iniciou_pasta.emit,
                ao_concluir=self.pasta_concluida.emit,
                cancelado=lambda: self._cancelar,
            )
        except mesclagem.PastaInvalida as e:
            self.falhou.emit(str(e))
        except Exception as e:
            self.falhou.emit(f"Erro inesperado: {type(e).__name__}: {e}")
        else:
            self.concluido.emit(execucao)


class BaixarAtualizacaoWorker(QObject):
    progresso = Signal(int, int)  # bytes lidos, total
    concluido = Signal(str)       # caminho do .exe novo (já conferido)
    falhou = Signal(str)

    def __init__(self, release, exe):
        super().__init__()
        self._release, self._exe = release, exe
        self._cancelar = False

    def cancelar(self) -> None:
        self._cancelar = True

    @Slot()
    def run(self) -> None:
        try:
            novo = atualizacao.baixar_e_conferir(self._release, self._exe, self.progresso.emit,
                                                 lambda: self._cancelar)
        except atualizacao.FalhaAtualizacao as e:
            self.falhou.emit(str(e))
        except Exception as e:
            self.falhou.emit(f"Erro inesperado: {type(e).__name__}: {e}")
        else:
            self.concluido.emit(str(novo))
