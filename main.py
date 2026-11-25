"""Ponto de entrada do Mesclador de PDFs avulso (.exe ou `python main.py [pasta]`)."""

import sys
from pathlib import Path

from mesclador import instancia
from mesclador.modulo import MODULO
from tcm_ui.avulso import rodar_avulso

if __name__ == "__main__":
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_dir():
        instancia.PASTA_INICIAL = sys.argv[1]
    sys.exit(rodar_avulso(MODULO))
