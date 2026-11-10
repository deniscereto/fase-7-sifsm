"""
regras_logicas.py
---------------------------------------------------------------
Regras de decisão booleanas do SIFSM.

REGRA PRINCIPAL (a mesma implementada no circuito / Tinkercad):

    A = consumo ALTO   (consumo > consumo esperado + folga de 15% do nominal)
    B = módulo CRÍTICO (suporte à vida: habitação, estufa, médico, ...)
    C = FALHA no sensor (leitura inválida ou sensor reportando defeito)

    ALERTA_CRITICO  S = (A AND B) OR C        ->  S = A·B + C

Regras auxiliares:
    IRRIGACAO  = MODULO_AGRICOLA_ATIVO AND UMIDADE_BAIXA AND NOT FALHA
    ILUMINACAO = PRESENCA AND LUMINOSIDADE_BAIXA AND NOT FALHA
    DESLIGAR_CARGA = (SOC_BAIXO OR TEMPESTADE) AND NOT CRITICO   (modo economia)
"""

from itertools import product

# Limiares (parâmetros ajustáveis da colônia)
TOLERANCIA_CONSUMO = 0.15     # 15% do nominal acima do consumo esperado...
TOLERANCIA_MIN_KWH = 5.0      # ...com folga mínima de 5 kWh (evita alarme falso)
UMIDADE_MINIMA = 55.0         # % - abaixo disso a estufa precisa de irrigação
LUX_MINIMO = 200.0            # lux - abaixo disso, ambiente ocupado precisa de luz
SOC_ECONOMIA = 0.40             # 40% - abaixo disso entra o modo economia
TEMP_INTERNA_VALIDA = (5.0, 35.0)


# ---------------------------------------------------------------
# Funções booleanas puras (uma por regra) -> fáceis de testar
# ---------------------------------------------------------------
def regra_alerta_critico(a: bool, b: bool, c: bool) -> bool:
    """S = (A AND B) OR C"""
    return (a and b) or c


def regra_irrigacao(agricola_ativo: bool, umidade_baixa: bool, falha: bool) -> bool:
    return agricola_ativo and umidade_baixa and not falha


def regra_iluminacao(presenca: bool, lux_baixo: bool, falha: bool) -> bool:
    return presenca and lux_baixo and not falha


def regra_modo_economia(soc_baixo: bool, tempestade: bool, critico: bool) -> bool:
    """Desligar esta carga? (SOC_BAIXO OR TEMPESTADE) AND NOT CRITICO.
    Módulo crítico (suporte à vida) nunca é desligado - apenas reduzido em 15%."""
    return (soc_baixo or tempestade) and not critico


# ---------------------------------------------------------------
# Tabela verdade genérica
# ---------------------------------------------------------------
def tabela_verdade(funcao, nomes: list[str]) -> list[tuple]:
    linhas = []
    for valores in product([False, True], repeat=len(nomes)):
        linhas.append((*[int(v) for v in valores], int(funcao(*valores))))
    return linhas


def imprimir_tabela_verdade(funcao, nomes: list[str], saida: str):
    cab = " | ".join(f"{n:^3}" for n in nomes) + f" || {saida}"
    print(cab)
    print("-" * len(cab))
    for linha in tabela_verdade(funcao, nomes):
        print(" | ".join(f"{v:^3}" for v in linha[:-1]) + f" || {linha[-1]:^{len(saida)}}")


# ---------------------------------------------------------------
# Aplicação das regras em uma leitura real do banco
# ---------------------------------------------------------------
def sensor_com_falha(leitura: dict) -> bool:
    """C = sensor marcou falha OU devolveu valor fisicamente impossível."""
    tmin, tmax = TEMP_INTERNA_VALIDA
    return bool(int(leitura.get("falha_sensor", 0))) or not (tmin <= float(leitura["temp_interna_c"]) <= tmax)


def consumo_esperado(modulo: dict, leitura: dict) -> float:
    """Consumo de referência: nominal + 1,6 kWh/tripulante + aquecimento extra
    quando a temperatura externa fica abaixo de -55 °C (0,45 kWh por grau)."""
    frio = max(0.0, -55.0 - float(leitura["temp_externa_c"]))
    return float(modulo["consumo_nominal_kwh"]) + 1.6 * int(leitura["ocupacao"]) + 0.45 * frio


def limite_consumo(modulo: dict, leitura: dict) -> float:
    folga = max(TOLERANCIA_CONSUMO * float(modulo["consumo_nominal_kwh"]), TOLERANCIA_MIN_KWH)
    return consumo_esperado(modulo, leitura) + folga


def avaliar_leitura(leitura: dict, modulo: dict) -> dict:
    """Aplica todas as regras e devolve as variáveis booleanas + classificação."""
    a = float(leitura["consumo_kwh"]) > limite_consumo(modulo, leitura)
    b = bool(int(modulo["critico"]))
    c = sensor_com_falha(leitura)
    s = regra_alerta_critico(a, b, c)

    irrig = regra_irrigacao(modulo["tipo"] == "AGRICULTURA" and modulo["status"] == "ATIVO",
                            float(leitura["umidade_pct"]) < UMIDADE_MINIMA, c)
    luz = regra_iluminacao(bool(int(leitura["presenca"])),
                           float(leitura["luminosidade_lux"]) < LUX_MINIMO, c)

    if s:
        nivel, prioridade = "CRITICO", 1
    elif a:                                   # consumo alto em módulo não crítico
        nivel, prioridade = "ATENCAO", 2
    elif irrig or luz:
        nivel, prioridade = "ATENCAO", 3
    else:
        nivel, prioridade = "NORMAL", 9

    motivos = []
    if a: motivos.append("consumo acima do esperado")
    if c: motivos.append("falha/leitura inválida no sensor")
    if irrig: motivos.append("umidade baixa -> liberar irrigação")
    if luz: motivos.append("presença com pouca luz -> acender iluminação")

    return {"cod_modulo": modulo["cod_modulo"], "sol": int(leitura["sol"]),
            "A_consumo_alto": int(a), "B_critico": int(b), "C_falha": int(c),
            "S_alerta": int(s), "irrigacao": int(irrig), "iluminacao": int(luz),
            "nivel": nivel, "prioridade": prioridade,
            "motivos": "; ".join(motivos) if motivos else "operação normal"}


EXPRESSAO_PRINCIPAL = "S = (A AND B) OR C   |   S = A·B + C"
DESCRICAO_VARIAVEIS = {
    "A": "Consumo alto (consumo > consumo esperado + folga de 15% do nominal, mín. 5 kWh)",
    "B": "Módulo crítico (suporte à vida)",
    "C": f"Falha no sensor (flag de falha ou temperatura interna fora de {TEMP_INTERNA_VALIDA} °C)",
    "S": "Acionar ALERTA CRÍTICO (LED vermelho + buzzer no circuito)",
}


def demonstrar_regra():
    print("\nREGRA BOOLEANA PRINCIPAL")
    print(EXPRESSAO_PRINCIPAL)
    for k, v in DESCRICAO_VARIAVEIS.items():
        print(f"  {k}: {v}")
    print()
    imprimir_tabela_verdade(regra_alerta_critico, ["A", "B", "C"], "S")
    print("\nRegra auxiliar: IRRIGACAO = AGRICOLA_ATIVO AND UMIDADE_BAIXA AND NOT FALHA")
    imprimir_tabela_verdade(regra_irrigacao, ["AG", "UB", "F"], "IRR")


if __name__ == "__main__":
    demonstrar_regra()
