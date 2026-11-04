"""
Núcleo do Mesclador de PDFs: regras de negócio, sem nenhuma dependência de interface.

Estrutura esperada (uma subpasta por fatura):
    PastaPrincipal/
        85067/
            85067.pdf   <- Fatura + CT-es/NDs (mesmo nome da pasta)
            2.pdf       <- CVA                    (obrigatório)
            3.pdf       <- Solicitação especial   (EXT / EME)
            4.pdf|png   <- Print do Google Maps   (EXT / EME)
            7.pdf       <- Ocorrência             (ND)

Resultado (na própria pasta principal):
    PastaPrincipal/85067.pdf

Ordem do PDF final:
    Fatura > CVA > CT-es > Solicitação especial > Print do Maps > Ocorrência

No PDF principal, tudo antes da primeira página de CT-e (DACTE) ou Nota de
Débito é a fatura; dali em diante são os CT-es/NDs.
"""
from __future__ import annotations

import io
import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

logging.getLogger("pypdf").setLevel(logging.ERROR)

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
ARQ_CVA = "2"
ARQ_SOLICITACAO = "3"
ARQ_MAPS = "4"
ARQ_OCORRENCIA = "7"
AUXILIARES = frozenset({ARQ_CVA, ARQ_SOLICITACAO, ARQ_MAPS, ARQ_OCORRENCIA})

EXT_PDF = (".pdf",)
EXT_IMAGEM = (".png", ".jpg", ".jpeg")

# Tipo da fatura, deduzido pelos arquivos opcionais presentes.
TIPOS = {
    frozenset(): "Dedicado",
    frozenset({ARQ_OCORRENCIA}): "Dedicado ND",
    frozenset({ARQ_SOLICITACAO, ARQ_MAPS}): "EXT / EME",
    frozenset({ARQ_SOLICITACAO, ARQ_MAPS, ARQ_OCORRENCIA}): "EXT ND / EME ND",
}

# Textos (sem espaços, maiúsculos) que marcam o início dos CT-es/NDs.
# Sem espaços porque alguns PDFs separam letras ("V ALOR", "D ACTE").
MARCADORES_TRANSPORTE = ("DACTE", "NOTADEDÉBITO", "NOTADEDEBITO")
MARCADORES_ND = ("NOTADEDÉBITO", "NOTADEDEBITO")

# Nota de Débito com "FISCAL:" vazio (logo depois vem o próximo rótulo ou o fim)
# é substituída pelo CT-e correspondente e fica FORA do PDF final.
# O texto é comparado sem espaços nem quebras de linha, então "FISCAL:" seguido
# de "OBSERVACOES:" na linha de baixo vira "FISCAL:OBSERVACOES:".
FISCAL_VAZIO = re.compile(r"FISCAL:(?=OBSERVA|USU[ÁA]RIOEMISSOR|DECLARO|$)")
NUMERO_ND = re.compile(r"N[ÚU]MERO(\d+)")

A4_PT = (595, 842)  # 1 pt = 1/72 pol.
DPI_IMAGEM = 150


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------
class Status(str, Enum):
    OK = "OK"
    AVISO = "Aviso"      # gerado, mas com algo para conferir
    PULADA = "Pulada"    # não gerado por falta/inconsistência de arquivos
    ERRO = "Erro"        # não gerado por falha (arquivo corrompido, sem permissão...)


@dataclass
class Resultado:
    pasta: str
    status: Status
    tipo: str = ""
    saida: Path | None = None
    paginas: dict[str, int] = field(default_factory=dict)
    mensagens: list[str] = field(default_factory=list)
    nds_desconsideradas: list[str] = field(default_factory=list)  # números das NDs sem Fiscal

    @property
    def gerou(self) -> bool:
        return self.saida is not None

    @property
    def total_paginas(self) -> int:
        return sum(self.paginas.values())

    def composicao(self) -> str:
        return ", ".join(f"{n} {nome}" for nome, n in self.paginas.items() if n)

    def descricao(self) -> str:
        partes = []
        if self.saida:
            partes.append(f"{self.saida.name}: {self.composicao()}")
        if self.nds_desconsideradas:
            n = len(self.nds_desconsideradas)
            partes.append(
                f"{n} ND sem Fiscal desconsiderada{'s' if n > 1 else ''} "
                f"({', '.join(self.nds_desconsideradas)})"
            )
        partes.extend(self.mensagens)
        return " · ".join(partes)


@dataclass
class Execucao:
    pasta_principal: Path
    total: int
    resultados: list[Resultado] = field(default_factory=list)
    cancelada: bool = False

    def contar(self, *status: Status) -> int:
        return sum(1 for r in self.resultados if r.status in status)

    @property
    def geradas(self) -> int:
        return sum(1 for r in self.resultados if r.gerou)


class PastaInvalida(Exception):
    """A pasta principal não pode ser processada."""


class _Falha(Exception):
    """Uma subpasta não pode ser processada (motivo amigável para o usuário)."""

    def __init__(self, motivo: str, status: Status = Status.PULADA):
        super().__init__(motivo)
        self.status = status


# ---------------------------------------------------------------------------
# Leitura de arquivos
# ---------------------------------------------------------------------------
def _abrir_pdf(caminho: Path) -> PdfReader:
    """Lê o PDF todo para a memória (não deixa o arquivo preso) e valida."""
    try:
        reader = PdfReader(io.BytesIO(caminho.read_bytes()))
        if reader.is_encrypted and not reader.decrypt(""):
            raise _Falha(f"{caminho.name} está protegido por senha.", Status.ERRO)
        _ = len(reader.pages)
        return reader
    except _Falha:
        raise
    except PermissionError:
        raise _Falha(f"sem permissão para ler {caminho.name}.", Status.ERRO)
    except (PdfReadError, ValueError, KeyError) as e:
        raise _Falha(f"{caminho.name} está corrompido ou não é um PDF válido ({e}).", Status.ERRO)


def _imagem_para_paginas(caminho: Path) -> list:
    """Converte PNG/JPG em uma página A4 (retrato ou paisagem, conforme a imagem)."""
    from PIL import Image, ImageOps

    try:
        with Image.open(caminho) as original:
            img = ImageOps.exif_transpose(original).convert("RGB")
    except Exception as e:
        raise _Falha(f"não foi possível abrir a imagem {caminho.name} ({e}).", Status.ERRO)

    largura, altura = A4_PT if img.height >= img.width else (A4_PT[1], A4_PT[0])
    escala = DPI_IMAGEM / 72
    folha_w, folha_h = int(largura * escala), int(altura * escala)
    img.thumbnail((folha_w, folha_h))
    folha = Image.new("RGB", (folha_w, folha_h), "white")
    folha.paste(img, ((folha_w - img.width) // 2, (folha_h - img.height) // 2))

    buf = io.BytesIO()
    folha.save(buf, "PDF", resolution=DPI_IMAGEM)
    buf.seek(0)
    return list(PdfReader(buf).pages)


def _achar(subpasta: Path, nome: str, extensoes: tuple[str, ...]) -> list[Path]:
    """Arquivos 'nome.ext' na subpasta, sem diferenciar maiúsculas/minúsculas."""
    return [
        a for a in sorted(subpasta.iterdir(), key=lambda p: p.name.lower())
        if a.is_file() and a.stem.lower() == nome and a.suffix.lower() in extensoes
    ]


def _ler_auxiliar(subpasta: Path, nome: str, extensoes, avisos: list[str]) -> list | None:
    """Páginas do arquivo auxiliar, ou None se ele não existir."""
    candidatos = _achar(subpasta, nome, extensoes)
    if not candidatos:
        return None
    arq = candidatos[0]
    if len(candidatos) > 1:
        avisos.append(f"há mais de um arquivo '{nome}' ({', '.join(c.name for c in candidatos)}); usado {arq.name}.")
    if arq.suffix.lower() in EXT_IMAGEM:
        return _imagem_para_paginas(arq)
    return list(_abrir_pdf(arq).pages)


def _achar_principal(subpasta: Path, avisos: list[str]) -> Path:
    """PDF da fatura: de preferência o que tem o mesmo nome da pasta."""
    pdfs = [
        p for p in sorted(subpasta.iterdir(), key=lambda p: p.name.lower())
        if p.is_file() and p.suffix.lower() == ".pdf" and p.stem.lower() not in AUXILIARES
    ]
    if not pdfs:
        raise _Falha("PDF da fatura (com os CT-es) não encontrado.")

    mesmo_nome = [p for p in pdfs if p.stem.lower() == subpasta.name.lower()]
    if mesmo_nome:
        extras = [p.name for p in pdfs if p not in mesmo_nome]
        if extras:
            avisos.append(f"PDFs ignorados: {', '.join(extras)}.")
        return mesmo_nome[0]

    if len(pdfs) == 1:
        avisos.append(f"o PDF da fatura ({pdfs[0].name}) não tem o mesmo nome da pasta.")
        return pdfs[0]

    raise _Falha(
        f"vários PDFs podem ser a fatura ({', '.join(p.name for p in pdfs)}) "
        f"e nenhum tem o nome da pasta. Renomeie o correto para {subpasta.name}.pdf."
    )


def _texto(pagina) -> str:
    try:
        texto = pagina.extract_text() or ""
    except Exception:
        texto = ""
    return "".join(texto.split()).upper()


def nd_sem_fiscal(texto: str) -> bool:
    """Página de Nota de Débito cujo campo "FISCAL:" (em Observações) está vazio.

    `texto` é o texto da página já sem espaços e em maiúsculas (ver _texto).
    """
    return any(m in texto for m in MARCADORES_ND) and bool(FISCAL_VAZIO.search(texto))


def _numero_nd(texto: str) -> str | None:
    if not any(m in texto for m in MARCADORES_ND):
        return None
    m = NUMERO_ND.search(texto)
    return m.group(1) if m else None


def remover_nds_sem_fiscal(paginas: list) -> tuple[list, list[str]]:
    """Tira do PDF final as NDs com "FISCAL:" vazio. Devolve (mantidas, números removidos).

    Uma ND pode ter várias páginas (FL 1/2, 2/2) e só a primeira mostra o campo
    "FISCAL:"; as demais continuam a lista de notas fiscais. Por isso a decisão é por número da ND: se ela está sem Fiscal,
    todas as páginas com esse número saem.
    """
    textos = [_texto(p) for p in paginas]
    numeros = [_numero_nd(t) for t in textos]

    remover: list[str] = []
    indices_sem_numero: set[int] = set()
    for i, texto in enumerate(textos):
        if nd_sem_fiscal(texto):
            if numeros[i]:
                if numeros[i] not in remover:
                    remover.append(numeros[i])
            else:
                indices_sem_numero.add(i)

    mantidas = [
        p for i, p in enumerate(paginas)
        if i not in indices_sem_numero and (numeros[i] is None or numeros[i] not in remover)
    ]
    removidas = remover + ["s/ número"] * len(indices_sem_numero)
    return mantidas, removidas


def separar_fatura_e_ctes(paginas: list, nome_arquivo: str) -> tuple[list, list]:
    """Tudo antes do 1º CT-e/ND é fatura; dali em diante são CT-es/NDs."""
    tem_texto = False
    for i, pagina in enumerate(paginas):
        texto = _texto(pagina)
        tem_texto = tem_texto or bool(texto)
        if any(m in texto for m in MARCADORES_TRANSPORTE):
            if i == 0:
                raise _Falha(f"{nome_arquivo} começa direto em um CT-e/ND, sem a fatura.")
            return paginas[:i], paginas[i:]

    if not tem_texto:
        raise _Falha(
            f"{nome_arquivo} parece ser escaneado (não tem texto pesquisável), "
            "então não dá para saber onde começam os CT-es."
        )
    raise _Falha(f"nenhuma página de CT-e (DACTE) ou Nota de Débito em {nome_arquivo}.")


# ---------------------------------------------------------------------------
# Gravação
# ---------------------------------------------------------------------------
def _nome_livre(base: str, usados: set[str]) -> str:
    nome, n = base, 2
    while nome.lower() in usados:
        nome = f"{base}_{n}"
        n += 1
    return nome


def _salvar(writer: PdfWriter, destino: Path) -> None:
    """Grava em arquivo temporário e só então substitui: nunca deixa PDF pela metade."""
    temp = destino.with_name(f".{destino.name}.tmp")
    try:
        with open(temp, "wb") as f:
            writer.write(f)
        os.replace(temp, destino)
    except PermissionError:
        temp.unlink(missing_ok=True)
        raise _Falha(
            f"não foi possível salvar {destino.name}: o arquivo está aberto em outro "
            "programa (ex.: leitor de PDF). Feche-o e rode de novo.",
            Status.ERRO,
        )
    except OSError as e:
        temp.unlink(missing_ok=True)
        raise _Falha(f"não foi possível salvar {destino.name} ({e}).", Status.ERRO)


# ---------------------------------------------------------------------------
# Processamento
# ---------------------------------------------------------------------------
def mesclar_pasta(subpasta: Path, pasta_saida: Path, usados: set[str]) -> Resultado:
    """Mescla os arquivos de uma subpasta. Nunca lança exceção: tudo vira Resultado."""
    r = Resultado(pasta=subpasta.name, status=Status.OK)
    avisos = r.mensagens
    try:
        principal = _achar_principal(subpasta, avisos)
        fatura, ctes = separar_fatura_e_ctes(list(_abrir_pdf(principal).pages), principal.name)
        ctes, r.nds_desconsideradas = remover_nds_sem_fiscal(ctes)
        if not ctes:
            raise _Falha(f"{principal.name} só tem Notas de Débito sem Fiscal; nenhum CT-e/ND para mesclar.")

        cva = _ler_auxiliar(subpasta, ARQ_CVA, EXT_PDF, avisos)
        if cva is None:
            raise _Falha(f"CVA ({ARQ_CVA}.pdf) não encontrado.")
        solicitacao = _ler_auxiliar(subpasta, ARQ_SOLICITACAO, EXT_PDF, avisos)
        maps = _ler_auxiliar(subpasta, ARQ_MAPS, EXT_PDF + EXT_IMAGEM, avisos)
        ocorrencia = _ler_auxiliar(subpasta, ARQ_OCORRENCIA, EXT_PDF, avisos)

        presentes = frozenset(
            nome for nome, pags in (
                (ARQ_SOLICITACAO, solicitacao), (ARQ_MAPS, maps), (ARQ_OCORRENCIA, ocorrencia),
            ) if pags is not None
        )
        r.tipo = TIPOS.get(presentes, "Fora do padrão")
        if presentes not in TIPOS:
            avisos.append(
                f"combinação de anexos fora do padrão ({', '.join(sorted(presentes))}); confira o PDF."
            )

        grupos = {
            "fatura": fatura,
            "CVA": cva,
            "CT-e": ctes,
            "solicitação": solicitacao or [],
            "maps": maps or [],
            "ocorrência": ocorrencia or [],
        }
        writer = PdfWriter()
        for paginas in grupos.values():
            for pagina in paginas:
                writer.add_page(pagina)

        nome = _nome_livre(principal.stem, usados)
        if nome != principal.stem:
            avisos.append(f"fatura {principal.stem} repetida em outra pasta; salva como {nome}.pdf.")
        destino = pasta_saida / f"{nome}.pdf"
        _salvar(writer, destino)
        usados.add(nome.lower())

        r.saida = destino
        r.paginas = {k: len(v) for k, v in grupos.items()}
        if avisos:
            r.status = Status.AVISO
    except _Falha as e:
        r.status = e.status
        avisos.insert(0, str(e))
    except Exception as e:  # rede de segurança: uma pasta nunca derruba o lote
        r.status = Status.ERRO
        avisos.insert(0, f"erro inesperado: {type(e).__name__}: {e}")
    return r


def listar_subpastas(pasta_principal: Path) -> list[Path]:
    """Subpastas de faturas (ignora pastas que começam com _ ou .)."""
    return sorted(
        (p for p in Path(pasta_principal).iterdir() if p.is_dir() and not p.name.startswith(("_", "."))),
        key=lambda p: p.name.lower(),
    )


def processar(
    pasta_principal: Path | str,
    ao_iniciar: Callable[[int, int, str], None] | None = None,
    ao_concluir: Callable[[Resultado], None] | None = None,
    cancelado: Callable[[], bool] | None = None,
) -> Execucao:
    pasta_principal = Path(pasta_principal)
    if not pasta_principal.is_dir():
        raise PastaInvalida(f"Pasta não encontrada: {pasta_principal}")
    subpastas = listar_subpastas(pasta_principal)
    if not subpastas:
        raise PastaInvalida("A pasta escolhida não tem subpastas de faturas.")

    execucao = Execucao(pasta_principal, total=len(subpastas))
    usados: set[str] = set()
    for i, sub in enumerate(subpastas):
        if cancelado and cancelado():
            execucao.cancelada = True
            break
        if ao_iniciar:
            ao_iniciar(i, len(subpastas), sub.name)
        resultado = mesclar_pasta(sub, pasta_principal, usados)
        execucao.resultados.append(resultado)
        if ao_concluir:
            ao_concluir(resultado)
    return execucao


def main(argv: list[str]) -> int:
    """Uso por terminal: python -m core "C:\\caminho\\PastaPrincipal" """
    if len(argv) != 1:
        print('Uso: python -m core "C:\\caminho\\PastaPrincipal"')
        return 2
    try:
        execucao = processar(
            argv[0],
            ao_concluir=lambda r: print(f"[{r.status.value.upper()}] {r.pasta}: {r.descricao()}"),
        )
    except PastaInvalida as e:
        print(e)
        return 1
    print(f"\nConcluído: {execucao.geradas} de {execucao.total} faturas geradas em {execucao.pasta_principal}")
    return 0
