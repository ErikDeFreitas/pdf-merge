# Mesclador de PDFs

Junta, para cada fatura, um único PDF na ordem:
**Fatura > CVA > CT-es > Solicitação especial > Print do Maps > Ocorrência**.

## Usar

Baixe o `MesclarPDFs.exe` da última [Release](../../releases/latest) e abra.
Escolha a pasta principal (uma subpasta por fatura) e clique em **Mesclar tudo**.

```
PastaPrincipal/
    85067/
        85067.pdf   Fatura + CT-es/NDs (mesmo nome da pasta)
        2.pdf       CVA (obrigatório)
        3.pdf       Solicitação especial   (EXT / EME)
        4.pdf|png   Print do Google Maps   (EXT / EME)
        7.pdf       Ocorrência             (ND)
```

Ao escolher a pasta, o app já mostra quantas faturas (subpastas) ela tem.
Os PDFs gerados são salvos na própria pasta principal (ex.: `PastaPrincipal/85067.pdf`)
e o resultado de cada fatura aparece na tela. Os arquivos originais nunca são alterados.

No PDF principal, tudo antes da primeira página de CT-e (DACTE) ou Nota de
Débito é considerado fatura. O tipo é deduzido pelos anexos presentes:

| Anexos       | Tipo            |
|--------------|-----------------|
| nenhum       | Dedicado        |
| 7            | Dedicado ND     |
| 3 e 4        | EXT / EME       |
| 3, 4 e 7     | EXT ND / EME ND |

## Comportamento

| Situação | Status | O que acontece |
|---|---|---|
| Tudo certo | OK | PDF gerado |
| PDF extra na pasta, nome da fatura diferente da pasta, anexos fora do padrão | Aviso | PDF gerado; o detalhe diz o que conferir |
| Sem CVA, sem CT-e/ND, começa direto no CT-e, vários PDFs candidatos | Pulada | Nada gerado; o motivo aparece na tabela |
| PDF escaneado (sem texto) | Pulada | Não há OCR; não dá para achar onde começam os CT-es |
| PDF corrompido, com senha ou aberto em outro programa | Erro | Só essa pasta falha; as demais seguem |
| Mesmo nº de fatura em duas pastas | Aviso | A segunda é salva como `NUMERO_2.pdf` |
| Nota de Débito com "FISCAL:" vazio (em Observações) | OK | A ND fica **fora do PDF final** (todas as páginas dela; o CT-e correspondente a substitui). O original não é alterado |

## Atualização automática

Ao abrir, o programa consulta a última Release no GitHub. Se houver versão nova, baixa em
segundo plano, confere o SHA-256, avisa e reinicia já atualizado. Se uma mesclagem estiver
rodando, a atualização fica para a próxima abertura. Sem internet, nada aparece.

Alguns antivírus sinalizam executáveis gerados com PyInstaller; se acontecer, libere o arquivo.

## Linha de comando

- `MesclarPDFs.exe "C:\caminho\PastaPrincipal"` abre a janela com a pasta já preenchida
  (o mesmo vale para `python main.py "C:\caminho\PastaPrincipal"`).
- `python -m mesclador "C:\caminho\PastaPrincipal"` mescla pelo terminal, sem janela.

## Desenvolver

A interface vem da biblioteca [`tcm-ui`](https://github.com/ErikDeFreitas/Tcm-ui).

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python main.py
```

Para desenvolver junto com o `tcm-ui`, instale-o editável a partir do clone vizinho
(`.venv\Scripts\pip install -e ..\Tcm-ui`) antes do `pip install -e ".[dev]"`.

Testes (não escrevem no registro nem na pasta real de dados):

```
.venv\Scripts\python -m pytest -q
```

Os dados do programa (log) ficam em `%LOCALAPPDATA%\MesclarPDFs`; defina `MESCLADOR_DADOS`
para usar outra pasta, por exemplo em testes.

## Gerar o executável

```
powershell -File build.ps1
```

Gera `dist\MesclarPDFs.exe` e `dist\MesclarPDFs.exe.sha256`.

## Lançar uma versão

1. Suba `__version__` em `src/mesclador/__init__.py` (ex.: `3.0.1`).
2. Crie a tag igual, com `v` na frente, e envie: `git tag v3.0.1` e `git push origin v3.0.1`.

O GitHub Actions (`.github/workflows/release.yml`) confere que a tag bate com `__version__`,
roda os testes, gera o `.exe` e o `.sha256` e publica a Release com os dois arquivos.
O `requirements.txt` fixa o `tcm-ui` numa tag (`v1.3.0`), que precisa existir no GitHub.

## Módulo do Sistema Financeiro

O Mesclador também é um módulo da casca Sistema Financeiro (`MODULO` em
`src/mesclador/modulo.py`, registrado no entry point `sistema_financeiro.modulos`).
Na casca ele aparece para quem está no grupo `SF-Mesclador`.

## Estrutura

| Pasta/arquivo                | Conteúdo                                              |
|------------------------------|-------------------------------------------------------|
| `src/mesclador/mesclagem.py` | Regras de negócio (sem interface)                     |
| `src/mesclador/worker.py`    | Execução em segundo plano para a janela               |
| `src/mesclador/tela.py`      | Tela do módulo                                        |
| `src/mesclador/instancia.py` | Instância do módulo (casca e avulso)                  |
| `src/mesclador/modulo.py`    | Registro do módulo (`MODULO`)                         |
| `src/mesclador/dados.py`     | Pasta de dados                                        |
| `main.py`                    | Ponto de entrada do `.exe` avulso                     |
| `build.ps1`                  | Gera o `.exe` e o `.sha256`                           |
| `assets/`                    | Ícone do executável (`MesclarPDFs.ico`)               |
| `tests/`                     | Testes (pytest)                                       |
