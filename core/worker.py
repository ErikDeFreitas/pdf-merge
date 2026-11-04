"""Executa a mesclagem fora da thread da interface, para a janela nunca travar."""
from PySide6.QtCore import QObject, Signal, Slot

from core import mesclagem


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
