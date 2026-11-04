"""
Atualização automática pelo GitHub Releases (sem interface).

Fluxo: buscar_ultima() -> tem_atualizacao() -> baixar_e_conferir() -> instalar().
O .exe novo só substitui o atual depois de o SHA-256 bater com o publicado na Release.
O Windows não deixa sobrescrever um .exe em uso, mas deixa renomear: o atual vira
"MesclarPDFs.exe.old" e é apagado na próxima abertura (limpar_antigo()).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPOSITORIO = "ErikDeFreitas/pdf-merge"
API_ULTIMA = f"https://api.github.com/repos/{REPOSITORIO}/releases/latest"
NOME_EXE = "MesclarPDFs.exe"
NOME_SHA = NOME_EXE + ".sha256"
BLOCO = 64 * 1024


class FalhaAtualizacao(Exception):
    """Mensagem já pronta para mostrar ao usuário."""


@dataclass
class Release:
    versao: str
    url_exe: str
    url_sha: str
    tamanho: int
    pagina: str


def _versao_tupla(versao: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", versao)[:3]) or (0,)


def tem_atualizacao(atual: str, release: Release | None) -> bool:
    return release is not None and _versao_tupla(release.versao) > _versao_tupla(atual)


def _abrir(url: str, timeout: float):
    from version import __version__
    req = urllib.request.Request(url, headers={"User-Agent": f"MesclarPDFs/{__version__}",
                                               "Accept": "application/octet-stream, application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def buscar_ultima(timeout: float = 8) -> Release | None:
    """Última Release publicada com .exe e .sha256. None se não houver (ou sem internet)."""
    try:
        with _abrir(API_ULTIMA, timeout) as resp:
            dados = json.load(resp)
    except Exception:
        return None
    arquivos = {a.get("name"): a for a in dados.get("assets", [])}
    exe, sha = arquivos.get(NOME_EXE), arquivos.get(NOME_SHA)
    if not exe or not sha:
        return None
    return Release(
        versao=str(dados.get("tag_name", "")).lstrip("vV"),
        url_exe=exe["browser_download_url"],
        url_sha=sha["browser_download_url"],
        tamanho=int(exe.get("size") or 0),
        pagina=dados.get("html_url", ""),
    )


def executavel_atual() -> Path | None:
    """Caminho do .exe em execução; None quando roda pelo Python (desenvolvimento)."""
    return Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None


def _antigo(exe: Path) -> Path:
    return exe.with_name(exe.name + ".old")


def _novo(exe: Path) -> Path:
    return exe.with_name(exe.name + ".new")


def limpar_antigo(exe: Path | None = None) -> None:
    exe = exe or executavel_atual()
    if exe:
        for sobra in (_antigo(exe), _novo(exe)):
            try:
                sobra.unlink(missing_ok=True)
            except OSError:
                pass


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(BLOCO), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar_e_conferir(release: Release, exe: Path,
                      progresso: Callable[[int, int], None] = lambda lido, total: None,
                      cancelado: Callable[[], bool] = lambda: False) -> Path:
    """Baixa o .exe novo ao lado do atual (MesclarPDFs.exe.new) e confere o SHA-256."""
    destino = _novo(exe)
    try:
        with _abrir(release.url_sha, 15) as resp:
            esperado = resp.read().decode("ascii", "ignore").split()[0].lower()
    except Exception as e:
        raise FalhaAtualizacao(f"Não foi possível baixar o SHA-256 da versão {release.versao}. ({e})") from e

    try:
        with _abrir(release.url_exe, 30) as resp, open(destino, "wb") as f:
            total = int(resp.headers.get("Content-Length") or release.tamanho or 0)
            lido = 0
            progresso(lido, total)
            while bloco := resp.read(BLOCO):
                if cancelado():
                    raise FalhaAtualizacao("Download cancelado.")
                f.write(bloco)
                lido += len(bloco)
                progresso(lido, total)
    except FalhaAtualizacao:
        destino.unlink(missing_ok=True)
        raise
    except PermissionError as e:
        destino.unlink(missing_ok=True)
        raise FalhaAtualizacao(f"Sem permissão para gravar em {exe.parent}. Baixe a versão pela página da Release.") from e
    except Exception as e:
        destino.unlink(missing_ok=True)
        raise FalhaAtualizacao(f"O download falhou. Verifique a internet e tente de novo. ({e})") from e

    if sha256(destino) != esperado:
        destino.unlink(missing_ok=True)
        raise FalhaAtualizacao("O arquivo baixado não confere com o SHA-256 da Release. Nada foi alterado.")
    return destino


def instalar(novo: Path, exe: Path) -> None:
    """Troca o .exe atual pelo novo; se algo falhar, devolve o original."""
    antigo = _antigo(exe)
    try:
        antigo.unlink(missing_ok=True)
        os.replace(exe, antigo)
    except OSError as e:
        raise FalhaAtualizacao(f"Não foi possível substituir {exe.name}. ({e})") from e
    try:
        os.replace(novo, exe)
    except OSError as e:
        os.replace(antigo, exe)
        raise FalhaAtualizacao(f"Não foi possível instalar a nova versão. ({e})") from e
