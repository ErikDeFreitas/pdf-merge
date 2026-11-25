"""MODULO do Mesclador para a casca e o avulso. Leve: só dados e a fábrica (sem Qt widgets, pypdf ou PIL)."""

from tcm_ui.modulo import Contexto, Modulo, Pagina

from mesclador import __version__, dados


def criar(contexto: Contexto):
    from mesclador.instancia import Mesclador  # import pesado só quando o módulo é aberto
    return Mesclador(contexto)


MODULO = Modulo(
    id="mesclador",
    nome="Mesclador de PDFs",
    icone="camadas",
    versao=__version__,
    grupo_ad="SF-Mesclador",
    repositorio="ErikDeFreitas/pdf-merge",
    nome_exe="MesclarPDFs.exe",
    pasta_dados=dados.PASTA,
    paginas=(Pagina("mesclar", "Mesclar PDFs", "Junte fatura, CVA, CT-es e anexos em um único PDF por pasta.",
                    "camadas"),),
    criar=criar,
)
