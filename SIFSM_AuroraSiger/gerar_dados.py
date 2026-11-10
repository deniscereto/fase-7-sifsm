"""
gerar_dados.py
---------------------------------------------------------------
Gera a base de dados SIMULADA da colônia Aurora Siger
(dados_aurora_siger.json).

Não é necessário executar este arquivo para usar o sistema: o JSON
já acompanha a entrega. Ele foi mantido para dar transparência sobre
COMO os dados foram criados (sementes fixas = resultados reproduzíveis).

Modelo usado para gerar o consumo de cada módulo (kWh por sol):
    consumo = nominal + 1,6 * ocupacao + 0,45 * (-55 - temp_externa) + ruído
Ou seja: mais tripulantes e mais frio lá fora => mais consumo.
Esse "modelo verdadeiro" é o que a regressão linear tenta redescobrir.
"""

import json
import numpy as np

SEMENTE = 2026
NUM_SOLS = 30          # 1 sol = 1 dia marciano (~24h39min)

# ---------------------------------------------------------------
# Módulos da colônia
# critico = 1 -> módulo essencial à vida (nunca pode ser desligado)
# ---------------------------------------------------------------
MODULOS = [
    {"cod_modulo": "HAB-01", "nome": "Habitação Alfa",          "tipo": "HABITACAO",      "critico": 1, "status": "ATIVO", "consumo_nominal_kwh": 42.0, "ocup_min": 8, "ocup_max": 12},
    {"cod_modulo": "AGR-01", "nome": "Estufa Agrícola",         "tipo": "AGRICULTURA",    "critico": 1, "status": "ATIVO", "consumo_nominal_kwh": 55.0, "ocup_min": 2, "ocup_max": 4},
    {"cod_modulo": "LAB-01", "nome": "Laboratório de Pesquisa", "tipo": "LABORATORIO",    "critico": 0, "status": "ATIVO", "consumo_nominal_kwh": 30.0, "ocup_min": 1, "ocup_max": 4},
    {"cod_modulo": "COM-01", "nome": "Central de Comunicação",  "tipo": "COMUNICACAO",    "critico": 1, "status": "ATIVO", "consumo_nominal_kwh": 18.0, "ocup_min": 1, "ocup_max": 2},
    {"cod_modulo": "MED-01", "nome": "Suporte Médico",          "tipo": "SUPORTE_MEDICO", "critico": 1, "status": "ATIVO", "consumo_nominal_kwh": 22.0, "ocup_min": 0, "ocup_max": 2},
    {"cod_modulo": "ARM-01", "nome": "Armazenamento",           "tipo": "ARMAZENAMENTO",  "critico": 0, "status": "ATIVO", "consumo_nominal_kwh": 12.0, "ocup_min": 0, "ocup_max": 1},
    {"cod_modulo": "ENE-01", "nome": "Central de Energia",      "tipo": "ENERGIA",        "critico": 1, "status": "ATIVO", "consumo_nominal_kwh": 15.0, "ocup_min": 0, "ocup_max": 1},
]

# Conexões físicas (rede de energia/dados) entre módulos -> GRAFO
CONEXOES = [
    ["ENE-01", "HAB-01"], ["ENE-01", "AGR-01"], ["ENE-01", "ARM-01"],
    ["HAB-01", "MED-01"], ["HAB-01", "COM-01"], ["AGR-01", "LAB-01"],
    ["LAB-01", "MED-01"], ["COM-01", "LAB-01"],
]

# Solicitações da tripulação (anonimizadas: só o papel, nunca o nome) -> FILA
SOLICITACOES = [
    {"id": 1, "solicitante": "Tripulante T-03 (engenharia)", "cod_modulo": "AGR-01", "prioridade": 2, "descricao": "Verificar bomba de irrigação da bancada 4"},
    {"id": 2, "solicitante": "Tripulante T-07 (médico)",     "cod_modulo": "MED-01", "prioridade": 1, "descricao": "Oscilação de energia no monitor de sinais vitais"},
    {"id": 3, "solicitante": "Tripulante T-01 (comando)",    "cod_modulo": "COM-01", "prioridade": 2, "descricao": "Recalibrar antena de alto ganho"},
    {"id": 4, "solicitante": "Tripulante T-10 (ciência)",    "cod_modulo": "LAB-01", "prioridade": 3, "descricao": "Agendar limpeza do espectrômetro"},
    {"id": 5, "solicitante": "Tripulante T-05 (logística)",  "cod_modulo": "ARM-01", "prioridade": 3, "descricao": "Inventário de peças de reposição"},
    {"id": 6, "solicitante": "Tripulante T-02 (engenharia)", "cod_modulo": "ENE-01", "prioridade": 1, "descricao": "Limpeza dos painéis solares após poeira"},
]


def gerar():
    rng = np.random.default_rng(SEMENTE)
    sols = np.arange(1, NUM_SOLS + 1)

    # Temperatura externa: ciclo sazonal simplificado + ruído (°C)
    temp_ext = -63 + 8 * np.sin(2 * np.pi * sols / NUM_SOLS) + rng.normal(0, 3, NUM_SOLS)

    # Opacidade da poeira (tau). Tempestade de poeira entre os sols 18 e 23
    tau = np.clip(0.5 + rng.normal(0, 0.1, NUM_SOLS), 0.3, None)
    tempestade = (sols >= 18) & (sols <= 23)
    tau[tempestade] = rng.uniform(2.5, 3.5, tempestade.sum())

    leituras = []
    for m in MODULOS:
        for i, sol in enumerate(sols):
            ocup = int(rng.integers(m["ocup_min"], m["ocup_max"] + 1))
            te = round(float(temp_ext[i]), 1)
            consumo = (m["consumo_nominal_kwh"] + 1.6 * ocup
                       + 0.45 * (-55 - te) + rng.normal(0, 1.5))
            umidade = rng.uniform(62, 80) if m["tipo"] == "AGRICULTURA" else rng.uniform(35, 50)
            lux = rng.uniform(150, 600) if ocup > 0 else rng.uniform(5, 40)
            leituras.append({
                "cod_sensor": f"SNS-{m['cod_modulo']}",
                "cod_modulo": m["cod_modulo"],
                "sol": int(sol),
                "ocupacao": ocup,
                "temp_externa_c": te,
                "temp_interna_c": round(float(rng.normal(21, 0.8)), 1),
                "luminosidade_lux": round(float(lux), 1),
                "umidade_pct": round(float(umidade), 1),
                "opacidade_poeira": round(float(tau[i]), 2),
                "consumo_kwh": round(float(consumo), 2),
                "presenca": int(ocup > 0),
                "falha_sensor": 0,
            })

    # Anomalias propositais (para testar regras e limpeza de dados)
    def achar(cod, sol):
        return next(l for l in leituras if l["cod_modulo"] == cod and l["sol"] == sol)

    for cod, sol, fator in [("HAB-01", 29, 1.30), ("MED-01", 30, 1.35),
                            ("LAB-01", 30, 1.40), ("AGR-01", 12, 1.25)]:
        l = achar(cod, sol)
        l["consumo_kwh"] = round(l["consumo_kwh"] * fator, 2)      # consumo alto

    for cod, sol in [("COM-01", 30), ("ARM-01", 9), ("ENE-01", 21)]:
        l = achar(cod, sol)
        l["falha_sensor"] = 1                                       # sensor com defeito
        l["temp_interna_c"] = -99.9                                 # leitura inválida

    achar("AGR-01", 30)["umidade_pct"] = 48.5                       # estufa seca -> irrigação

    base = {
        "colonia": "Aurora Siger",
        "descricao": "Base simulada do SIFSM - 7 módulos x 30 sols",
        "unidades": {"consumo_kwh": "kWh/sol", "temp": "°C", "luminosidade": "lux",
                     "umidade": "%", "opacidade_poeira": "tau (adimensional)"},
        "modulos": [{k: v for k, v in m.items() if not k.startswith("ocup_")} for m in MODULOS],
        "leituras": leituras,
        "conexoes": CONEXOES,
        "solicitacoes": SOLICITACOES,
    }
    with open("dados_aurora_siger.json", "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=2)
    print(f"Gerado: {len(base['modulos'])} módulos, {len(leituras)} leituras.")


if __name__ == "__main__":
    gerar()
