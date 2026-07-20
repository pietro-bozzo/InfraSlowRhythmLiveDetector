/*
  Contrôle manuel de stimulation — mode Gated Burst (Agilent 33250A)
  ------------------------------------------------------------------
  Générateur configuré en : Burst → Gated, branché sur Trig In panneau arrière.
  Le générateur tourne tant que gatePin est HIGH, s'arrête proprement
  en fin de cycle quand il repasse LOW.

  Commandes série :
    START          → démarre la session (définit la baseline t=0)
    STOP           → arrête la session (coupe le gate si actif)
    <durée en s>   → envoie une stimulation de cette durée (ex: "0.1", "2.5")

  Log série (compatible stim_logger.py) :
    SESSION_START,<timestamp>
    STIM,<timestamp>,<durée_s>
    SESSION_STOP,<timestamp>
*/

const int gatePin = 11;

unsigned long debsession  = 0;
bool          sessionActive = false;

String formatTime(unsigned long ms) {
  unsigned long totalSeconds = ms / 1000;
  unsigned long minutes      = totalSeconds / 60;
  unsigned long seconds      = totalSeconds % 60;
  unsigned long milliseconds = ms % 1000;
  char buffer[20];
  sprintf(buffer, "%02lu:%02lu.%03lu", minutes, seconds, milliseconds);
  return String(buffer);
}

void setup() {
  pinMode(gatePin, OUTPUT);
  digitalWrite(gatePin, LOW);
  Serial.begin(57600);
  Serial.println("# Gated Burst Manual Control ready");
  Serial.println("# Commandes : START | STOP | <duree en secondes>");
}

void loop() {
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim();

    // ── START ──────────────────────────────────────────────────────────────
    if (input.equalsIgnoreCase("START")) {
      sessionActive = true;
      debsession    = millis();
      Serial.print("SESSION_START,");
      Serial.println(formatTime(0));
      return;
    }

    // ── STOP ───────────────────────────────────────────────────────────────
    if (input.equalsIgnoreCase("STOP")) {
      sessionActive = false;
      digitalWrite(gatePin, LOW);
      Serial.print("SESSION_STOP,");
      Serial.println(formatTime(millis() - debsession));
      return;
    }

    // ── DURÉE DE STIMULATION ───────────────────────────────────────────────
    if (sessionActive) {
      float duration = input.toFloat();
      if (duration > 0) {
        unsigned long durationMs = (unsigned long)(duration * 1000.0);

        // Log
        Serial.print("STIM,");
        Serial.print(formatTime(millis() - debsession));
        Serial.print(",");
        Serial.println(duration);

        // Gate HIGH pendant toute la durée → le 33250A génère en continu
        // Gate LOW → le générateur finit son cycle en cours et s'arrête proprement
        digitalWrite(gatePin, HIGH);
        delay(durationMs);
        digitalWrite(gatePin, LOW);
      }
    }
  }
}
