/*
  arduino_sifsm.ino  -  SIFSM | Colônia Aurora Siger
  ---------------------------------------------------------------
  Regra booleana de ALERTA CRÍTICO (mesma do Python):

      S = (A AND B) OR C

  A = consumo alto      -> potenciômetro em A0 (consumo simulado)
  B = módulo crítico    -> chave deslizante em D2 (INPUT_PULLUP)
  C = falha no sensor   -> botão em D3 (INPUT_PULLUP)

  Saídas:
  D8  -> LED verde   (operação normal)
  D9  -> LED vermelho (alerta crítico)
  D10 -> buzzer       (alerta crítico)

  Para colar no Tinkercad: Circuitos > Criar > adicionar Arduino Uno,
  montar conforme circuito_logico.png e colar este código em "Código > Texto".
*/

const int PINO_CONSUMO = A0;
const int PINO_CRITICO = 2;
const int PINO_FALHA   = 3;
const int LED_VERDE    = 8;
const int LED_VERMELHO = 9;
const int BUZZER       = 10;

const int LIMITE_CONSUMO = 700;   // 0..1023 -> ~68% da escala = consumo alto

void setup() {
  pinMode(PINO_CRITICO, INPUT_PULLUP);   // chave fechada = LOW = 1 lógico
  pinMode(PINO_FALHA,   INPUT_PULLUP);   // botão pressionado = LOW = 1 lógico
  pinMode(LED_VERDE,    OUTPUT);
  pinMode(LED_VERMELHO, OUTPUT);
  pinMode(BUZZER,       OUTPUT);
  Serial.begin(9600);
  Serial.println("SIFSM - monitor de alerta critico iniciado");
}

void loop() {
  int leitura = analogRead(PINO_CONSUMO);

  // Variáveis booleanas da regra
  bool A = leitura > LIMITE_CONSUMO;               // consumo alto
  bool B = digitalRead(PINO_CRITICO) == LOW;       // módulo crítico
  bool C = digitalRead(PINO_FALHA)   == LOW;       // falha no sensor

  bool S = (A && B) || C;                          // S = A·B + C

  digitalWrite(LED_VERMELHO, S ? HIGH : LOW);
  digitalWrite(LED_VERDE,    S ? LOW  : HIGH);
  if (S) {
    tone(BUZZER, 1000);                            // 1 kHz
  } else {
    noTone(BUZZER);
  }

  // Log no Monitor Serial (evidência para o vídeo)
  Serial.print("consumo="); Serial.print(leitura);
  Serial.print(" A="); Serial.print(A);
  Serial.print(" B="); Serial.print(B);
  Serial.print(" C="); Serial.print(C);
  Serial.print(" -> S="); Serial.println(S);

  delay(500);
}
