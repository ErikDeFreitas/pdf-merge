"""
Mesclador de PDFs por pastas: Fatura > CVA > CT-es

Estrutura esperada:
    PastaPrincipal/
        84829/            <- uma subpasta por fatura
            qualquer.pdf  <- fatura, CVA e CT-es (juntos ou separados)
            outro.pdf
        84830/
            ...
Resultado:
    PastaPrincipal/84829.pdf
    PastaPrincipal/84830.pdf

Os arquivos NÃO precisam ter nome padronizado: cada página é identificada
pelo texto (CONTROLE DE VEÍCULOS ALUGADOS = CVA, DACTE = CT-e, FATURA = fatura).

Dependência: pip install pypdf
Uso por tela:      python mesclar_pastas.py
Uso por terminal:  python mesclar_pastas.py "C:\\caminho\\PastaPrincipal"
"""
import re
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter



def classificar(texto):
    """Retorna 'cva', 'cte', 'fatura' ou None, conforme o texto da página."""
    t = (texto or "").upper()
    if "CONTROLE DE VEÍCULOS" in t or "CONTROLE DE VEICULOS" in t:
        return "cva"
    if "DACTE" in t:
        return "cte"
    if "FATURA" in t and ("DADOS DO SACADO" in t or "RELAÇÃO DOS FRETES" in t):
        return "fatura"
    return None


def numero_fatura(texto, padrao):
    m = re.search(r"FATURA\s*N[º°o]?\s*(\d+)", texto or "", re.IGNORECASE)
    return m.group(1) if m else padrao


def mesclar_pasta(subpasta, pasta_saida, log, usados):
    """Mescla os PDFs de uma subpasta. Retorna o caminho gerado ou None."""
    faturas, cvas, ctes, outras = [], [], [], []
    numero = None

    pdfs = sorted(subpasta.glob("*.pdf"))
    if not pdfs:
        log(f"[PULADA] {subpasta.name}: nenhum PDF encontrado.")
        return None

    for pdf in pdfs:
        try:
            leitor = PdfReader(pdf)
            for i, pagina in enumerate(leitor.pages):
                texto = pagina.extract_text()
                tipo = classificar(texto)
                if tipo == "fatura":
                    faturas.append(pagina)
                    numero = numero or numero_fatura(texto, None)
                elif tipo == "cva":
                    cvas.append(pagina)
                elif tipo == "cte":
                    ctes.append(pagina)
                else:
                    outras.append(f"{pdf.name} (pág. {i + 1})")
        except Exception as e:
            log(f"[ERRO] {subpasta.name}/{pdf.name}: {e}")
            return None

    if not faturas:
        log(f"[PULADA] {subpasta.name}: fatura não encontrada.")
        return None
    if not cvas:
        log(f"[PULADA] {subpasta.name}: CVA não encontrado.")
        return None
    if outras:
        log(f"[AVISO] {subpasta.name}: páginas não identificadas e ignoradas: "
            + ", ".join(outras))

    writer = PdfWriter()
    for pagina in faturas + cvas + ctes:
        writer.add_page(pagina)

    base = numero or subpasta.name
    nome, n = base, 2
    while nome in usados:  # duas pastas com o mesmo nº de fatura: não sobrescreve
        nome = f"{base}_{n}"
        n += 1
    usados.add(nome)
    if nome != base:
        log(f"[AVISO] {subpasta.name}: fatura {base} repetida, salvando como {nome}.pdf")
    saida = pasta_saida / f"{nome}.pdf"
    with open(saida, "wb") as f:
        writer.write(f)

    log(f"[OK] {subpasta.name}: {saida.name} "
        f"({len(faturas)} fatura, {len(cvas)} CVA, {len(ctes)} CT-e = "
        f"{len(writer.pages)} páginas)")
    return saida


def processar(pasta_principal, log=print):
    pasta_principal = Path(pasta_principal)
    subpastas = sorted(p for p in pasta_principal.iterdir() if p.is_dir())
    if not subpastas:
        log("Nenhuma subpasta encontrada.")
        return 0
    gerados = 0
    usados = set()
    for sub in subpastas:
        if mesclar_pasta(sub, pasta_principal, log, usados):
            gerados += 1
    log(f"\nConcluído: {gerados} de {len(subpastas)} pastas processadas.")
    return gerados


def tela():
    import tkinter as tk
    from tkinter import filedialog, scrolledtext

    janela = tk.Tk()
    janela.title("Mesclar PDFs por pastas - Fatura > CVA > CT-es")
    janela.geometry("680x420")

    var = tk.StringVar()

    topo = tk.Frame(janela)
    topo.pack(fill="x", padx=12, pady=10)
    tk.Label(topo, text="Pasta principal:").pack(side="left")
    tk.Entry(topo, textvariable=var, width=60).pack(side="left", padx=6)

    def escolher():
        caminho = filedialog.askdirectory()
        if caminho:
            var.set(caminho)

    tk.Button(topo, text="...", command=escolher).pack(side="left")

    caixa = scrolledtext.ScrolledText(janela, height=18, state="disabled")
    caixa.pack(fill="both", expand=True, padx=12, pady=4)

    def log(msg):
        caixa.configure(state="normal")
        caixa.insert("end", msg + "\n")
        caixa.see("end")
        caixa.configure(state="disabled")
        janela.update_idletasks()

    def iniciar():
        if not var.get():
            log("Selecione a pasta principal.")
            return
        try:
            processar(var.get(), log)
        except Exception as e:
            log(f"[ERRO] {e}")

    tk.Button(janela, text="Mesclar tudo", command=iniciar, width=20).pack(pady=10)
    janela.mainloop()


if __name__ == "__main__":
    if len(sys.argv) == 2:
        processar(sys.argv[1])
    else:
        tela()
