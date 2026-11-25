import os
import subprocess
import sys
from importlib.metadata import entry_points
from pathlib import Path

import mesclador
from mesclador import dados
from mesclador.modulo import MODULO


def test_valores_do_modulo():
    assert (MODULO.id, MODULO.nome, MODULO.icone) == ("mesclador", "Mesclador de PDFs", "camadas")
    assert (MODULO.grupo_ad, MODULO.repositorio, MODULO.nome_exe) == (
        "SF-Mesclador", "ErikDeFreitas/pdf-merge", "MesclarPDFs.exe")
    assert MODULO.versao == mesclador.__version__ == "3.0.0"
    assert MODULO.pasta_dados == dados.PASTA
    assert MODULO.aplicacao_settings == "MesclarPDFs"
    assert [(p.chave, p.titulo, p.subtitulo, p.icone) for p in MODULO.paginas] == [
        ("mesclar", "Mesclar PDFs", "Junte fatura, CVA, CT-es e anexos em um único PDF por pasta.", "camadas")]


def test_entry_point_carrega_o_modulo():
    eps = {ep.name: ep for ep in entry_points(group="sistema_financeiro.modulos")}
    assert eps["mesclador"].load() is MODULO


def test_modulo_e_leve(tmp_path):
    codigo = ("import sys, mesclador.modulo; "
              "print(*[m in sys.modules for m in ('pypdf', 'PIL', 'mesclador.tela')])")
    env = {**os.environ, "MESCLADOR_DADOS": str(tmp_path / "nao_criar")}
    saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, env=env, check=True)
    assert saida.stdout.split() == ["False"] * 3
    assert not Path(tmp_path / "nao_criar").exists()
