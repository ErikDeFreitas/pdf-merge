"""Instância do Mesclador aberta na casca ou no avulso."""

from PySide6.QtWidgets import QWidget
from tcm_ui.modulo import Contexto

from mesclador.tela import TelaMesclar

PASTA_INICIAL: str = ""  # o main.py avulso preenche com a pasta passada na linha de comando


class Mesclador:
    def __init__(self, contexto: Contexto):
        self.contexto = contexto
        self.tela: TelaMesclar | None = None

    def widget(self, chave_pagina: str) -> QWidget:
        if chave_pagina != "mesclar":
            raise KeyError(chave_pagina)
        if self.tela is None:
            self.tela = TelaMesclar(self.contexto, PASTA_INICIAL)
        return self.tela

    def acoes_cabecalho(self, chave_pagina: str) -> list[QWidget]:
        return []

    def pode_fechar(self) -> bool:
        return self.tela is None or not self.tela.rodando  # nunca fecha no meio de uma mesclagem
