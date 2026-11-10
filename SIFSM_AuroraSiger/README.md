# SIFSM – Sistema Integrado de Futuro Sustentável em Marte

**Colônia Aurora Siger · Atividade Integradora – FIAP · Ciência da Computação**

**Autor:** Denis Urbano Cereto – RM569187 (projeto individual)

## Objetivo

O SIFSM é um protótipo em Python que organiza os dados da colônia Aurora Siger (7 módulos e 210 leituras de sensores em 30 sols). Com esses dados, ele apoia decisões sustentáveis sobre energia, ambiente e manutenção. O sistema integra os seguintes elementos:

- banco de dados com CRUD e tratamento de erros;
- regra booleana `S = (A AND B) OR C`, também implementada em circuito (portas lógicas e Arduino/Tinkercad);
- estruturas de dados: fila, fila de prioridade, pilha com "desfazer", tabela hash e grafo;
- simulação energética com integração numérica e simbólica e convolução;
- regressão linear simples e múltipla para prever consumo;
- assistente multiagente com triador, especialistas, ferramentas, handoff, guardrails, sessão, tracing, RAG e aprovação humana;
- análise de arquitetura computacional com benchmark real;
- análise integrada de sustentabilidade, a opção 10 do menu.

## Arquivos da entrega

| Arquivo | Conteúdo |
|---|---|
| **`codigo_fonte.py`** | **Arquivo principal**: menu no terminal e modo `--demo` |
| `banco_dados.py` | Conexão Oracle/SQLite, CRUD de módulos e leituras, alertas e carga do JSON |
| `regras_logicas.py` | Regras booleanas, tabela verdade e avaliação das leituras |
| `estruturas_dados.py` | Fila FIFO, fila de prioridade (heap), pilha, tabela hash própria e grafo (BFS/DFS) |
| `simulacao_computacional.py` | Simulação energética (3 cenários), SoC por integração, SymPy × trapézios e convolução |
| `modelo_linear.py` | Análise exploratória, regressão simples e múltipla, MAE/RMSE/R², VIF e resíduos |
| `agentes_ia.py` | Sistema multiagente executável offline |
| `agentes_openai_sdk_conceitual.py` | Mesma arquitetura com o OpenAI Agents SDK (conceitual; requer chave de API) |
| `arquitetura_computacional.py` | Benchmark sequencial × vetorizado, float64 × float32 e mapa de hardware |
| `script_banco.sql` | Criação das tabelas no Oracle e carga dos módulos |
| `dados_aurora_siger.json` | Base simulada: módulos, leituras, conexões da rede e solicitações |
| `gerar_dados.py` | Script que gerou o JSON (semente fixa, reproduzível) |
| `circuito_logico.png` / `circuito_logico.pdf` | Circuito por portas lógicas e esquema de ligação no Arduino |
| `arduino_sifsm.ino` | Código do Arduino para colar no Tinkercad |
| `link_tinkercad.txt` | Link do circuito no Tinkercad e o passo a passo de montagem |
| `gerar_circuito.py` | Script que desenha o circuito (requer `schemdraw`) |
| `relatorio_tecnico.pdf` / `.md` | Relatório técnico completo |
| `link_video.txt` | Link do vídeo no YouTube (não listado) |
| `requirements.txt` | Dependências |
| `graficos_ou_imagens/` | Gráficos gerados, diagrama de arquitetura e evidência de execução |

## Dependências

Use Python 3.10 ou superior. Todas as bibliotecas abaixo foram trabalhadas nas disciplinas da fase:

```bash
pip install numpy pandas matplotlib scipy sympy scikit-learn
```

`sqlite3` já vem com o Python. Os pacotes opcionais são:

- `oracledb`, para usar o Oracle da FIAP;
- `schemdraw`, só para regenerar a figura do circuito;
- `openai-agents`, só para a versão conceitual com LLM.

## Como executar

```bash
# 1) Menu interativo (recomendado)
python codigo_fonte.py

# 2) Demonstração automática de TODAS as funcionalidades (sem digitar nada).
#    Gera os gráficos e graficos_ou_imagens/evidencia_execucao_demo.txt
python codigo_fonte.py --demo
```

Cada módulo também roda sozinho: `python simulacao_computacional.py`, `python modelo_linear.py`, `python regras_logicas.py` e `python arquitetura_computacional.py`.

### Banco de dados: Oracle ou SQLite

Por padrão, o sistema cria `banco_aurora_siger.db` (SQLite) e o carrega a partir do JSON na primeira execução. Assim, o avaliador consegue rodar o projeto sem credenciais.

Para usar o Oracle da FIAP, como nas aulas:

1. Execute `script_banco.sql` no Oracle SQL Developer.
2. Instale o driver com `pip install oracledb`.
3. Defina as variáveis de ambiente e execute:

```bash
# Windows (PowerShell)
$env:SIFSM_DB="oracle"; $env:ORACLE_USER="rmXXXXXX"; $env:ORACLE_PASSWORD="senha"
python codigo_fonte.py
```

O DSN padrão é `oracle.fiap.com.br:1521/ORCL`; para outro servidor, defina `ORACLE_DSN`. Se a conexão falhar, o sistema avisa e volta automaticamente para o SQLite. As tabelas e as instruções SQL, com bind variables `:nome`, são as mesmas nos dois bancos.

4. Na primeira execução com Oracle, use a opção **11 – Recarregar base a partir do JSON** para inserir as 210 leituras.

## Menu principal

```
 1 - Módulos da colônia (CRUD)          7 - Modelo linear (previsão de consumo)
 2 - Leituras de sensores (CRUD)        8 - Assistente IA multiagente
 3 - Desfazer última operação (pilha)   9 - Arquitetura computacional (benchmark)
 4 - Regra booleana e circuito lógico  10 - ANALISAR SUSTENTABILIDADE DA COLÔNIA
 5 - Estruturas de dados               11 - Recarregar base a partir do JSON
 6 - Simulação computacional            0 - Sair
```

A opção 10 executa o fluxo integrado previsto no enunciado: consulta ao banco, regra booleana, alertas na fila de prioridade (gravados em `T_SIFSM_ALERTA`), simulação, previsão por regressão, análise da rede (grafo), recomendações e limitações.

## Exemplos de execução

A saída completa está em `graficos_ou_imagens/evidencia_execucao_demo.txt`. Trecho:

```
[3] Fila de prioridade (heap) – ordem de tratamento:
      P1 CRITICO  COM-01: falha/leitura inválida no sensor
      P1 CRITICO  MED-01: consumo acima do esperado
      P2 ATENCAO  LAB-01: consumo acima do esperado
      P3 ATENCAO  AGR-01: umidade baixa -> liberar irrigação
```
