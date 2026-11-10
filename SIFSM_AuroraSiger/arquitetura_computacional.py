"""
arquitetura_computacional.py
---------------------------------------------------------------
Relaciona o SIFSM com arquitetura de computadores (capítulo "Do Silício
ao Qubit") e faz MEDIÇÕES REAIS no computador que executa o projeto:

1) Sequencial x vetorizado: a mesma integral (energia = ∫P dt) calculada
   com laço Python (um valor por vez, como uma CPU escalar) e com NumPy
   (operações SIMD sobre blocos de dados - a ideia por trás de GPUs/NPUs).
2) Movimentação de dados: float64 x float32 -> metade dos bytes trafegando
   entre memória e processador para o mesmo cálculo.
3) Operações de multiplicação e acumulação (MAC) da regressão linear.
4) Mapa "parte do sistema -> unidade de processamento mais adequada".
"""

import os
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PASTA_GRAF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graficos_ou_imagens")

MAPA_ARQUITETURA = [
    ("Leitura de sensores + regra S = A·B + C", "Microcontrolador (Arduino) no módulo",
     "Decisão simples, tempo real, mW de consumo; funciona mesmo sem a rede"),
    ("CRUD e consultas ao banco", "CPU do servidor local da colônia",
     "Tarefa sequencial, com desvios e E/S de disco; poucos dados por vez"),
    ("Estruturas (fila, pilha, hash, grafo)", "CPU (cache L1/L2)",
     "Acesso irregular por ponteiros; se beneficia de cache, não de paralelismo massivo"),
    ("Simulação energética (milhares de passos)", "CPU com SIMD (NumPy) / GPU para muitos cenários",
     "Mesma conta repetida em vetores: paralelismo de dados"),
    ("Regressão linear (treino)", "CPU (BLAS vetorizado)",
     "Poucas centenas de linhas; GPU seria desperdício de energia"),
    ("Agentes com LLM (versão SDK)", "GPU/TPU em data center ou NPU local com modelo pequeno",
     "Bilhões de MACs por token; maior consumo energético do sistema"),
]


def potencia(t):
    return np.maximum(0.0, 40 * np.sin(np.pi * (t % 24.66 - 6) / 12.33))


def bench_sequencial_vetorizado(n=1_000_000) -> dict:
    t = np.linspace(0, 10 * 24.66, n)
    p = potencia(t)
    dt = t[1] - t[0]
    lista_p = p.tolist()                         # dados como objetos Python

    t0 = time.perf_counter()
    soma = 0.0
    for i in range(n - 1):                       # 1 operação por iteração (escalar)
        soma += (lista_p[i] + lista_p[i + 1]) * 0.5 * dt
    t_seq = time.perf_counter() - t0

    t0 = time.perf_counter()
    soma_vet = float(np.sum((p[:-1] + p[1:]) * 0.5) * dt)   # blocos SIMD
    t_vet = time.perf_counter() - t0

    p32 = p.astype(np.float32)
    t0 = time.perf_counter()
    soma_32 = float(np.sum((p32[:-1] + p32[1:]) * np.float32(0.5)) * dt)
    t_32 = time.perf_counter() - t0
    return {"n": n, "t_seq": t_seq, "t_vet": t_vet, "t_32": t_32,
            "aceleracao": t_seq / t_vet, "resultado_seq": soma, "resultado_vet": soma_vet,
            "resultado_32": soma_32, "bytes_64": p.nbytes, "bytes_32": p32.nbytes}


def macs_regressao(linhas=207, variaveis=3) -> int:
    """Equações normais (XᵀX)⁻¹Xᵀy: XᵀX custa linhas·(p+1)² multiplicações-acumulações."""
    p = variaveis + 1
    return linhas * p * p + linhas * p


def executar(verbose=True, grafico=True) -> dict:
    r = bench_sequencial_vetorizado()
    r["macs_regressao"] = macs_regressao()
    if verbose:
        print("\n=== ARQUITETURA COMPUTACIONAL – MEDIÇÕES NESTE COMPUTADOR ===")
        print(f"Integral de {r['n']:,} amostras de potência (energia de 10 sols):".replace(",", "."))
        print(f"  Laço Python (sequencial/escalar): {r['t_seq']*1000:8.1f} ms  -> {r['resultado_seq']:.2f} kWh")
        print(f"  NumPy float64 (vetorizado/SIMD): {r['t_vet']*1000:8.1f} ms  -> {r['resultado_vet']:.2f} kWh")
        print(f"  NumPy float32 (metade dos bytes): {r['t_32']*1000:8.1f} ms  -> {r['resultado_32']:.2f} kWh")
        print(f"  Aceleração do processamento vetorizado: ≈ {r['aceleracao']:.0f}x")
        print(f"  Dados movimentados: {r['bytes_64']/1e6:.1f} MB (float64) x {r['bytes_32']/1e6:.1f} MB (float32)")
        print(f"  Treino da regressão: ≈ {r['macs_regressao']:,} operações MAC (irrisório para uma CPU)".replace(",", "."))
        print("\nOnde cada parte do SIFSM deveria rodar:")
        for parte, hw, motivo in MAPA_ARQUITETURA:
            print(f"  • {parte:<44} -> {hw}\n      {motivo}")
        print("\nConclusão: processar perto do dado (edge/Arduino), vetorizar o que é repetitivo e"
              " reservar GPU/TPU só para o que exige (LLM) reduz energia - recurso escasso em Marte.")
    if grafico:
        os.makedirs(PASTA_GRAF, exist_ok=True)
        fig, ax = plt.subplots(figsize=(8, 4))
        nomes = ["Laço Python\n(sequencial)", "NumPy float64\n(vetorizado)", "NumPy float32\n(vetorizado)"]
        tempos = [r["t_seq"] * 1000, r["t_vet"] * 1000, r["t_32"] * 1000]
        b = ax.bar(nomes, tempos, color=["#e63946", "#457b9d", "#2a9d8f"])
        ax.bar_label(b, fmt="%.1f ms")
        ax.set_yscale("log"); ax.set_ylabel("Tempo (ms, escala log)")
        ax.set_title(f"Mesma integral, 1 milhão de amostras – vetorização ≈ {r['aceleracao']:.0f}x mais rápida")
        ax.grid(axis="y", alpha=0.3)
        r["arquivo"] = os.path.join(PASTA_GRAF, "arq_1_sequencial_vs_vetorizado.png")
        fig.tight_layout(); fig.savefig(r["arquivo"], dpi=130); plt.close(fig)
    return r


if __name__ == "__main__":
    executar()
