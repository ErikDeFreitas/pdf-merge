"""Pasta de dados do Mesclador. Só stdlib; nada é criado ao importar."""

import os
from pathlib import Path

NOME_PASTA = "MesclarPDFs"


def pasta_dados() -> Path:
    var = os.environ.get("MESCLADOR_DADOS")
    if var:
        return Path(var)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / NOME_PASTA


PASTA: Path = pasta_dados()
