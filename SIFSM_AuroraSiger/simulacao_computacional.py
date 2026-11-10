"""
simulacao_computacional.py
---------------------------------------------------------------
Simulação energética da colônia Aurora Siger + integração matemática.

FENÔMENO REPRESENTADO
  Balanço de energia da colônia ao longo de vários sols: os painéis solares
  geram energia de dia, os módulos consomem o tempo todo e a bateria
  absorve a diferença. Uma tempestade de poeira reduz a geração solar.

VARIÁVEIS
  t            tempo (h)                       P_solar(t)  geração (kW)
  tau          opacidade da poeira             P_carga(t)  consumo (kW)
  SoC(t)       estado de carga da bateria (0..1)   C       capacidade (kWh)

MATEMÁTICA USADA (capítulo de Integração Matemática)
  * Estado de carga por contagem de energia (análogo à contagem de Coulomb):
        SoC(t) = SoC(t0) + (1/C) * ∫ [η_c·P_sol(τ) − P_carga(τ)/η_d] dτ
  * Energia = área sob a curva de potência: E = ∫ P(t) dt  (regra dos trapézios)
  * Média de função: P_média = (1/T) ∫ P(t) dt
  * Integral simbólica (SymPy) da curva solar ideal para validar o resultado numérico
  * Convolução: efeito de inércia do sensor de temperatura + filtro de média móvel

LIMITAÇÕES
  * Perfis de geração/consumo simplificados (senoide e fator diário);
  * bateria com eficiência constante, sem degradação nem efeito da temperatura;
  * a poeira é modelada só pelo fator exp(-0,4·tau); sem limpeza de painéis;
  * passo fixo (Euler) de 3 minutos.
"""

import os

import matplotlib
matplotlib.use("Agg")                     # gera arquivos sem abrir janelas
import matplotlib.pyplot as plt
import numpy as np
import sympy as sp
from scipy.integrate import trapezoid

PASTA_GRAF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graficos_ou_imagens")

# ---------------- Parâmetros físicos ----------------
SOL_H = 24.66              # duração de 1 sol em horas
DIA_INICIO_H = 6.0         # nascer do sol (h)
DIA_DURACAO_H = 12.33      # horas de luz
P_PICO_KW = 48.0           # potência de pico dos painéis limpos (kW)
CAP_BATERIA_KWH = 600.0    # capacidade do banco de baterias
SOC_INICIAL = 0.85
SOC_RESERVA = 0.10         # abaixo disso o BMS corta a descarga (proteção)
SOC_ECONOMIA = 0.40        # liga modo economia (mesmo limiar de regras_logicas)
SOC_SAIDA_ECONOMIA = 0.50  # histerese para desligar o modo economia
TAU_TEMPESTADE = 1.5       # opacidade acima disso = tempestade de poeira detectada
ETA_CARGA, ETA_DESCARGA = 0.95, 0.95
DT_H = 0.05                # passo de 3 minutos

# Consumo médio padrão (kWh/sol) caso o banco não esteja disponível
CONSUMO_PADRAO = {"HAB-01": 63.0, "AGR-01": 63.5, "LAB-01": 38.0, "COM-01": 24.0,
                  "MED-01": 25.0, "ARM-01": 16.0, "ENE-01": 19.0}
CRITICOS_PADRAO = {"HAB-01", "AGR-01", "COM-01", "MED-01", "ENE-01"}


def _garantir_pasta():
    os.makedirs(PASTA_GRAF, exist_ok=True)


# ===============================================================
# Modelos de geração e consumo
# ===============================================================
def transmissao_poeira(tau):
    return np.exp(-0.4 * np.asarray(tau))


def potencia_solar(t_h, tau):
    """P_solar(t) = P_pico · T(tau) · sen(π (h - h0)/D) durante o dia; 0 à noite."""
    hora = np.mod(t_h, SOL_H)
    fase = (hora - DIA_INICIO_H) / DIA_DURACAO_H
    dia = (fase >= 0) & (fase <= 1)
    return np.where(dia, P_PICO_KW * transmissao_poeira(tau) * np.sin(np.pi * np.clip(fase, 0, 1)), 0.0)


def perfil_diario(t_h):
    """Fator de uso ao longo do sol (média = 1): pico às 15h com a tripulação ativa."""
    return 1 + 0.2 * np.cos(2 * np.pi * (np.mod(t_h, SOL_H) - 15) / SOL_H)


def tau_cenario(t_h, sols_tempestade=(3, 7), tau_normal=0.5, tau_tempestade=3.0):
    sol = np.floor(t_h / SOL_H) + 1
    tempestade = (sol >= sols_tempestade[0]) & (sol <= sols_tempestade[1])
    return np.where(tempestade, tau_tempestade, tau_normal)


# ===============================================================
# Simulação de um cenário
# ===============================================================
def simular(consumo_kwh_sol: dict, criticos: set, num_sols=10, tempestade=True,
            gestao_inteligente=False, nome="cenário", soc_inicial=SOC_INICIAL, tau_fixo=None):
    t = np.arange(0, num_sols * SOL_H, DT_H)
    if tau_fixo is not None:
        tau = np.full_like(t, float(tau_fixo))
    else:
        tau = tau_cenario(t) if tempestade else np.full_like(t, 0.5)
    p_sol = potencia_solar(t, tau)
    perfil = perfil_diario(t)

    pot_media = {m: e / SOL_H for m, e in consumo_kwh_sol.items()}     # kW médios
    p_crit = sum(p for m, p in pot_media.items() if m in criticos)
    p_ncrit = sum(p for m, p in pot_media.items() if m not in criticos)

    soc = np.empty_like(t)
    p_carga = np.empty_like(t)
    nao_suprida = np.zeros_like(t)          # kW que a colônia pediu e não recebeu
    economia = np.zeros_like(t, dtype=bool)
    s, modo_eco = soc_inicial, False

    for k in range(len(t)):
        # --- regra booleana de modo economia (com histerese no SoC) ---
        #     ECONOMIA = (SOC_BAIXO OR TEMPESTADE_DETECTADA)  -> só afeta cargas não críticas
        if gestao_inteligente:
            tempestade_detectada = tau[k] > TAU_TEMPESTADE
            if not modo_eco and (s < SOC_ECONOMIA or tempestade_detectada):
                modo_eco = True
            elif modo_eco and s > SOC_SAIDA_ECONOMIA and not tempestade_detectada:
                modo_eco = False
        # cargas não críticas desligadas e críticas -15% (iluminação, setpoint térmico)
        demanda = (p_crit * (0.85 if modo_eco else 1.0) + (0 if modo_eco else p_ncrit)) * perfil[k]

        saldo = ETA_CARGA * p_sol[k] - demanda / ETA_DESCARGA       # kW na bateria
        s_novo = s + saldo * DT_H / CAP_BATERIA_KWH                 # passo de Euler
        if s_novo < SOC_RESERVA:                                    # BMS corta carga
            falta_kwh = (SOC_RESERVA - s_novo) * CAP_BATERIA_KWH
            nao_suprida[k] = falta_kwh / DT_H * ETA_DESCARGA
            s_novo = SOC_RESERVA
        s = min(s_novo, 1.0)                                        # bateria cheia
        soc[k], p_carga[k], economia[k] = s, demanda, modo_eco

    # Energias = área sob as curvas (regra dos trapézios)
    e_gerada = trapezoid(p_sol, t)
    e_consumida = trapezoid(p_carga, t)
    e_nao_suprida = trapezoid(nao_suprida, t)
    return {
        "nome": nome, "t": t, "tau": tau, "p_solar": p_sol, "p_carga": p_carga, "soc": soc,
        "nao_suprida": nao_suprida, "economia": economia,
        "e_gerada_kwh": e_gerada, "e_consumida_kwh": e_consumida,
        "e_nao_suprida_kwh": e_nao_suprida,
        "p_media_carga_kw": e_consumida / (t[-1] - t[0]),            # média de função
        "soc_min": soc.min(), "soc_final": soc[-1],
        "horas_economia": economia.sum() * DT_H,
    }


# ===============================================================
# Validação matemática: integral simbólica x numérica
# ===============================================================
def validar_integral_solar(tau=0.5):
    h = sp.symbols("h", real=True)
    P, D = sp.Rational(48), sp.Rational(1233, 100)
    expr = P * sp.exp(sp.Rational(-2, 5) * sp.nsimplify(tau)) * sp.sin(sp.pi * h / D)
    integral_simbolica = sp.integrate(expr, (h, 0, D))                # = 2·P·T·D/π
    valor_exato = float(integral_simbolica)

    t = np.arange(0, SOL_H, DT_H)
    p = potencia_solar(t, tau)
    valor_scipy = trapezoid(p, t)
    # trapézio "na mão" (como no capítulo): Σ (y_i + y_{i+1})/2 · Δt
    valor_manual = sum((p[i] + p[i + 1]) / 2 * (t[i + 1] - t[i]) for i in range(len(t) - 1))
    return {"expressao": str(sp.simplify(integral_simbolica)), "exato_kwh": valor_exato,
            "trapezio_scipy_kwh": valor_scipy, "trapezio_manual_kwh": valor_manual,
            "erro_relativo_pct": abs(valor_scipy - valor_exato) / valor_exato * 100}


# ===============================================================
# Convolução: inércia do sensor de temperatura + filtro de ruído
# ===============================================================
def simular_sensor_convolucao(seed=7):
    rng = np.random.default_rng(seed)
    t = np.arange(0, SOL_H, DT_H)
    temp_real = 21 + 1.2 * np.sin(2 * np.pi * (t - 9) / SOL_H)
    temp_real[(t > 12) & (t < 12.5)] += 3.0                  # porta aberta / evento
    tau_sensor_h = 0.25                                      # constante de tempo do sensor
    th = np.arange(0, 5 * tau_sensor_h, DT_H)
    h = np.exp(-th / tau_sensor_h); h /= h.sum()             # resposta ao impulso normalizada
    medida = np.convolve(temp_real, h, mode="full")[:len(t)]  # sensor "atrasa" o sinal
    medida[: len(h)] = temp_real[: len(h)]                   # evita borda inicial
    medida_ruido = medida + rng.normal(0, 0.35, len(t))
    janela = np.ones(9) / 9                                  # média móvel (27 min)
    filtrada = np.convolve(medida_ruido, janela, mode="same")
    erro_bruto = np.sqrt(np.mean((medida_ruido - temp_real)[10:-10] ** 2))
    erro_filtrado = np.sqrt(np.mean((filtrada - temp_real)[10:-10] ** 2))
    return {"t": t, "real": temp_real, "medida": medida_ruido, "filtrada": filtrada,
            "rmse_bruto": erro_bruto, "rmse_filtrado": erro_filtrado}


# ===============================================================
# Gráficos
# ===============================================================
def gerar_graficos(cenarios: list[dict], sensor: dict) -> list[str]:
    _garantir_pasta()
    arquivos = []
    cores = {"Normal": "#2a9d8f", "Tempestade sem gestão": "#e63946",
             "Tempestade com gestão inteligente": "#457b9d"}

    # 1) Potência num sol normal x sol de tempestade (área = energia)
    c = cenarios[2]
    fig, ax = plt.subplots(figsize=(11, 5))
    for sol, rotulo, cor in [(1, "Sol 1 (normal)", "#f4a261"), (4, "Sol 4 (tempestade)", "#6c757d")]:
        m = (c["t"] >= (sol - 1) * SOL_H) & (c["t"] < sol * SOL_H)
        hora = c["t"][m] - (sol - 1) * SOL_H
        ax.plot(hora, c["p_solar"][m], color=cor, lw=2, label=f"Geração solar – {rotulo}")
        ax.fill_between(hora, c["p_solar"][m], alpha=0.25, color=cor)
    m1 = c["t"] < SOL_H
    ax.plot(c["t"][m1], c["p_carga"][m1], "k--", lw=2, label="Consumo da colônia")
    ax.set(xlabel="Hora do sol (h)", ylabel="Potência (kW)",
           title="Potência ao longo do sol – a área sob a curva é a energia (∫P dt)")
    ax.grid(alpha=0.3); ax.legend()
    arquivos.append(os.path.join(PASTA_GRAF, "sim_1_potencia_sol.png"))
    fig.tight_layout(); fig.savefig(arquivos[-1], dpi=140); plt.close(fig)

    # 2) SoC nos três cenários
    fig, ax = plt.subplots(figsize=(11, 5))
    for c in cenarios:
        ax.plot(c["t"] / SOL_H, c["soc"] * 100, lw=2, label=c["nome"], color=cores.get(c["nome"]))
    ax.axvspan(2, 7, color="#bc6c25", alpha=0.12, label="Tempestade de poeira (sols 3–7)")
    ax.axhline(SOC_ECONOMIA * 100, color="orange", ls=":", label="Limiar SoC do modo economia (40%)")
    ax.axhline(SOC_RESERVA * 100, color="red", ls=":", label="Reserva de proteção (10%)")
    ax.set(xlabel="Tempo (sols)", ylabel="Estado de carga – SoC (%)", ylim=(0, 105),
           title="Estado de carga da bateria: SoC(t) = SoC₀ + (1/C)∫(P_solar − P_carga)dt")
    ax.grid(alpha=0.3); ax.legend(loc="lower left", fontsize=9)
    arquivos.append(os.path.join(PASTA_GRAF, "sim_2_soc_cenarios.png"))
    fig.tight_layout(); fig.savefig(arquivos[-1], dpi=140); plt.close(fig)

    # 3) Balanço de energia por cenário
    fig, ax = plt.subplots(figsize=(10, 5))
    nomes = [c["nome"].replace(" inteligente", "\ninteligente").replace(" sem", "\nsem") for c in cenarios]
    x = np.arange(len(cenarios)); w = 0.27
    for i, (chave, rot, cor) in enumerate([("e_gerada_kwh", "Gerada", "#f4a261"),
                                           ("e_consumida_kwh", "Demandada", "#457b9d"),
                                           ("e_nao_suprida_kwh", "NÃO suprida", "#e63946")]):
        v = [c[chave] for c in cenarios]
        b = ax.bar(x + (i - 1) * w, v, w, label=rot, color=cor)
        ax.bar_label(b, fmt="%.0f", fontsize=8)
    ax.set_xticks(x, nomes); ax.set_ylabel("Energia em 10 sols (kWh)")
    ax.set_title("Balanço energético por cenário (integração numérica pela regra dos trapézios)")
    ax.legend(); ax.grid(axis="y", alpha=0.3)
    arquivos.append(os.path.join(PASTA_GRAF, "sim_3_balanco_energia.png"))
    fig.tight_layout(); fig.savefig(arquivos[-1], dpi=140); plt.close(fig)

    # 4) Convolução do sensor
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(sensor["t"], sensor["medida"], color="#adb5bd", lw=1, label="Leitura do sensor (atraso + ruído)")
    ax.plot(sensor["t"], sensor["real"], "k", lw=2, label="Temperatura real")
    ax.plot(sensor["t"], sensor["filtrada"], color="#e76f51", lw=2,
            label="Após filtro de média móvel (convolução)")
    ax.set(xlabel="Hora do sol (h)", ylabel="Temperatura interna (°C)",
           title=f"Convolução em sensores – RMSE bruto {sensor['rmse_bruto']:.2f} °C → "
                 f"filtrado {sensor['rmse_filtrado']:.2f} °C")
    ax.grid(alpha=0.3); ax.legend(fontsize=9)
    arquivos.append(os.path.join(PASTA_GRAF, "sim_4_convolucao_sensor.png"))
    fig.tight_layout(); fig.savefig(arquivos[-1], dpi=140); plt.close(fig)
    return arquivos


# ===============================================================
# Execução completa (usada pelo menu e pelo modo standalone)
# ===============================================================
def executar_simulacao(consumo_kwh_sol: dict | None = None, criticos: set | None = None,
                       graficos=True, verbose=True) -> dict:
    consumo = consumo_kwh_sol or CONSUMO_PADRAO
    criticos = criticos or CRITICOS_PADRAO
    cenarios = [
        simular(consumo, criticos, tempestade=False, nome="Normal"),
        simular(consumo, criticos, tempestade=True, nome="Tempestade sem gestão"),
        simular(consumo, criticos, tempestade=True, gestao_inteligente=True,
                nome="Tempestade com gestão inteligente"),
    ]
    validacao = validar_integral_solar()
    sensor = simular_sensor_convolucao()
    arquivos = gerar_graficos(cenarios, sensor) if graficos else []

    if verbose:
        print("\n=== SIMULAÇÃO ENERGÉTICA – 10 sols (passo de 3 min) ===")
        print(f"Consumo médio informado: {sum(consumo.values()):.1f} kWh/sol | "
              f"Bateria: {CAP_BATERIA_KWH:.0f} kWh | Painéis: {P_PICO_KW:.0f} kW pico")
        print(f"{'Cenário':38s} {'Gerada':>8s} {'Demanda':>8s} {'Ñ supr.':>8s} "
              f"{'P média':>8s} {'SoC mín':>8s} {'h econ.':>8s}")
        for c in cenarios:
            print(f"{c['nome']:38s} {c['e_gerada_kwh']:8.0f} {c['e_consumida_kwh']:8.0f} "
                  f"{c['e_nao_suprida_kwh']:8.1f} {c['p_media_carga_kw']:8.2f} "
                  f"{c['soc_min']*100:7.1f}% {c['horas_economia']:8.1f}")
        v = validacao
        print("\nValidação da integração (geração solar em 1 sol, tau = 0,5):")
        print(f"  Integral simbólica (SymPy): {v['expressao']}  ≈ {v['exato_kwh']:.2f} kWh")
        print(f"  Trapézios (SciPy): {v['trapezio_scipy_kwh']:.2f} kWh | "
              f"Trapézios manual: {v['trapezio_manual_kwh']:.2f} kWh | "
              f"erro relativo: {v['erro_relativo_pct']:.4f}%")
        print(f"\nConvolução no sensor de temperatura: RMSE {sensor['rmse_bruto']:.2f} °C "
              f"-> {sensor['rmse_filtrado']:.2f} °C após filtro de média móvel")
        if arquivos:
            print("Gráficos salvos em:", *[os.path.relpath(a) for a in arquivos], sep="\n  ")
    return {"cenarios": cenarios, "validacao": validacao, "sensor": sensor, "arquivos": arquivos}


def projetar_soc(consumo_kwh_sol: dict, criticos: set, soc_inicial: float, tau: float,
                 num_sols: int = 3) -> dict:
    """Projeção rápida usada na 'Análise integrada': mantém o tau atual por N sols."""
    sem = simular(consumo_kwh_sol, criticos, num_sols=num_sols, nome="sem gestão",
                  soc_inicial=soc_inicial, tau_fixo=tau)
    com = simular(consumo_kwh_sol, criticos, num_sols=num_sols, gestao_inteligente=True,
                  nome="com gestão", soc_inicial=soc_inicial, tau_fixo=tau)
    return {"sem_gestao": sem, "com_gestao": com}


if __name__ == "__main__":
    # Tenta usar os consumos médios reais do banco; se não houver, usa o padrão
    try:
        from banco_dados import BancoAurora
        banco = BancoAurora(); banco.conectar()
        if banco.base_vazia():
            banco.carregar_json()
        df = banco.dataframe_analitico()
        consumo = df[df.opacidade_poeira < 1.5].groupby("cod_modulo").consumo_kwh.mean().to_dict()
        criticos = set(df[df.critico == 1].cod_modulo)
        banco.fechar()
    except Exception as e:
        print(f"[AVISO] Usando consumo padrão ({e})")
        consumo, criticos = None, None
    executar_simulacao(consumo, criticos)
