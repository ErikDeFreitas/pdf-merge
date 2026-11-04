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

Ao abrir, o programa consulta a última Release no GitHub. Se houver versão nova,
aparece o aviso **Nova versão disponível**: em **Atualizar** ele baixa o novo `.exe`
(com barra de progresso), confere o SHA-256 publicado na Release e reabre já atualizado.
Sem internet, nada aparece. Se uma mesclagem estiver rodando, o aviso espera ela terminar.

Alguns antivírus sinalizam executáveis gerados com PyInstaller; se acontecer,
libere o arquivo.

## Desenvolver

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Modo terminal (sem janela): `python -m core "C:\caminho\PastaPrincipal"`

## Lançar uma versão

```
git tag v2.1.0
git push origin v2.1.0
```

O GitHub Actions gera o `.exe` e publica na Release automaticamente
(`.github/workflows/release.yml`). A versão exibida no app vem da tag.

## Estrutura

| Pasta/arquivo        | Conteúdo                                         |
|----------------------|--------------------------------------------------|
| `core/mesclagem.py`  | Regras de negócio (sem interface)                |
| `core/worker.py`     | Execução em segundo plano para a janela          |
| `core/atualizacao.py`| Busca, download e instalação de nova versão      |
| `ui/atualizacao.py`  | Aviso de nova versão com barra de progresso      |
| `ui/themes.py`       | Tokens do Design System e temas Light/Dark       |
| `ui/styles.qss`      | Estilos globais (QSS)                            |
| `ui/components.py`   | Componentes reutilizáveis                        |
| `main.py`            | Aplicação                                        |
| `MesclarPDFs.spec`   | Configuração do PyInstaller                      |
| `assets/`            | Ícone do executável (`MesclarPDFs.ico`)          |
