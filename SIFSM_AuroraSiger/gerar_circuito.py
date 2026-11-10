"""
gerar_circuito.py
---------------------------------------------------------------
Desenha a representação do circuito lógico da regra principal
S = (A AND B) OR C e o esquema de ligação no Arduino (Tinkercad).
Gera: circuito_logico.png e circuito_logico.pdf
Dependência extra (apenas para gerar a figura): pip install schemdraw
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import schemdraw
import schemdraw.elements as elm
from schemdraw import logic

# ---------------- 1) Diagrama de portas lógicas ----------------
with schemdraw.Drawing(show=False) as d1:
    d1.config(fontsize=13)
    e_and = logic.And().label("AND\n(74HC08)", "bottom", fontsize=10)
    logic.Line().at(e_and.in1).left(1.5).label("A  consumo alto", "left")
    logic.Line().at(e_and.in2).left(1.5).label("B  módulo crítico", "left")
    logic.Line().at(e_and.out).right(0.8)
    e_or = logic.Or().anchor("in1").label("OR\n(74HC32)", "bottom", fontsize=10)
    logic.Line().at(e_or.in2).down(1.2)
    logic.Line().left(4.9).label("C  falha no sensor", "left")
    logic.Line().at(e_or.out).right(1.2).label("S  ALERTA CRÍTICO\n(LED vermelho + buzzer)", "right")
    d1.save("_portas.png", dpi=200)

# ---------------- 2) Esquema Arduino (Tinkercad) ----------------
with schemdraw.Drawing(show=False) as d2:
    d2.config(fontsize=12, unit=2.4)
    uno = elm.Ic(pins=[
        elm.IcPin(name="D3", side="left", slot="1/3"),
        elm.IcPin(name="D2", side="left", slot="2/3"),
        elm.IcPin(name="A0", side="left", slot="3/3"),
        elm.IcPin(name="D10", side="right", slot="1/3"),
        elm.IcPin(name="D9", side="right", slot="2/3"),
        elm.IcPin(name="D8", side="right", slot="3/3"),
    ], edgepadW=2.0, edgepadH=1.2, pinspacing=2.8, leadlen=1.4,
        label="Arduino UNO R3\n\nD2/D3 em\nINPUT_PULLUP")
    # Entradas (lado esquerdo) - cada uma termina no GND
    elm.Line().at(uno.A0).left(2.2)
    pot = elm.Potentiometer().down().anchor("tap").label("Potenciômetro 10kΩ\n→ A (consumo)", "bottom", fontsize=11, ofst=(0.3, 0))
    elm.Vdd().at(pot.start).label("5V", fontsize=11)
    elm.Ground().at(pot.end)
    elm.Switch().at(uno.D2).left().label("Chave deslizante  →  B (crítico)", "top", fontsize=11)
    elm.Ground().right()
    elm.Button().at(uno.D3).left().label("Botão  →  C (falha)", "top", fontsize=11)
    elm.Ground().right()
    # Saídas (lado direito) - cada uma termina no GND
    elm.Resistor().at(uno.D8).right().label("220Ω", "bottom", fontsize=10)
    elm.LED().right().label("LED verde (normal)", "top", fontsize=11)
    elm.Ground()
    elm.Resistor().at(uno.D9).right().label("220Ω", "bottom", fontsize=10)
    elm.LED().right().label("LED vermelho (S)", "top", fontsize=11)
    elm.Ground()
    elm.Line().at(uno.D10).right(2.4)
    elm.Speaker().right().label("Buzzer (S)", "top", fontsize=11)
    elm.Ground()
    d2.save("_arduino.png", dpi=200)

# ---------------- 3) Composição final (PNG + PDF) ----------------
img1 = plt.imread("_portas.png")
img2 = plt.imread("_arduino.png")
fig = plt.figure(figsize=(11, 13))
fig.suptitle("SIFSM – Circuito lógico da regra de ALERTA CRÍTICO\nS = (A · B) + C",
             fontsize=16, fontweight="bold")
ax1 = fig.add_axes([0.03, 0.62, 0.94, 0.28]); ax1.imshow(img1); ax1.axis("off")
ax1.set_title("1) Implementação por portas lógicas (CIs 74HC08 + 74HC32)", fontsize=12, loc="left")
ax2 = fig.add_axes([0.03, 0.17, 0.94, 0.42]); ax2.imshow(img2); ax2.axis("off")
ax2.set_title("2) Implementação embarcada no Arduino (simulação no Tinkercad – arduino_sifsm.ino)",
              fontsize=12, loc="left")
tabela = ("Tabela verdade:  A B C | S\n"
          "                 0 0 0 | 0     0 0 1 | 1     0 1 0 | 0     0 1 1 | 1\n"
          "                 1 0 0 | 0     1 0 1 | 1     1 1 0 | 1     1 1 1 | 1\n\n"
          "A = 1 quando a leitura do potenciômetro (consumo simulado) passa do limite (valor > 700 de 1023)\n"
          "B = 1 quando a chave indica módulo crítico (habitação, estufa, médico, comunicação, energia)\n"
          "C = 1 quando o botão de falha do sensor é pressionado (sensor com defeito / leitura inválida)")
fig.text(0.05, 0.03, tabela, family="monospace", fontsize=10.5, va="bottom")
fig.savefig("circuito_logico.png", dpi=150)
fig.savefig("circuito_logico.pdf")
print("circuito_logico.png e circuito_logico.pdf gerados.")

import os
os.remove("_portas.png"); os.remove("_arduino.png")
