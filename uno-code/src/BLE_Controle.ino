#include <SoftwareSerial.h>

// -------------------------
// HC-05
// -------------------------
// Arduino RX = D2  <- HC-05 TX
// Arduino TX = D3  -> HC-05 RX
SoftwareSerial bluetooth(2, 3);

// -------------------------
// Comandos
// -------------------------
#define CMD_UP     'U'
#define CMD_DOWN   'D'
#define CMD_LEFT   'L'
#define CMD_RIGHT  'R'
#define CMD_STOP   'S'

void setup() {
  // Serial USB para debug
  Serial.begin(9600);

  // Comunicação com HC-05 (baud padrão de operação, confira o datasheet do seu módulo)
  bluetooth.begin(9600);

  Serial.println("================================");
  Serial.println(" Arduino Uno + HC-05");
  Serial.println(" Controle Bluetooth");
  Serial.println("================================");
  Serial.println("Aguardando comandos...");
}

void loop() {

  // Verifica se chegou algum dado do celular
  if (bluetooth.available()) {

    char comando = bluetooth.read();

    // Mostra o comando recebido no computador
    Serial.print("Comando recebido: ");
    Serial.println(comando);

    switch (comando) {

      case CMD_UP:
        Serial.println(">>> FRENTE");
        break;

      case CMD_DOWN:
        Serial.println(">>> RE");
        break;

      case CMD_LEFT:
        Serial.println("<<< ESQUERDA");
        break;

      case CMD_RIGHT:
        Serial.println(">>> DIREITA");
        break;

      case CMD_STOP:
        Serial.println("XXX PARADO");
        break;

      default:
        Serial.println("Comando desconhecido");
        break;
    }
  }
}
