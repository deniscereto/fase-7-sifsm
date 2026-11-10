"""
modelo_linear.py
---------------------------------------------------------------
Modelagem linear aplicada à tomada de decisão: estimar o CONSUMO
ENERGÉTICO (kWh/sol) para planejar a carga da bateria.

1) Regressão linear SIMPLES (nível colônia):
       consumo_total_sol = b0 + b1 · temp_externa
2) Regressão linear MÚLTIPLA (nível módulo):
       consumo = b0 + b1·ocupacao + b2·temp_externa + b3·consumo_nominal

Etapas (como no capítulo "Aplicações em cenários reais"):
análise exploratória -> correlação -> treino/teste -> coeficientes ->
métricas (MAE, RMSE, R²) -> multicolinearidade (VIF) -> resíduos.
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

PASTA_GRAF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graficos_ou_imagens")
FEATURES = ["ocupacao", "temp_externa_c", "consumo_nominal_kwh"]
ALVO = "consumo_kwh"


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Limpeza: remove leituras com falha de sensor (dados não confiáveis)."""
    limpo = df[(df.falha_sensor == 0)].copy()
    for c in FEATURES + [ALVO]:
        limpo[c] = pd.to_numeric(limpo[c], errors="coerce")
    return limpo.dropna(subset=FEATURES + [ALVO])


def calcular_vif(X: pd.DataFrame) -> pd.Series:
    """VIF_j = 1 / (1 - R²_j), onde R²_j vem de regredir X_j nas demais variáveis.
    (Mesmo conceito do statsmodels, implementado com scikit-learn.)"""
    vifs = {}
    for col in X.columns:
        outras = X.drop(columns=col)
        r2 = LinearRegression().fit(outras, X[col]).score(outras, X[col])
        vifs[col] = np.inf if r2 >= 1 else 1 / (1 - r2)
    return pd.Series(vifs, name="VIF")


def metricas(y, y_pred) -> dict:
    return {"MAE": mean_absolute_error(y, y_pred),
            "RMSE": float(np.sqrt(mean_squared_error(y, y_pred))),
            "R2": r2_score(y, y_pred)}


def treinar_modelos(df_bruto: pd.DataFrame, graficos=True, verbose=True) -> dict:
    df = preparar(df_bruto)
    removidas = len(df_bruto) - len(df)

    # ---------------- Análise exploratória ----------------
    corr = df[FEATURES + [ALVO]].corr()

    # ---------------- 1) Regressão simples (colônia) ----------------
    por_sol = df.groupby("sol").agg(consumo_total=(ALVO, "sum"),
                                    temp_externa=("temp_externa_c", "mean"),
                                    n=("cod_modulo", "count")).reset_index()
    por_sol = por_sol[por_sol.n == por_sol.n.max()]       # só sols com todos os módulos válidos
    Xs, ys = por_sol[["temp_externa"]], por_sol["consumo_total"]
    simples = LinearRegression().fit(Xs, ys)
    met_simples = metricas(ys, simples.predict(Xs))
    r_pearson = np.corrcoef(por_sol.temp_externa, por_sol.consumo_total)[0, 1]

    # ---------------- 2) Regressão múltipla (módulo) ----------------
    X, y = df[FEATURES], df[ALVO]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=42)
    multipla = LinearRegression().fit(X_tr, y_tr)
    pred_te = multipla.predict(X_te)
    met_treino = metricas(y_tr, multipla.predict(X_tr))
    met_teste = metricas(y_te, pred_te)
    vif = calcular_vif(X)
    coefs = pd.Series(multipla.coef_, index=FEATURES)

    res = {"df": df, "removidas": removidas, "corr": corr,
           "simples": simples, "met_simples": met_simples, "r_pearson": r_pearson, "por_sol": por_sol,
           "multipla": multipla, "coefs": coefs, "intercepto": multipla.intercept_,
           "met_treino": met_treino, "met_teste": met_teste, "vif": vif,
           "y_te": y_te, "pred_te": pred_te, "arquivos": []}

    if graficos:
        res["arquivos"] = gerar_graficos(res)
    if verbose:
        imprimir_relatorio(res)
    return res


def imprimir_relatorio(r: dict):
    df = r["df"]
    print("\n=== MODELO LINEAR – ESTIMATIVA DE CONSUMO ENERGÉTICO ===")
    print(f"Registros usados: {len(df)} (removidos {r['removidas']} com falha de sensor)")
    print("\nAnálise exploratória (resumo):")
    print(df[FEATURES + [ALVO]].describe().round(2).loc[["mean", "std", "min", "max"]].to_string())
    print("\nCorrelação de Pearson com o consumo:")
    print(r["corr"][ALVO].drop(ALVO).round(3).to_string())

    s = r["simples"]
    print("\n[1] Regressão SIMPLES – consumo total da colônia por sol x temperatura externa")
    print(f"    consumo_total = {s.intercept_:.2f} + ({s.coef_[0]:.3f}) · temp_externa")
    print(f"    -> cada 1 °C MAIS FRIO lá fora aumenta o consumo da colônia em ≈ {-s.coef_[0]:.2f} kWh/sol")
    print(f"    r de Pearson = {r['r_pearson']:.3f} | R² = {r['met_simples']['R2']:.3f} | "
          f"MAE = {r['met_simples']['MAE']:.2f} kWh")

    print("\n[2] Regressão MÚLTIPLA – consumo por módulo (treino 75% / teste 25%)")
    termos = " ".join(f"{'+' if v >= 0 else '-'} {abs(v):.3f}·{k}" for k, v in r["coefs"].items())
    print(f"    consumo = {r['intercepto']:.2f} {termos}")
    c = r["coefs"]
    print(f"    • ocupação: cada tripulante a mais no módulo => +{c['ocupacao']:.2f} kWh/sol")
    print(f"    • temperatura externa: cada 1 °C mais frio => +{-c['temp_externa_c']:.2f} kWh/sol (aquecimento)")
    print(f"    • consumo nominal: coeficiente {c['consumo_nominal_kwh']:.2f} (≈1 => o nominal de projeto está bem calibrado)")
    mt, ms = r["met_treino"], r["met_teste"]
    print(f"    Treino: MAE {mt['MAE']:.2f} | RMSE {mt['RMSE']:.2f} | R² {mt['R2']:.3f}")
    print(f"    Teste : MAE {ms['MAE']:.2f} | RMSE {ms['RMSE']:.2f} | R² {ms['R2']:.3f}")
    print("    VIF (multicolinearidade; < 5 é aceitável): " +
          ", ".join(f"{k}={v:.2f}" for k, v in r["vif"].items()))
    if r["arquivos"]:
        print("Gráficos salvos em:", *[os.path.relpath(a) for a in r["arquivos"]], sep="\n  ")


def gerar_graficos(r: dict) -> list[str]:
    os.makedirs(PASTA_GRAF, exist_ok=True)
    arqs = []

    # EDA: correlação + dispersões
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.5))
    im = axs[0].imshow(r["corr"], cmap="RdBu_r", vmin=-1, vmax=1)
    nomes = ["ocupação", "temp. ext.", "nominal", "consumo"]
    axs[0].set_xticks(range(4), nomes, rotation=30); axs[0].set_yticks(range(4), nomes)
    for i in range(4):
        for j in range(4):
            axs[0].text(j, i, f"{r['corr'].iloc[i, j]:.2f}", ha="center", va="center", fontsize=9)
    axs[0].set_title("Matriz de correlação"); fig.colorbar(im, ax=axs[0], shrink=0.8)
    df = r["df"]
    sc = axs[1].scatter(df.ocupacao, df.consumo_kwh, c=df.consumo_nominal_kwh, cmap="viridis", s=18)
    axs[1].set(xlabel="Ocupação (tripulantes)", ylabel="Consumo (kWh/sol)", title="Consumo x ocupação")
    fig.colorbar(sc, ax=axs[1], label="nominal (kWh)", shrink=0.8)
    ps = r["por_sol"]
    axs[2].scatter(ps.temp_externa, ps.consumo_total, color="#457b9d")
    xx = np.linspace(ps.temp_externa.min(), ps.temp_externa.max(), 50)
    axs[2].plot(xx, r["simples"].predict(pd.DataFrame({"temp_externa": xx})), "r-",
                label=f"Reta ajustada (R²={r['met_simples']['R2']:.2f})")
    axs[2].set(xlabel="Temperatura externa média (°C)", ylabel="Consumo total (kWh/sol)",
               title="Regressão simples – colônia")
    axs[2].legend()
    for a in axs[1:]:
        a.grid(alpha=0.3)
    arqs.append(os.path.join(PASTA_GRAF, "reg_1_exploratoria.png"))
    fig.tight_layout(); fig.savefig(arqs[-1], dpi=130); plt.close(fig)

    # Avaliação: real x previsto e resíduos
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.5))
    y, p = r["y_te"], r["pred_te"]
    axs[0].scatter(y, p, color="#2a9d8f", s=22)
    lim = [min(y.min(), p.min()) - 2, max(y.max(), p.max()) + 2]
    axs[0].plot(lim, lim, "k--", label="previsão perfeita")
    axs[0].set(xlabel="Consumo real (kWh)", ylabel="Consumo previsto (kWh)",
               title=f"Regressão múltipla – teste (R²={r['met_teste']['R2']:.3f})")
    axs[0].legend()
    axs[1].scatter(p, y - p, color="#e76f51", s=22)
    axs[1].axhline(0, color="k", lw=1)
    axs[1].set(xlabel="Consumo previsto (kWh)", ylabel="Resíduo (real − previsto)",
               title="Resíduos (pontos altos = consumos anômalos)")
    for a in axs:
        a.grid(alpha=0.3)
    arqs.append(os.path.join(PASTA_GRAF, "reg_2_avaliacao.png"))
    fig.tight_layout(); fig.savefig(arqs[-1], dpi=130); plt.close(fig)
    return arqs


def prever_consumo(modelo: LinearRegression, ocupacao: float, temp_externa: float,
                   consumo_nominal: float) -> float:
    X = pd.DataFrame([[ocupacao, temp_externa, consumo_nominal]], columns=FEATURES)
    return float(modelo.predict(X)[0])


if __name__ == "__main__":
    from banco_dados import BancoAurora
    banco = BancoAurora(); banco.conectar()
    if banco.base_vazia():
        banco.carregar_json()
    treinar_modelos(banco.dataframe_analitico())
    banco.fechar()
