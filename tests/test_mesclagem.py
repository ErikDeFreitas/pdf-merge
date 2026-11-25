from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, StreamObject

from mesclador import mesclagem
from mesclador.mesclagem import Status


def _pdf(destino: Path, *textos: str | None) -> Path:
    """PDF com uma página por item; texto None = página em branco."""
    w = PdfWriter()
    for t in textos:
        if t is None:
            w.add_blank_page(width=595, height=842)
            continue
        p = w.add_blank_page(width=595, height=842)
        fonte = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        p[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): w._add_object(fonte)})
        })
        fluxo = StreamObject()
        fluxo.set_data(f"BT /F1 12 Tf 50 700 Td ({t}) Tj ET".encode("latin-1"))
        p[NameObject("/Contents")] = w._add_object(fluxo)
    with open(destino, "wb") as f:
        w.write(f)
    return destino


def _fatura(sub: Path, nome: str | None = None, com_cva: bool = True) -> Path:
    sub.mkdir(parents=True, exist_ok=True)
    _pdf(sub / f"{nome or sub.name}.pdf", "Fatura de servicos", "DACTE conhecimento 1", "DACTE conhecimento 2")
    if com_cva:
        _pdf(sub / "2.pdf", None)
    return sub


def test_listar_subpastas_ignora_arquivos(tmp_path):
    (tmp_path / "A").mkdir()
    (tmp_path / "B").mkdir()
    (tmp_path / "_oculta").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "solto.pdf").write_bytes(b"x")
    assert [p.name for p in mesclagem.listar_subpastas(tmp_path)] == ["A", "B"]


def test_subpasta_sem_principal_e_pulada_e_as_outras_seguem(tmp_path):
    _fatura(tmp_path / "100")
    (tmp_path / "200").mkdir()
    _pdf(tmp_path / "200" / "2.pdf", None)  # só auxiliar: sem PDF da fatura
    _fatura(tmp_path / "300")

    exe = mesclagem.processar(tmp_path)

    status = {r.pasta: r.status for r in exe.resultados}
    assert status == {"100": Status.OK, "200": Status.PULADA, "300": Status.OK}
    assert exe.geradas == 2
    assert len(PdfReader(tmp_path / "100.pdf").pages) == 4  # fatura + CVA + 2 CT-es
    assert not (tmp_path / "200.pdf").exists()


def test_pdf_corrompido_vira_erro_ou_pulada_sem_derrubar(tmp_path):
    sub = tmp_path / "100"
    sub.mkdir()
    (sub / "100.pdf").write_bytes(b"isto nao e um pdf")
    _pdf(sub / "2.pdf", None)
    _fatura(tmp_path / "200")

    exe = mesclagem.processar(tmp_path)

    ruim = next(r for r in exe.resultados if r.pasta == "100")
    assert ruim.status in (Status.ERRO, Status.PULADA)
    assert not ruim.gerou
    assert ruim.mensagens
    assert next(r for r in exe.resultados if r.pasta == "200").status == Status.OK


def test_imagem_jfif_entra_como_pagina(tmp_path):
    sub = _fatura(tmp_path / "100")
    _pdf(sub / "3.pdf", None)
    Image.new("RGB", (80, 60), "red").save(sub / "4.jfif", "JPEG")

    exe = mesclagem.processar(tmp_path)

    r = exe.resultados[0]
    assert r.status == Status.OK, r.mensagens
    assert r.tipo == "EXT / EME"
    assert r.paginas["maps"] == 1
    assert "4.jfif" in r.usados
    assert len(PdfReader(tmp_path / "100.pdf").pages) == 1 + 2 + 1 + 1 + 1  # fatura, CT-es, CVA, solicitação, maps


def test_cancelado_para_depois_da_pasta_atual(tmp_path):
    for n in ("100", "200", "300"):
        _fatura(tmp_path / n)
    concluidas = []

    exe = mesclagem.processar(
        tmp_path,
        ao_concluir=concluidas.append,
        cancelado=lambda: len(concluidas) >= 1,
    )

    assert exe.cancelada is True
    assert [r.pasta for r in exe.resultados] == ["100"]
    assert (tmp_path / "100.pdf").exists()
    assert not (tmp_path / "200.pdf").exists()


def test_cli_devolve_codigo(tmp_path, capsys):
    _fatura(tmp_path / "100")
    assert mesclagem.main([str(tmp_path)]) == 0
    assert "1 de 1 faturas geradas" in capsys.readouterr().out
    assert mesclagem.main([str(tmp_path / "nao_existe")]) == 1
    assert mesclagem.main([]) == 2
