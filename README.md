# Mesclador de PDFs por Pastas

Ferramenta em Python que percorre uma pasta principal, junta os PDFs de cada subpasta em **um único arquivo** na ordem correta e salva o resultado na própria pasta principal.

Criada para o fluxo de faturamento de transportadoras: **Fatura → CVA → CT-es**.

## O que ela faz

- Percorre todas as subpastas da pasta principal (uma subpasta por fatura).
- Identifica cada página pelo **conteúdo**, não pelo nome do arquivo:
  - **Fatura**: páginas com "FATURA", "Dados do Sacado" ou "Relação dos Fretes"
  - **CVA** (Controle de Veículos Alugados): páginas com "CONTROLE DE VEÍCULOS ALUGADOS"
  - **CT-e**: páginas com "DACTE"
- Monta o PDF final na ordem **Fatura → CVA → CT-es** (qualquer quantidade de CT-es).
- Salva na pasta principal com o **número da fatura** como nome (ex.: `84829.pdf`).
- Funciona com os documentos juntos num único PDF ou separados em vários arquivos.
- Tem interface gráfica simples (tkinter) e também roda por terminal.

## Estrutura de pastas

Antes:

```
PastaPrincipal/
├── 84829/
│   ├── fatura_e_ctes.pdf
│   └── cva.pdf
└── 84830/
    ├── fatura.pdf
    ├── cte_1.pdf
    ├── cte_2.pdf
    └── cva.pdf
```

Depois de executar:

```
PastaPrincipal/
├── 84829.pdf      <- gerado
├── 84830.pdf      <- gerado
├── 84829/
└── 84830/
```

Os arquivos originais nunca são alterados.

## Requisitos

- Python 3.9 ou superior
- [pypdf](https://pypi.org/project/pypdf/)

```bash
pip install pypdf
```

## Como usar

### Pela interface gráfica

```bash
python mesclar_pastas.py
```

Escolha a pasta principal e clique em **Mesclar tudo**. O andamento aparece na própria janela.

### Pelo terminal

```bash
python mesclar_pastas.py "C:\caminho\PastaPrincipal"
```

### Exemplo de saída

```
[OK] 84829: 84829.pdf (1 fatura, 1 CVA, 2 CT-e = 4 páginas)
[OK] 84830: 84830.pdf (1 fatura, 1 CVA, 5 CT-e = 7 páginas)
[PULADA] 84831: CVA não encontrado.

Concluído: 2 de 3 pastas processadas.
```

## Gerar o executável (.exe)

No Windows, com Python instalado:

1. Deixe `mesclar_pastas.py` e `gerar_exe.bat` na mesma pasta.
2. Execute o `gerar_exe.bat`.
3. O executável será criado em `dist\MesclarPDFs.exe`.

O `.exe` roda em máquinas sem Python. Alguns antivírus podem sinalizar executáveis gerados com PyInstaller; se acontecer, libere o arquivo ou a pasta.

## Comportamento e limitações

| Situação | O que acontece |
|---|---|
| Subpasta sem fatura ou sem CVA | A pasta é pulada, com aviso no log |
| Página não reconhecida | É ignorada, com aviso informando arquivo e página |
| PDF com erro de leitura | A pasta é pulada, com aviso |
| Duas pastas com o mesmo nº de fatura | A segunda é salva como `NUMERO_2.pdf`, sem sobrescrever |
| PDF escaneado (só imagem, sem texto) | Não é possível identificar as páginas (não há OCR) |

## Estrutura do projeto

```
.
├── mesclar_pastas.py   # script principal (interface + lógica)
├── gerar_exe.bat       # gera o executável com PyInstaller
└── README.md
```
