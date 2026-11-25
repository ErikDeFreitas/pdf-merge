import re
from pathlib import Path

from mesclador.modulo import MODULO

RAIZ = Path(__file__).resolve().parent.parent


def test_build_usa_nome_do_exe():
    script = (RAIZ / "build.ps1").read_text(encoding="utf-8")
    assert MODULO.nome_exe == "MesclarPDFs.exe"
    assert '$nome = "MesclarPDFs"' in script
    # o .sha256 é gravado como "<hash>  MesclarPDFs.exe" + quebra de linha
    assert '"$hash  $nome.exe`n"' in script
    assert "--collect-data tcm_ui --collect-data mesclador" in script
    assert (RAIZ / "assets" / "MesclarPDFs.ico").is_file()


def test_requirements_fixa_tcm_ui():
    texto = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"tcm-ui @ git\+https://github.com/ErikDeFreitas/Tcm-ui@v\d+\.\d+\.\d+", texto)
