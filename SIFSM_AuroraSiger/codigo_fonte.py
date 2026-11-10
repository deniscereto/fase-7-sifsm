"""
=====================================================================
 codigo_fonte.py  -  ARQUIVO PRINCIPAL DO SISTEMA
 SIFSM - Sistema Integrado de Futuro Sustentável em Marte
 Colônia Aurora Siger
=====================================================================
Como executar:
    python codigo_fonte.py           -> menu interativo no terminal
    python codigo_fonte.py --demo    -> executa TODAS as funcionalidades em
                                        sequência (sem digitar nada) e salva a
                                        evidência em graficos_ou_imagens/

Módulos do projeto (cada um pode ser executado sozinho):
    banco_dados.py ............ conexão Oracle/SQLite + CRUD + carga do JSON
    regras_logicas.py ......... regras booleanas e tabela verdade
    estruturas_dados.py ....... fila, fila de prioridade, pilha, hash, grafo
    simulacao_computacional.py  simulação energética + integração matemática
    modelo_linear.py .......... regressão linear simples e múltipla
    agentes_ia.py ............. assistente multiagente (triador + especialistas)
    arquitetura_computacional.py benchmark CPU sequencial x vetorizado
"""

import os
import sys

try:                                       # acentos corretos em qualquer terminal
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd

from banco_dados import (BancoAurora, RegistroNaoEncontrado, carregar_auxiliares,
                         TIPOS_MODULO, STATUS_MODULO)
from regras_logicas import (avaliar_leitura, demonstrar_regra, regra_modo_economia,
                            SOC_ECONOMIA)
from estruturas_dados import (FilaSolicitacoes, FilaPrioridadeAlertas, PilhaHistorico,
                              montar_grafo)
import simulacao_computacional as sim
import modelo_linear as ml
import agentes_ia as ia
import arquitetura_computacional as arq

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)
MARGEM = " " * 4
PASTA = os.path.dirname(os.path.abspath(__file__))


# ===================================================================
# Estado global do sistema
# ===================================================================
class SIFSM:
    def __init__(self, interativo=True):
        self.interativo = interativo
        self.banco = BancoAurora()
        self.fila_solicitacoes = FilaSolicitacoes()
        self.alertas = FilaPrioridadeAlertas()
        self.historico = PilhaHistorico()
        self.grafo = None
        self.modelo = None                 # resultado de ml.treinar_modelos
        self.triador = ia.AgenteTriador()
        self.sessao = ia.Sessao(usuario="operador")
        self.contexto = None

    # ---------------- inicialização com tratamento de erros ----------------
    def iniciar(self) -> bool:
        try:
            tipo = self.banco.conectar()
            if self.banco.base_vazia():
                info = self.banco.carregar_json()
                print(f"[INICIO] Base vazia: carregadas {info['modulos']} módulos e {info['leituras']} leituras do JSON.")
        except (ConnectionError, FileNotFoundError, ValueError) as e:
            print(f"[ERRO] Não foi possível iniciar o banco: {e}")
            return False
        else:
            print(f"[INICIO] Conectado ao banco {tipo.upper()}.")
        finally:
            aux = carregar_auxiliares()       # roda com ou sem erro no banco
        self.grafo = montar_grafo(aux["conexoes"])
        for s in sorted(aux["solicitacoes"], key=lambda x: x["id"]):
            self.fila_solicitacoes.enfileirar(s)
        self._montar_contexto()
        return True

    def _montar_contexto(self):
        aprovador = self._aprovar_humano if self.interativo else self._aprovar_demo
        self.contexto = ia.ContextoColonia(self.banco, self.grafo, self.fila_solicitacoes,
                                           self.modelo["multipla"] if self.modelo else None,
                                           aprovador=aprovador)

    @staticmethod
    def _aprovar_humano(texto: str) -> bool:
        resp = input(f"\n{MARGEM}[APROVAÇÃO HUMANA] {texto}\n{MARGEM}Aprovar? (s/n): ")
        return resp.strip().lower() == "s"

    @staticmethod
    def _aprovar_demo(texto: str) -> bool:
        print(f"{MARGEM}[APROVAÇÃO HUMANA - simulada no modo demo] {texto} -> APROVADO")
        return True

    def sol_atual(self) -> int:
        df = self.banco.consultar("SELECT MAX(sol) AS s FROM T_SIFSM_LEITURA")
        return int(df.iloc[0]["s"] or 0)


# ===================================================================
# Entrada de dados com validação (try/except)
# ===================================================================
def ler_int(msg, minimo=None, maximo=None, padrao=None):
    while True:
        valor = input(MARGEM + msg).strip()
        if valor == "" and padrao is not None:
            return padrao
        try:
            n = int(valor)
            if (minimo is not None and n < minimo) or (maximo is not None and n > maximo):
                raise ValueError
        except ValueError:
            faixa = f" entre {minimo} e {maximo}" if minimo is not None and maximo is not None else ""
            print(f"{MARGEM}Valor inválido. Digite um número inteiro{faixa}.")
        else:
            return n


def ler_float(msg, padrao=None):
    while True:
        valor = input(MARGEM + msg).strip().replace(",", ".")
        if valor == "" and padrao is not None:
            return padrao
        try:
            return float(valor)
        except ValueError:
            print(f"{MARGEM}Valor inválido. Digite um número (ex.: 42.5).")


def ler_texto(msg, padrao=None):
    valor = input(MARGEM + msg).strip()
    return padrao if valor == "" and padrao is not None else valor


def pausar(app):
    if app.interativo:
        input(f"\n{MARGEM}Pressione ENTER para continuar...")


def limpar(app):
    if app.interativo:
        os.system("cls" if os.name == "nt" else "clear")


def titulo(txt):
    print("\n" + "=" * 70 + f"\n {txt}\n" + "=" * 70)


# ===================================================================
# 1) CRUD - MÓDULOS
# ===================================================================
def menu_modulos(app: SIFSM):
    while True:
        titulo("MÓDULOS DA COLÔNIA – CRUD")
        print(f"{MARGEM}1 - Cadastrar módulo\n{MARGEM}2 - Listar módulos\n"
              f"{MARGEM}3 - Alterar módulo\n{MARGEM}4 - Excluir módulo\n{MARGEM}0 - Voltar")
        op = ler_int("Escolha -> ", 0, 4)
        if op == 0:
            return
        try:
            if op == 1:
                dados = {"cod_modulo": ler_texto("Código (ex.: HAB-02): "),
                         "nome": ler_texto("Nome: "),
                         "tipo": ler_texto(f"Tipo {TIPOS_MODULO}: "),
                         "critico": ler_int("Crítico? (1=sim, 0=não): ", 0, 1),
                         "status": ler_texto(f"Status {STATUS_MODULO} [ATIVO]: ", "ATIVO"),
                         "consumo_nominal_kwh": ler_float("Consumo nominal (kWh/sol): ")}
                cod = app.banco.cadastrar_modulo(dados)
                app.historico.empilhar("MODULO_CADASTRO", {"cod_modulo": cod})
                print(f"\n{MARGEM}##### Módulo {cod} CADASTRADO #####")
            elif op == 2:
                df = app.banco.listar_modulos()
                print("Nenhum módulo cadastrado." if df.empty else df.to_string(index=False))
            elif op == 3:
                cod = ler_texto("Código do módulo a alterar: ")
                atual = app.banco.buscar_modulo(cod)
                print(f"{MARGEM}Atual: {atual}\n{MARGEM}(ENTER mantém o valor)")
                novos = {"nome": ler_texto(f"Nome [{atual['nome']}]: ", atual["nome"]),
                         "status": ler_texto(f"Status [{atual['status']}]: ", atual["status"]),
                         "consumo_nominal_kwh": ler_float(f"Nominal [{atual['consumo_nominal_kwh']}]: ",
                                                          atual["consumo_nominal_kwh"])}
                antes = app.banco.alterar_modulo(cod, novos)
                app.historico.empilhar("MODULO_ALTERACAO", antes)
                print(f"\n{MARGEM}##### Módulo ALTERADO #####")
            elif op == 4:
                cod = ler_texto("Código do módulo a excluir: ")
                if ler_texto(f"Confirma exclusão de {cod}? (s/n): ").lower() == "s":
                    antes = app.banco.excluir_modulo(cod)
                    app.historico.empilhar("MODULO_EXCLUSAO", antes)
                    print(f"\n{MARGEM}##### Módulo EXCLUÍDO #####")
        except RegistroNaoEncontrado as e:
            print(f"{MARGEM}[NÃO ENCONTRADO] {e}")
        except ValueError as e:
            print(f"{MARGEM}[DADO INVÁLIDO] {e}")
        except Exception as e:                          # erro do banco (PK duplicada etc.)
            print(f"{MARGEM}[ERRO NO BANCO] Operação cancelada: {e}")
        pausar(app)


# ===================================================================
# 2) CRUD - LEITURAS
# ===================================================================
def ler_codigo_modulo(banco, padrao=None) -> str:
    """Pergunta o código do módulo e valida NA HORA se ele existe (try/except)."""
    validos = ", ".join(banco.listar_modulos().cod_modulo)
    while True:
        cod = ler_texto(f"Código do módulo [{padrao or ''}] (ex.: HAB-01): ", padrao)
        try:
            if not cod:
                raise ValueError("o código não pode ficar em branco")
            return banco.buscar_modulo(cod)["cod_modulo"]
        except (RegistroNaoEncontrado, ValueError) as e:
            print(f"{MARGEM}[DADO INVÁLIDO] {str(e).rstrip('.')}. Códigos válidos: {validos}")


def coletar_leitura(banco, padrao: dict | None = None) -> dict:
    p = padrao or {}
    g = lambda k, d=None: p.get(k, d)
    return {"cod_modulo": ler_codigo_modulo(banco, g("cod_modulo")),
            "sol": ler_int(f"Sol [{g('sol', '')}]: ", 1, padrao=g("sol")),
            "ocupacao": ler_int(f"Ocupação (tripulantes) [{g('ocupacao', 0)}]: ", 0, padrao=g("ocupacao", 0)),
            "temp_externa_c": ler_float(f"Temperatura externa °C [{g('temp_externa_c', -60.0)}]: ", g("temp_externa_c", -60.0)),
            "temp_interna_c": ler_float(f"Temperatura interna °C [{g('temp_interna_c', 21.0)}]: ", g("temp_interna_c", 21.0)),
            "luminosidade_lux": ler_float(f"Luminosidade lux [{g('luminosidade_lux', 300.0)}]: ", g("luminosidade_lux", 300.0)),
            "umidade_pct": ler_float(f"Umidade % [{g('umidade_pct', 45.0)}]: ", g("umidade_pct", 45.0)),
            "opacidade_poeira": ler_float(f"Opacidade da poeira (tau) [{g('opacidade_poeira', 0.5)}]: ", g("opacidade_poeira", 0.5)),
            "consumo_kwh": ler_float(f"Consumo kWh [{g('consumo_kwh', '')}]: ", g("consumo_kwh")),
            "falha_sensor": ler_int(f"Falha no sensor? (0/1) [{g('falha_sensor', 0)}]: ", 0, 1, g("falha_sensor", 0))}


def menu_leituras(app: SIFSM):
    while True:
        titulo("LEITURAS DE SENSORES – CRUD")
        print(f"{MARGEM}1 - Cadastrar leitura\n{MARGEM}2 - Listar leituras (com filtro)\n"
              f"{MARGEM}3 - Alterar leitura\n{MARGEM}4 - Excluir leitura\n{MARGEM}0 - Voltar")
        op = ler_int("Escolha -> ", 0, 4)
        if op == 0:
            return
        try:
            if op == 1:
                dados = coletar_leitura(app.banco, {"sol": app.sol_atual() + 1})
                dados["presenca"] = 1 if dados["ocupacao"] > 0 else 0
                novo = app.banco.cadastrar_leitura(dados)
                app.historico.empilhar("LEITURA_CADASTRO", {"id_leitura": novo})
                print(f"\n{MARGEM}##### Leitura {novo} CADASTRADA #####")
                modulo = app.banco.buscar_modulo(dados["cod_modulo"])
                aval = avaliar_leitura(app.banco.buscar_leitura(novo), modulo)
                print(f"{MARGEM}Regra booleana aplicada: A={aval['A_consumo_alto']} B={aval['B_critico']} "
                      f"C={aval['C_falha']} -> S={aval['S_alerta']} ({aval['nivel']}: {aval['motivos']})")
            elif op == 2:
                cod = ler_texto("Filtrar por módulo (ENTER = todos): ", "")
                sol = ler_int("Filtrar por sol (0 = todos): ", 0, padrao=0)
                df = app.banco.listar_leituras(cod or None, sol or None)
                cols = ["id_leitura", "cod_modulo", "sol", "ocupacao", "temp_externa_c", "temp_interna_c",
                        "umidade_pct", "opacidade_poeira", "consumo_kwh", "falha_sensor"]
                if df.empty:
                    print(f"{MARGEM}Nenhuma leitura encontrada.")
                else:
                    print(df[cols].tail(40).to_string(index=False))
                    print(f"{MARGEM}{len(df)} leitura(s) encontradas (mostrando até as 40 últimas).")
            elif op == 3:
                id_l = ler_int("ID da leitura a alterar: ", 1)
                atual = app.banco.buscar_leitura(id_l)
                print(f"{MARGEM}(ENTER mantém o valor atual)")
                novos = coletar_leitura(app.banco, atual)
                antes = app.banco.alterar_leitura(id_l, novos)
                app.historico.empilhar("LEITURA_ALTERACAO", antes)
                print(f"\n{MARGEM}##### Leitura {id_l} ALTERADA #####")
                aval = avaliar_leitura(app.banco.buscar_leitura(id_l), app.banco.buscar_modulo(novos["cod_modulo"]))
                print(f"{MARGEM}Regra booleana reaplicada: A={aval['A_consumo_alto']} B={aval['B_critico']} "
                      f"C={aval['C_falha']} -> S={aval['S_alerta']} ({aval['nivel']}: {aval['motivos']})")
            elif op == 4:
                id_l = ler_int("ID da leitura a excluir: ", 1)
                if ler_texto(f"Confirma exclusão da leitura {id_l}? (s/n): ").lower() == "s":
                    antes = app.banco.excluir_leitura(id_l)
                    app.historico.empilhar("LEITURA_EXCLUSAO", antes)
                    print(f"\n{MARGEM}##### Leitura EXCLUÍDA (pode ser desfeita na opção 3 do menu) #####")
        except RegistroNaoEncontrado as e:
            print(f"{MARGEM}[NÃO ENCONTRADO] {e}")
        except (ValueError, TypeError) as e:
            print(f"{MARGEM}[DADO INVÁLIDO] {e}")
        except Exception as e:
            print(f"{MARGEM}[ERRO NO BANCO] Operação cancelada: {e}")
        pausar(app)


# ===================================================================
# 3) DESFAZER (PILHA)
# ===================================================================
def desfazer(app: SIFSM):
    titulo("DESFAZER ÚLTIMA OPERAÇÃO (PILHA LIFO)")
    op = app.historico.desempilhar()
    if op is None:
        print(f"{MARGEM}Histórico vazio: nada para desfazer.")
        return
    tipo, d = op["operacao"], op["dados"]
    try:
        if tipo == "LEITURA_CADASTRO":
            app.banco.excluir_leitura(d["id_leitura"])
        elif tipo == "LEITURA_ALTERACAO":
            app.banco.alterar_leitura(d["id_leitura"], d)
        elif tipo == "LEITURA_EXCLUSAO":
            app.banco.restaurar_leitura(d)
        elif tipo == "MODULO_CADASTRO":
            app.banco.excluir_modulo(d["cod_modulo"])
        elif tipo == "MODULO_ALTERACAO":
            app.banco.alterar_modulo(d["cod_modulo"], d)
        elif tipo == "MODULO_EXCLUSAO":
            app.banco.cadastrar_modulo(d)
    except Exception as e:
        print(f"{MARGEM}[ERRO] Não foi possível desfazer {tipo}: {e}")
        app.historico.empilhar(tipo, d)          # devolve à pilha
    else:
        print(f"{MARGEM}Operação {tipo} desfeita com sucesso. Restam {len(app.historico)} no histórico.")


# ===================================================================
# 4) REGRA BOOLEANA E CIRCUITO
# ===================================================================
def menu_regra(app: SIFSM):
    titulo("REGRA BOOLEANA E CIRCUITO LÓGICO")
    demonstrar_regra()
    sol = app.sol_atual()
    df = app.banco.dataframe_analitico()
    df = df[df.sol == sol]
    print(f"\nAplicação da regra nas leituras do sol {sol}:")
    linhas = [avaliar_leitura(r, r) for r in df.to_dict("records")]
    print(pd.DataFrame(linhas)[["cod_modulo", "A_consumo_alto", "B_critico", "C_falha", "S_alerta",
                                "irrigacao", "iluminacao", "nivel", "motivos"]].to_string(index=False))
    print(f"\nCircuito: circuito_logico.png / circuito_logico.pdf | Arduino: arduino_sifsm.ino | "
          f"Tinkercad: link_tinkercad.txt")
    print("Portas: A e B entram numa porta AND (74HC08); a saída e C entram numa OR (74HC32) -> LED/buzzer.")


# ===================================================================
# 5) ESTRUTURAS DE DADOS
# ===================================================================
def menu_estruturas(app: SIFSM):
    while True:
        titulo("ESTRUTURAS DE DADOS APLICADAS")
        print(f"{MARGEM}1 - Fila de solicitações da tripulação (FIFO)\n"
              f"{MARGEM}2 - Atender próxima solicitação\n"
              f"{MARGEM}3 - Busca rápida por código (tabela hash)\n"
              f"{MARGEM}4 - Rede da colônia: BFS, rota e impacto de falha (grafo)\n"
              f"{MARGEM}5 - Histórico de operações (pilha)\n{MARGEM}0 - Voltar")
        op = ler_int("Escolha -> ", 0, 5)
        if op == 0:
            return
        if op == 1:
            mostrar_fila(app)
        elif op == 2:
            s = app.fila_solicitacoes.atender()
            print(f"{MARGEM}Atendida: {s}" if s else f"{MARGEM}Fila vazia.")
        elif op == 3:
            cod = ler_texto("Código do módulo ou sensor (ex.: SNS-MED-01): ")
            print(MARGEM + ia.ferramenta_consultar_modulo(app.contexto, cod))
            print(f"{MARGEM}Tabela hash: {app.contexto.indice.ocupacao()}")
        elif op == 4:
            mostrar_grafo(app, ler_texto("Módulo de destino/falha [MED-01]: ", "MED-01").upper())
        elif op == 5:
            itens = app.historico.listar()
            print(f"{MARGEM}Pilha vazia." if not itens else
                  "\n".join(f"{MARGEM}{i+1}. {o['operacao']}" for i, o in enumerate(itens)))
        pausar(app)


def mostrar_fila(app):
    print(f"{MARGEM}{len(app.fila_solicitacoes)} solicitação(ões) na fila (ordem de atendimento):")
    for i, s in enumerate(app.fila_solicitacoes.listar(), 1):
        print(f"{MARGEM}{i}. #{s['id']} [{s['cod_modulo']}] prioridade {s['prioridade']} – {s['descricao']}")


def mostrar_grafo(app, destino="MED-01"):
    dist = app.grafo.bfs("ENE-01")
    print(f"{MARGEM}BFS a partir da Central de Energia (saltos): " +
          ", ".join(f"{k}={v}" for k, v in dist.items()))
    rota = app.grafo.caminho("ENE-01", destino)
    print(f"{MARGEM}Menor rota ENE-01 -> {destino}: {' -> '.join(rota) if rota else 'sem rota'}")
    print(f"{MARGEM}Análise de resiliência (DFS sem o nó com falha):")
    for no, isolados in app.grafo.pontos_criticos().items():
        print(f"{MARGEM}  se {no} falhar -> isolados: {', '.join(isolados) if isolados else 'nenhum'}")


# ===================================================================
# 6, 7, 8, 9) SIMULAÇÃO, MODELO, IA, ARQUITETURA
# ===================================================================
def consumo_medio_normal(app):
    df = app.banco.dataframe_analitico()
    df = df[(df.opacidade_poeira < sim.TAU_TEMPESTADE) & (df.falha_sensor == 0)]
    return df.groupby("cod_modulo").consumo_kwh.mean().to_dict(), set(df[df.critico == 1].cod_modulo)


def menu_simulacao(app: SIFSM):
    titulo("SIMULAÇÃO COMPUTACIONAL E INTEGRAÇÃO MATEMÁTICA")
    consumo, criticos = consumo_medio_normal(app)
    sim.executar_simulacao(consumo, criticos)
    print("\nInterpretação: a área sob a curva de potência é a energia; o SoC é a integral do saldo"
          "\n(geração − consumo) dividida pela capacidade. Sem gestão, a tempestade esgota a bateria;"
          "\ncom a regra de modo economia a colônia atravessa a tempestade sem faltar energia.")


def menu_modelo(app: SIFSM):
    titulo("MODELAGEM LINEAR – PREVISÃO DE CONSUMO")
    app.modelo = ml.treinar_modelos(app.banco.dataframe_analitico())
    app._montar_contexto()                       # agentes passam a usar o modelo treinado
    print("\n" + ia.ferramenta_prever(app.contexto))


def menu_ia(app: SIFSM, perguntas=None):
    titulo("ASSISTENTE IA MULTIAGENTE (triador + especialistas)")
    if app.modelo is None:
        app.modelo = ml.treinar_modelos(app.banco.dataframe_analitico(), graficos=False, verbose=False)
        app._montar_contexto()
    print("Agentes: Triador -> Energia | Ambiental | Manutenção | Dados. Guardrails ativos.")
    if perguntas:
        for i, p in enumerate(perguntas):
            print(f"\nOPERADOR: {p}")
            print(app.triador.conversar(p, app.contexto, app.sessao, mostrar_trace=i in (4, 6)))
        return
    print("Digite sua pergunta (ou 'sair'). Ex.: 'Como está a bateria?', 'Há falhas nos sensores?'")
    while True:
        msg = input("\nOPERADOR> ").strip()
        if msg.lower() in ("sair", "0", ""):
            return
        print(app.triador.conversar(msg, app.contexto, app.sessao))


# ===================================================================
# 10) ANÁLISE INTEGRADA DE SUSTENTABILIDADE
# ===================================================================
def analisar_sustentabilidade(app: SIFSM):
    titulo("ANÁLISE INTEGRADA DE SUSTENTABILIDADE DA COLÔNIA")
    sol = app.sol_atual()
    df = app.banco.dataframe_analitico()
    ult = df[df.sol == sol]

    # 1. Banco de dados
    print(f"[1] Banco: {len(ult)} leituras do sol {sol} | consumo total {ult.consumo_kwh.sum():.1f} kWh | "
          f"opacidade média tau={ult.opacidade_poeira.mean():.2f}")

    # 2. Regra booleana + 3. fila de prioridade + persistência dos alertas
    app.banco.limpar_alertas()
    app.alertas = FilaPrioridadeAlertas()
    for r in ult.to_dict("records"):
        a = avaliar_leitura(r, r)
        if a["nivel"] != "NORMAL":
            app.alertas.inserir(a["prioridade"], a)
            app.banco.registrar_alerta(a["cod_modulo"], sol, a["nivel"], a["prioridade"], a["motivos"])
    print(f"[2] Regra S = A·B + C aplicada: {len(app.alertas)} alerta(s) gravados em T_SIFSM_ALERTA")
    print("[3] Fila de prioridade (heap) – ordem de tratamento:")
    for a in app.alertas.em_ordem():
        print(f"      P{a['prioridade']} {a['nivel']:<8} {a['cod_modulo']}: {a['motivos']}")

    # 4. Simulação: projeção da bateria com o tau atual e com hipótese de tempestade
    consumo, criticos = consumo_medio_normal(app)
    soc_atual = 0.60                                             # informado pelo BMS (simulado)
    proj = sim.projetar_soc(consumo, criticos, soc_atual, float(ult.opacidade_poeira.mean()))
    proj_t = sim.projetar_soc(consumo, criticos, soc_atual, 3.0)
    print(f"[4] Simulação (3 sols, SoC atual {soc_atual:.0%}): condição atual -> SoC mín "
          f"{proj['sem_gestao']['soc_min']:.0%}; se vier tempestade -> SoC mín "
          f"{proj_t['sem_gestao']['soc_min']:.0%} sem gestão / {proj_t['com_gestao']['soc_min']:.0%} com gestão "
          f"(energia não suprida {proj_t['sem_gestao']['e_nao_suprida_kwh']:.0f} -> "
          f"{proj_t['com_gestao']['e_nao_suprida_kwh']:.0f} kWh)")

    # 5. Modelo linear
    if app.modelo is None:
        app.modelo = ml.treinar_modelos(df, graficos=False, verbose=False)
        app._montar_contexto()
    print(f"[5] {ia.ferramenta_prever(app.contexto)}")
    print(f"    (modelo com R² de teste = {app.modelo['met_teste']['R2']:.3f}, "
          f"erro médio {app.modelo['met_teste']['MAE']:.2f} kWh)")

    # 6. Grafo: resiliência da rede
    pontos = {n: iso for n, iso in app.grafo.pontos_criticos().items() if iso and n != "ENE-01"}
    folhas = sorted(n for n, viz in app.grafo.adj.items() if len(viz) == 1)
    print(f"[6] Rede (grafo): ENE-01 é a única fonte (ponto único de falha); outros nós críticos: "
          f"{', '.join(pontos) if pontos else 'nenhum (rotas redundantes)'}; "
          f"módulos com uma só ligação: {', '.join(folhas) or 'nenhum'}")

    # 7. Recomendações (regras + critérios de sustentabilidade e responsabilidade)
    print("\n[7] RECOMENDAÇÕES TÉCNICAS (sujeitas à validação humana do operador de turno):")
    recs = []
    for a in app.alertas.em_ordem():
        if a["C_falha"]:
            recs.append(f"Abrir chamado P1 para o sensor de {a['cod_modulo']} e descartar a leitura das análises (POP-03).")
        elif a["S_alerta"]:
            recs.append(f"Inspecionar {a['cod_modulo']}: consumo acima do esperado em módulo crítico – "
                        "verificar equipamentos ociosos antes de qualquer corte (POP-06).")
        elif a["A_consumo_alto"]:
            recs.append(f"{a['cod_modulo']} (não crítico) com consumo alto: candidato a redução no modo economia.")
        if a["irrigacao"]:
            recs.append(f"Liberar irrigação em {a['cod_modulo']} (umidade baixa, sensor íntegro – POP-04).")
    soc_baixo = proj_t["sem_gestao"]["soc_min"] < SOC_ECONOMIA
    desligaveis = sorted(m for m in consumo if regra_modo_economia(soc_baixo, True, m in criticos))
    recs.append(f"Plano de contingência para tempestade: ativar modo economia desligando {', '.join(desligaveis)} "
                f"(regra (SOC_BAIXO OR TEMPESTADE) AND NOT CRITICO); módulos críticos apenas reduzidos em 15%.")
    recs.append("Resiliência: ENE-01 é ponto único de falha – instalar baterias de reserva distribuídas em "
                "HAB-01 e MED-01" + (f" e criar segunda ligação para {', '.join(folhas)}" if folhas else "") + ".")
    recs.append("Privacidade: relatórios usam dados agregados por módulo; nenhum dado individual da tripulação é exposto.")
    for i, r in enumerate(dict.fromkeys(recs), 1):
        print(f"    {i}. {r}")

    print("\n[8] LIMITAÇÕES: dados simulados (30 sols); modelo linear não capta efeitos não lineares nem"
          "\n    falhas súbitas; simulação sem degradação da bateria; agentes por regras (sem LLM) e"
          "\n    decisões finais sempre do operador humano.")


# ===================================================================
# Menu principal
# ===================================================================
def menu_principal(app: SIFSM):
    while True:
        limpar(app)
        print("=" * 70)
        print("  SIFSM – Sistema Integrado de Futuro Sustentável em Marte")
        print(f"  Colônia Aurora Siger | banco: {app.banco.tipo.upper()} | sol atual: {app.sol_atual()}")
        print("=" * 70)
        print("""
     1 - Módulos da colônia (CRUD)
     2 - Leituras de sensores (CRUD)
     3 - Desfazer última operação (pilha)
     4 - Regra booleana e circuito lógico
     5 - Estruturas de dados (fila, hash, grafo)
     6 - Simulação computacional (energia + integração)
     7 - Modelo linear (previsão de consumo)
     8 - Assistente IA multiagente
     9 - Arquitetura computacional (benchmark)
    10 - ANALISAR SUSTENTABILIDADE DA COLÔNIA
    11 - Recarregar base a partir do JSON
     0 - Sair""")
        op = ler_int("Escolha -> ", 0, 11)
        if op == 0:
            print(f"{MARGEM}Encerrando o SIFSM. Até o próximo sol!")
            return
        if op == 1:
            menu_modulos(app); continue
        if op == 2:
            menu_leituras(app); continue
        if op == 5:
            menu_estruturas(app); continue
        try:
            {3: desfazer, 4: menu_regra, 6: menu_simulacao, 7: menu_modelo, 8: menu_ia,
             9: lambda a: (titulo("ARQUITETURA COMPUTACIONAL"), arq.executar()),
             10: analisar_sustentabilidade, 11: recarregar}[op](app)
        except Exception as e:                  # nenhuma falha derruba o menu
            print(f"\n{MARGEM}[ERRO INESPERADO] {type(e).__name__}: {e}")
        pausar(app)


def recarregar(app: SIFSM):
    try:
        info = app.banco.carregar_json()
    except (FileNotFoundError, ValueError) as e:
        print(f"{MARGEM}[ERRO] {e}")
    else:
        print(f"{MARGEM}Base recarregada: {info['modulos']} módulos e {info['leituras']} leituras.")
        app.historico = PilhaHistorico()
        app.modelo = None
        app._montar_contexto()


# ===================================================================
# Modo demonstração (executa tudo sem interação)
# ===================================================================
class Tee:
    def __init__(self, *saidas):
        self.saidas = saidas

    def write(self, txt):
        for s in self.saidas:
            s.write(txt)

    def flush(self):
        for s in self.saidas:
            s.flush()


def modo_demo():
    os.makedirs(os.path.join(PASTA, "graficos_ou_imagens"), exist_ok=True)
    arq_log = os.path.join(PASTA, "graficos_ou_imagens", "evidencia_execucao_demo.txt")
    with open(arq_log, "w", encoding="utf-8") as log:
        original = sys.stdout
        sys.stdout = Tee(original, log)
        try:
            executar_demo()
        finally:
            sys.stdout = original
    print(f"\nEvidência completa salva em {os.path.relpath(arq_log)}")


def executar_demo():
    app = SIFSM(interativo=False)
    if not app.iniciar():
        return
    recarregar(app)

    titulo("CRUD DE LEITURAS E MÓDULOS + PILHA (DESFAZER)")
    novo = app.banco.cadastrar_leitura({"cod_modulo": "HAB-01", "sol": 31, "ocupacao": 11,
                                        "temp_externa_c": -66.0, "temp_interna_c": 21.2,
                                        "luminosidade_lux": 410, "umidade_pct": 42,
                                        "opacidade_poeira": 0.5, "consumo_kwh": 64.8})
    app.historico.empilhar("LEITURA_CADASTRO", {"id_leitura": novo})
    print(f"CADASTRAR -> leitura {novo} criada")
    print("LISTAR (sol 31):\n" + app.banco.listar_leituras(sol=31)[
        ["id_leitura", "cod_modulo", "sol", "ocupacao", "consumo_kwh"]].to_string(index=False))
    antes = app.banco.alterar_leitura(novo, {"consumo_kwh": 88.0})
    app.historico.empilhar("LEITURA_ALTERACAO", antes)
    print(f"ALTERAR -> consumo {antes['consumo_kwh']} -> {app.banco.buscar_leitura(novo)['consumo_kwh']} kWh")
    a = avaliar_leitura(app.banco.buscar_leitura(novo), app.banco.buscar_modulo("HAB-01"))
    print(f"Regra na leitura alterada: A={a['A_consumo_alto']} B={a['B_critico']} C={a['C_falha']} -> "
          f"S={a['S_alerta']} ({a['nivel']})")
    desfazer(app)
    print(f"Após desfazer: consumo = {app.banco.buscar_leitura(novo)['consumo_kwh']} kWh")
    antes = app.banco.excluir_leitura(novo)
    app.historico.empilhar("LEITURA_EXCLUSAO", antes)
    print(f"EXCLUIR -> leitura {novo} removida")
    desfazer(app)
    print(f"Após desfazer: leitura {novo} existe? {not app.banco.listar_leituras(sol=31).empty}")
    app.banco.excluir_leitura(novo)
    print("CRUD de MÓDULO:")
    app.banco.cadastrar_modulo({"cod_modulo": "REC-01", "nome": "Reciclagem de Água", "tipo": "ARMAZENAMENTO",
                                "critico": 0, "consumo_nominal_kwh": 14})
    app.banco.alterar_modulo("REC-01", {"status": "MANUTENCAO"})
    print(app.banco.listar_modulos().to_string(index=False))
    app.banco.excluir_modulo("REC-01")
    print("REC-01 excluído.")

    titulo("TRATAMENTO DE ERROS (try / except / else / finally)")
    testes = [
        ("Módulo inexistente", lambda: app.banco.cadastrar_leitura({"cod_modulo": "XYZ-99", "sol": 1, "consumo_kwh": 10})),
        ("Umidade 150%", lambda: app.banco.cadastrar_leitura({"cod_modulo": "AGR-01", "sol": 1, "consumo_kwh": 10, "umidade_pct": 150})),
        ("Consumo com texto", lambda: app.banco.cadastrar_leitura({"cod_modulo": "AGR-01", "sol": 1, "consumo_kwh": "muito"})),
        ("Tipo de módulo inválido", lambda: app.banco.cadastrar_modulo({"cod_modulo": "X-01", "nome": "X", "tipo": "PISCINA", "consumo_nominal_kwh": 5})),
        ("Código duplicado (PK)", lambda: app.banco.cadastrar_modulo({"cod_modulo": "HAB-01", "nome": "Dup", "tipo": "HABITACAO", "consumo_nominal_kwh": 5})),
        ("Excluir módulo com leituras (FK)", lambda: app.banco.excluir_modulo("HAB-01")),
        ("Buscar leitura inexistente", lambda: app.banco.buscar_leitura(99999)),
        ("Arquivo JSON ausente", lambda: app.banco.carregar_json("nao_existe.json")),
    ]
    for nome, f in testes:
        try:
            f()
        except RegistroNaoEncontrado as e:
            print(f"  ✔ {nome:<34} -> RegistroNaoEncontrado: {e}")
        except (ValueError, TypeError) as e:
            print(f"  ✔ {nome:<34} -> {type(e).__name__}: {e}")
        except FileNotFoundError as e:
            print(f"  ✔ {nome:<34} -> FileNotFoundError: {e}")
        except Exception as e:
            print(f"  ✔ {nome:<34} -> erro do banco tratado ({type(e).__name__}): {e}")
        else:
            print(f"  ✘ {nome}: deveria ter falhado!")
        finally:
            pass                                    # a aplicação segue rodando

    menu_regra(app)
    titulo("ESTRUTURAS DE DADOS APLICADAS")
    mostrar_fila(app)
    print(f"Atendendo a primeira (FIFO): {app.fila_solicitacoes.atender()['descricao']}")
    print(ia.ferramenta_consultar_modulo(app.contexto, "SNS-MED-01"), "|", app.contexto.indice.ocupacao())
    mostrar_grafo(app, "MED-01")
    print("Pilha de histórico (topo primeiro):", [o["operacao"] for o in app.historico.listar()])
    menu_simulacao(app)
    menu_modelo(app)
    menu_ia(app, ia.PERGUNTAS_DEMO)
    titulo("ARQUITETURA COMPUTACIONAL")
    arq.executar()
    analisar_sustentabilidade(app)
    app.banco.fechar()


if __name__ == "__main__":
    if "--demo" in sys.argv:
        modo_demo()
    else:
        sistema = SIFSM(interativo=True)
        if sistema.iniciar():
            try:
                menu_principal(sistema)
            except (KeyboardInterrupt, EOFError):
                print("\nExecução interrompida pelo usuário.")
            finally:
                sistema.banco.fechar()
