/*
  StandardFirmata + Sleep Stimulation Protocol v4
  ------------------------------------------------
  - instructionPin (13) : TTL entrant OpenEphys
      Signal continu HIGH = rat éveillé (avec logique anti-bruit)
      LOW  = rat immobile

  - stimulationPin (11) : gate vers Agilent 33250A (Trig In panneau arrière)
      Générateur en mode Burst → Gated.

  ── DÉTECTION DU RÉVEIL (anti-bruit) ─────────────────────────────────────────
    Un TTL HIGH est confirmé comme "réveil" seulement si :
      - Il dure au moins WAKE_MIN_DURATION_MS (2 s) en continu, OU
      - Un autre TTL HIGH survient dans WAKE_REFRACTORY_MS (5 s) après le
        premier front montant.
    Tout TTL court et isolé est ignoré.

  ── PHASES DU PROTOCOLE ──────────────────────────────────────────────────────
    Phase 1 — IDLE      : attente du START (envoyé via SysEx par Python)
    Phase 2 — BASELINE  : accumulation de 1h d'immobilité cumulée, sans stim
    Phase 3 — STIM      : protocole de stimulation

  ── PHASE STIM ───────────────────────────────────────────────────────────────
    À chaque période d'immobilité :
      1. Attendre 120 s d'immobilité CONTINUE (PRE_STIM_WAIT_MS)
      2. Tirer un bloc au hasard parmi A, B, C, D
      3. Exécuter le bloc complet
      4. Pause fixe de 10 s (INTER_BLOCK_PAUSE_MS)
      5. Retour à 1
    Réveil confirmé → gate LOW, retour à 1 au prochain endormissement
    (nouveau bloc tiré, on ne reprend pas un bloc interrompu)

  ── DÉFINITION DES BLOCS ─────────────────────────────────────────────────────
    Bloc A : liste [100,150,200,300] ms mélangée aléatoirement,
             chaque élément x → stim x ms + pause 60 000 ms (4 éléments)
    Bloc B : 10 × (100 ms ON + 5 000 ms OFF)
    Bloc C : 10 × (100 ms ON + 10 000 ms OFF)
    Bloc D : 10 × (100 ms ON + 20 000 ms OFF)

  ── COMMANDE DE DÉMARRAGE ────────────────────────────────────────────────────
    Le script Python envoie un message SysEx custom pour démarrer la session :
      0xF0  START_SYSEX
      0x7F  commande custom SYSEX_CMD_START (réservé utilisateur dans Firmata)
      0xF7  END_SYSEX
    → Aucun risque de collision avec les paquets Firmata binaires normaux.

  ── LOG SÉRIE ────────────────────────────────────────────────────────────────
    SESSION_START,<t>
    BASELINE_START,<t>,target_ms=<n>
    BASELINE_PROGRESS,<t>,cumul_ms=<n>
    BASELINE_DONE,<t>
    SLEEP_START,<t>
    SLEEP_END,<t>
    BLOCK_WAIT,<t>
    BLOCK_START,<t>,block=<A|B|C|D>
    STIM_START,<t>,block=<A|B|C|D>,on_ms=<n>,off_ms=<n>,rep=<i>/<total>
    STIM_END,<t>,block=<A|B|C|D>,on_ms=<n>,duration_ms=<réel>
    BLOCK_END,<t>,block=<A|B|C|D>
    INTER_BLOCK_PAUSE,<t>
    SESSION_STOP,<t>

  ── CONFIGURATION ─────────────────────────────────────────────────────────────
    Tous les paramètres ajustables (broches, durées, blocs de stimulation) sont
    définis dans SleepStim_CONFIG.h. Ne modifiez QUE ce fichier entre les
    sessions. Ce fichier .ino ne doit pas être modifié.

  Base : StandardFirmata (c) Hans-Christoph Steiner et al.
*/

#include <Servo.h>
#include <Wire.h>
#include <Firmata.h>

// ── Configuration externe (broches, durées, blocs) ───────────────────────────
// Le fichier SleepStim_CONFIG.h doit être placé dans le même dossier que ce
// sketch (l'IDE Arduino l'affichera comme un second onglet).
#include "SleepStim_CONFIG.h"

#define I2C_WRITE                   B00000000
#define I2C_READ                    B00001000
#define I2C_READ_CONTINUOUSLY       B00010000
#define I2C_STOP_READING            B00011000
#define I2C_READ_WRITE_MODE_MASK    B00011000
#define I2C_10BIT_ADDRESS_MODE_MASK B00100000
#define I2C_END_TX_MASK             B01000000
#define I2C_STOP_TX                 1
#define I2C_RESTART_TX              0
#define I2C_MAX_QUERIES             8
#define I2C_REGISTER_NOT_SPECIFIED  -1
#define MINIMUM_SAMPLING_INTERVAL   1

// ── États ─────────────────────────────────────────────────────────────────────
enum ProgPhase { PHASE_IDLE, PHASE_BASELINE, PHASE_STIM };

enum StimState {
  SS_AWAKE,        // réveil confirmé (ou avant premier endormissement)
  SS_PRE_WAIT,     // immobile, décompte 120 s
  SS_BLOCK_ON,     // gate HIGH
  SS_BLOCK_OFF,    // pause intra-bloc
  SS_INTER_PAUSE   // pause 10 s entre blocs
};

// ── Variables principales ─────────────────────────────────────────────────────
ProgPhase     progPhase     = PHASE_IDLE;
StimState     stimState     = SS_AWAKE;

// Logique fenetre glissante
volatile bool ttlRaw         = false;
bool          wakeConfirmed  = false;
bool          ttlWasHigh     = false;
unsigned long prewakeSinceMs = 0;    // debut du pre_wake continu (0 = pas en pre_wake)
unsigned long noprewakeSinceMs = 0;  // debut de l absence de pre_wake (0 = en pre_wake)

// Historique TTL pour integration : tableau circulaire de (start_ms, end_ms)
#define TTL_HISTORY_SIZE  20
unsigned long ttlHistStart[TTL_HISTORY_SIZE];
unsigned long ttlHistEnd[TTL_HISTORY_SIZE];
uint8_t       ttlHistCount = 0;
uint8_t       ttlHistHead  = 0;   // index du plus ancien element
unsigned long currentTTLStart = 0; // debut du TTL en cours (0 si pas de TTL actif)

bool stimulationEnabled = true;
bool emergencyPaused = false;


// Baseline
unsigned long baselineCumulMs   = 0;
unsigned long baselineLastOnset = 0;
unsigned long baselineLastLog   = 0;

// Stimulation
unsigned long sleepOnsetTime  = 0;
unsigned long stimPhaseStart  = 0;
unsigned long stimOnStart     = 0;

// Bloc courant
char          currentBlock  = ' ';
uint8_t       blockRepTotal = 0;
uint8_t       blockRepIdx   = 0;
unsigned long blockOnMs     = 0;
unsigned long blockOffMs    = 0;
// Bloc A : ordre mélangé des 4 durées
unsigned long blockAOrder[4];

// Session
unsigned long sessionStart   = 0;
bool          sessionStarted = false;
bool syncReceived = false;

// ── Variables Firmata ─────────────────────────────────────────────────────────
#ifdef FIRMATA_SERIAL_FEATURE
SerialFirmata serialFeature;
#endif
int  analogInputsToReport = 0;
byte reportPINs[TOTAL_PORTS];
byte previousPINs[TOTAL_PORTS];
byte portConfigInputs[TOTAL_PORTS];
unsigned long currentMillis;
unsigned long previousMillis;
unsigned int  samplingInterval = 19;
struct i2c_device_info { byte addr; int reg; byte bytes; byte stopTX; };
i2c_device_info query[I2C_MAX_QUERIES];
byte        i2cRxData[64];
boolean     isI2CEnabled     = false;
signed char queryIndex       = -1;
unsigned int i2cReadDelayTime = 0;
Servo   servos[MAX_SERVOS];
byte    servoPinMap[TOTAL_PINS];
byte    detachedServos[MAX_SERVOS];
byte    detachedServoCount = 0;
byte    servoCount         = 0;
boolean isResetting        = false;

void setPinModeCallback(byte, int);
void reportAnalogCallback(byte, int);
void sysexCallback(byte, byte, byte*);

// ── Utilitaires ───────────────────────────────────────────────────────────────
void wireWrite(byte data) {
#if ARDUINO >= 100
  Wire.write((byte)data);
#else
  Wire.send(data);
#endif
}
byte wireRead(void) {
#if ARDUINO >= 100
  return Wire.read();
#else
  return Wire.receive();
#endif
}

const char* formatTime(unsigned long ms) {
  static char buf[12];  // static : alloué une fois, persiste entre les appels
  unsigned long s = ms / 1000;
  sprintf(buf, "%02lu:%02lu.%03lu", s / 60, s % 60, ms % 1000);
  return buf;           // retourne un pointeur, pas une copie
}

// ── LOG ───────────────────────────────────────────────────────────────────────
void logSleepStart(unsigned long now)    { Serial.print("SLEEP_START,");       Serial.println(formatTime(now - sessionStart)); }
void logSleepEnd(unsigned long now)      { Serial.print("SLEEP_END,");         Serial.println(formatTime(now - sessionStart)); }
void logBaselineDone(unsigned long now)  { Serial.print("BASELINE_DONE,");     Serial.println(formatTime(now - sessionStart)); }
void logBlockWait(unsigned long now)     { Serial.print("BLOCK_WAIT,");        Serial.println(formatTime(now - sessionStart)); }
void logInterBlockPause(unsigned long now){ Serial.print("INTER_BLOCK_PAUSE,");Serial.println(formatTime(now - sessionStart)); }

void logBaselineProgress(unsigned long now) {
  Serial.print("BASELINE_PROGRESS,"); Serial.print(formatTime(now - sessionStart));
  Serial.print(",cumul_ms=");         Serial.println(baselineCumulMs);
}
void logBlockStart(unsigned long now) {
  Serial.print("BLOCK_START,"); Serial.print(formatTime(now - sessionStart));
  Serial.print(",block=");      Serial.println(currentBlock);
}
void logBlockEnd(unsigned long now) {
  Serial.print("BLOCK_END,"); Serial.print(formatTime(now - sessionStart));
  Serial.print(",block=");     Serial.println(currentBlock);
}
void logStimStart(unsigned long now) {
  Serial.print("STIM_START,");  Serial.print(formatTime(now - sessionStart));
  Serial.print(",block=");      Serial.print(currentBlock);
  Serial.print(",on_ms=");      Serial.print(blockOnMs);
  Serial.print(",off_ms=");     Serial.print(blockOffMs);
  Serial.print(",rep=");        Serial.print(blockRepIdx + 1);
  Serial.print("/");            Serial.println(blockRepTotal);
}
void logStimEnd(unsigned long now) {
  Serial.print("STIM_END,");    Serial.print(formatTime(now - sessionStart));
  Serial.print(",block=");      Serial.print(currentBlock);
  Serial.print(",on_ms=");      Serial.print(blockOnMs);
  Serial.print(",duration_ms=");Serial.println(now - stimOnStart);
}

// ── Logique anti-bruit réveil ─────────────────────────────────────────────────
// Appelée à chaque loop(). Met à jour wakeConfirmed et stimulationEnabled.
void updateWakeLogic() {
  unsigned long now = millis();
  bool currentTTL = ttlRaw;

  bool risingEdge  = currentTTL  && !ttlWasHigh;
  bool fallingEdge = !currentTTL && ttlWasHigh;
  ttlWasHigh = currentTTL;

  // ── Mise a jour de l historique TTL ──────────────────────────────────────
  if (risingEdge) {
    currentTTLStart = now;
  }
  if (fallingEdge && currentTTLStart > 0) {
    // Stocker l intervalle TTL termine dans l historique circulaire
    uint8_t idx = (ttlHistHead + ttlHistCount) % TTL_HISTORY_SIZE;
    if (ttlHistCount < TTL_HISTORY_SIZE) {
      ttlHistStart[idx] = currentTTLStart;
      ttlHistEnd[idx]   = now;
      ttlHistCount++;
    } else {
      // Buffer plein : ecraser le plus ancien
      ttlHistStart[ttlHistHead] = currentTTLStart;
      ttlHistEnd[ttlHistHead]   = now;
      ttlHistHead = (ttlHistHead + 1) % TTL_HISTORY_SIZE;
    }
    currentTTLStart = 0;
  }

  // ── Integration TTL dans la fenetre [now - WINDOW_MS, now] ───────────────
  unsigned long windowStart = (now > WINDOW_MS) ? now - WINDOW_MS : 0;
  unsigned long integral    = 0;

  // TTL termines dans l historique
  for (uint8_t i = 0; i < ttlHistCount; i++) {
    uint8_t idx = (ttlHistHead + i) % TTL_HISTORY_SIZE;
    unsigned long ts = ttlHistStart[idx];
    unsigned long te = ttlHistEnd[idx];
    if (te < windowStart) continue;   // hors fenetre
    unsigned long os = max(ts, windowStart);
    unsigned long oe = min(te, now);
    if (oe > os) integral += oe - os;
  }

  // TTL en cours (pas encore termine)
  if (currentTTL && currentTTLStart > 0) {
    unsigned long os = max(currentTTLStart, windowStart);
    integral += now - os;
  }

  // ── Logique pre_wake -> wake_confirmed ────────────────────────────────────
  bool pre_wake = (integral > K_MS);

  if (pre_wake) {
    noprewakeSinceMs = 0;
    if (prewakeSinceMs == 0) prewakeSinceMs = now;
    if (now - prewakeSinceMs >= PRE_WAKE_CONFIRM_MS) wakeConfirmed = true;
  } else {
    prewakeSinceMs = 0;
    if (noprewakeSinceMs == 0) noprewakeSinceMs = now;
    if (wakeConfirmed && (now - noprewakeSinceMs >= SLEEP_CONFIRM_MS)) {
      wakeConfirmed = false;
    }
  }

  // Nettoyage historique : supprimer entrees hors fenetre
  while (ttlHistCount > 0) {
    if (ttlHistEnd[ttlHistHead] < windowStart) {
      ttlHistHead = (ttlHistHead + 1) % TTL_HISTORY_SIZE;
      ttlHistCount--;
    } else break;
  }

  stimulationEnabled = !wakeConfirmed;
}

// ── Gestion des blocs ─────────────────────────────────────────────────────────
// Mélange Fisher-Yates du tableau blockAOrder
void shuffleBlockA() {
  for (int i = 0; i < 4; i++) blockAOrder[i] = BLOCK_A_DURATIONS[i];
  for (int i = 3; i > 0; i--) {
    int j = random(i + 1);
    unsigned long tmp = blockAOrder[i];
    blockAOrder[i] = blockAOrder[j];
    blockAOrder[j] = tmp;
  }
}

void pickRandomBlock() {
  uint8_t r = random(4);
  blockRepIdx = 0;
  if (r == 0) {
    currentBlock  = 'A';
    blockRepTotal = BLOCK_A_REPS;
    shuffleBlockA();
    blockOnMs  = blockAOrder[0];
    blockOffMs = BLOCK_A_OFF_MS;
  } else if (r == 1) {
    currentBlock  = 'B';
    blockRepTotal = BLOCK_B_REPS;
    blockOnMs     = BLOCK_B_ON_MS;
    blockOffMs    = BLOCK_B_OFF_MS;
  } else if (r == 2) {
    currentBlock  = 'C';
    blockRepTotal = BLOCK_C_REPS;
    blockOnMs     = BLOCK_C_ON_MS;
    blockOffMs    = BLOCK_C_OFF_MS;
  } else {
    currentBlock  = 'D';
    blockRepTotal = BLOCK_D_REPS;
    blockOnMs     = BLOCK_D_ON_MS;
    blockOffMs    = BLOCK_D_OFF_MS;
  }
}

void startBlock(unsigned long now) {

  if (emergencyPaused) {
    digitalWrite(stimulationPin, LOW);
    return;
  }

  logBlockStart(now);
  stimPhaseStart = now;
  stimOnStart    = now;
  stimState      = SS_BLOCK_ON;

  digitalWrite(stimulationPin, HIGH);
  logStimStart(now);
}

// ------ Logique d'arrêt d'urgence pour la stim ------------------------------
void emergencyPause(unsigned long now) {
  // Coupure physique immédiate de la stimulation
  digitalWrite(stimulationPin, LOW);

  // Si une stimulation était réellement en cours, enregistrer sa fin
  if (stimState == SS_BLOCK_ON) {
    logStimEnd(now);
  }

  emergencyPaused = true;

  // Le bloc courant est abandonné
  stimState      = SS_AWAKE;
  currentBlock   = ' ';
  blockRepIdx    = 0;
  blockRepTotal  = 0;
  blockOnMs      = 0;
  blockOffMs     = 0;

  Serial.print("EMERGENCY_PAUSE,");
  if (sessionStarted) {
    Serial.println(formatTime(now - sessionStart));
  } else {
    Serial.println("00:00.000");
  }
}

void emergencyResume(unsigned long now) {
  // Maintenir la sortie LOW pendant la reprise
  digitalWrite(stimulationPin, LOW);

  emergencyPaused = false;

  /*
   * On ne reprend jamais une stimulation ou un bloc interrompu.
   * On repart avec un nouveau délai de PRE_STIM_WAIT_MS.
   */
  if (progPhase == PHASE_STIM) {
    sleepOnsetTime = now;
    stimPhaseStart = now;
    stimState      = SS_PRE_WAIT;

    Serial.print("EMERGENCY_RESUME,");
    Serial.println(formatTime(now - sessionStart));

    logBlockWait(now);
  } else {
    Serial.print("EMERGENCY_RESUME,");
    if (sessionStarted) {
      Serial.println(formatTime(now - sessionStart));
    } else {
      Serial.println("00:00.000");
    }
  }
}

// ── Logique baseline ──────────────────────────────────────────────────────────
void baselineLogic() {
  unsigned long now = millis();

  if (!stimulationEnabled) {
    // Rat éveillé : arrêter d'accumuler
    if (baselineLastOnset > 0) {
      baselineCumulMs  += (now - baselineLastOnset);
      baselineLastOnset = 0;
    }
    return;
  }

  // Rat immobile
  if (baselineLastOnset == 0) baselineLastOnset = now;

  unsigned long currentCumul = baselineCumulMs + (now - baselineLastOnset);

  if (currentCumul - baselineLastLog >= BASELINE_LOG_INTERVAL) {
    baselineLastLog = currentCumul;
    unsigned long saved = baselineCumulMs;
    baselineCumulMs = currentCumul;
    logBaselineProgress(now);
    baselineCumulMs = saved;
  }

  if (currentCumul >= BASELINE_CUMUL_MS) {
    baselineCumulMs = currentCumul;
    logBaselineDone(now);
    progPhase      = PHASE_STIM;
    sleepOnsetTime = now;
    stimState      = SS_PRE_WAIT;
    logBlockWait(now);
  }
}

// ── Logique stimulation ───────────────────────────────────────────────────────
void stimulationLogic() {
  unsigned long now = millis();

  // Réveil confirmé
  if (!stimulationEnabled) {
    if (stimState != SS_AWAKE) {
      if (stimState == SS_BLOCK_ON) {
        digitalWrite(stimulationPin, LOW);
        logStimEnd(now);
        logBlockEnd(now);   // bloc interrompu, sera retitré au réveil
      }
      stimState = SS_AWAKE;
      logSleepEnd(now);
    }
    return;
  }

  // Retour à l'immobilité
  if (stimState == SS_AWAKE) {
    sleepOnsetTime = now;
    stimState      = SS_PRE_WAIT;
    logSleepStart(now);
    logBlockWait(now);
    return;
  }

  unsigned long elapsed = now - stimPhaseStart;

  switch (stimState) {

    case SS_PRE_WAIT:
      if (now - sleepOnsetTime >= PRE_STIM_WAIT_MS) {
        pickRandomBlock();
        startBlock(now);
      }
      break;

    case SS_BLOCK_ON:
      if (elapsed >= blockOnMs) {
        digitalWrite(stimulationPin, LOW);
        logStimEnd(now);
        stimPhaseStart = now;
        if (blockRepIdx >= blockRepTotal - 1) {
          logBlockEnd(now);
          logInterBlockPause(now);
          stimState = SS_INTER_PAUSE;
        } else {
          stimState = SS_BLOCK_OFF;
        }
      }
      break;

    case SS_BLOCK_OFF:
      if (elapsed >= blockOffMs) {
        blockRepIdx++;
        // Bloc A : prendre la prochaine durée de l'ordre mélangé
        if (currentBlock == 'A') {
          blockOnMs  = blockAOrder[blockRepIdx];
          blockOffMs = BLOCK_A_OFF_MS;
        }
        if (emergencyPaused) {
          digitalWrite(stimulationPin, LOW);
          stimState = SS_AWAKE;
          return;
        }
        stimPhaseStart = now;
        stimOnStart    = now;
        stimState      = SS_BLOCK_ON;
        digitalWrite(stimulationPin, HIGH);
        logStimStart(now);
      }
      break;

    case SS_INTER_PAUSE:
      if (elapsed >= INTER_BLOCK_PAUSE_MS) {
        sleepOnsetTime = now;
        stimPhaseStart = now;
        stimState      = SS_PRE_WAIT;
        logBlockWait(now);
      }
      break;

    default: break;
  }
}

/*==============================================================================
 * FONCTIONS FIRMATA
 *============================================================================*/
void attachServo(byte pin, int minPulse, int maxPulse) {
  if (servoCount < MAX_SERVOS) {
    if (detachedServoCount > 0) {
      servoPinMap[pin] = detachedServos[detachedServoCount - 1];
      if (detachedServoCount > 0) detachedServoCount--;
    } else {
      servoPinMap[pin] = servoCount;
      servoCount++;
    }
    if (minPulse > 0 && maxPulse > 0)
      servos[servoPinMap[pin]].attach(PIN_TO_DIGITAL(pin), minPulse, maxPulse);
    else
      servos[servoPinMap[pin]].attach(PIN_TO_DIGITAL(pin));
  } else { Firmata.sendString("Max servos attached"); }
}

void detachServo(byte pin) {
  servos[servoPinMap[pin]].detach();
  if (servoPinMap[pin] == servoCount && servoCount > 0) servoCount--;
  else if (servoCount > 0) { detachedServoCount++; detachedServos[detachedServoCount - 1] = servoPinMap[pin]; }
  servoPinMap[pin] = 255;
}

void enableI2CPins() {
  for (byte i = 0; i < TOTAL_PINS; i++) if (IS_PIN_I2C(i)) setPinModeCallback(i, PIN_MODE_I2C);
  isI2CEnabled = true; Wire.begin();
}
void disableI2CPins() { isI2CEnabled = false; queryIndex = -1; }

void readAndReportData(byte address, int theRegister, byte numBytes, byte stopTX) {
  if (theRegister != I2C_REGISTER_NOT_SPECIFIED) {
    Wire.beginTransmission(address); wireWrite((byte)theRegister);
    Wire.endTransmission(stopTX);
    if (i2cReadDelayTime > 0) delayMicroseconds(i2cReadDelayTime);
  } else { theRegister = 0; }
  Wire.requestFrom(address, numBytes);
  if (numBytes < Wire.available()) Firmata.sendString("I2C: Too many bytes received");
  else if (numBytes > Wire.available()) { Firmata.sendString("I2C: Too few bytes received"); numBytes = Wire.available(); }
  i2cRxData[0] = address; i2cRxData[1] = theRegister;
  for (int i = 0; i < numBytes && Wire.available(); i++) i2cRxData[2 + i] = wireRead();
  Firmata.sendSysex(SYSEX_I2C_REPLY, numBytes + 2, i2cRxData);
}

void outputPort(byte portNumber, byte portValue, byte forceSend) {
  portValue = portValue & portConfigInputs[portNumber];
  if (forceSend || previousPINs[portNumber] != portValue) {
    Firmata.sendDigitalPort(portNumber, portValue);
    previousPINs[portNumber] = portValue;
  }
}

void checkDigitalInputs(void) {
  if (TOTAL_PORTS > 0  && reportPINs[0])  outputPort(0,  readPort(0,  portConfigInputs[0]),  false);
  if (TOTAL_PORTS > 1  && reportPINs[1])  outputPort(1,  readPort(1,  portConfigInputs[1]),  false);
  if (TOTAL_PORTS > 2  && reportPINs[2])  outputPort(2,  readPort(2,  portConfigInputs[2]),  false);
  if (TOTAL_PORTS > 3  && reportPINs[3])  outputPort(3,  readPort(3,  portConfigInputs[3]),  false);
  if (TOTAL_PORTS > 4  && reportPINs[4])  outputPort(4,  readPort(4,  portConfigInputs[4]),  false);
  if (TOTAL_PORTS > 5  && reportPINs[5])  outputPort(5,  readPort(5,  portConfigInputs[5]),  false);
  if (TOTAL_PORTS > 6  && reportPINs[6])  outputPort(6,  readPort(6,  portConfigInputs[6]),  false);
  if (TOTAL_PORTS > 7  && reportPINs[7])  outputPort(7,  readPort(7,  portConfigInputs[7]),  false);
  if (TOTAL_PORTS > 8  && reportPINs[8])  outputPort(8,  readPort(8,  portConfigInputs[8]),  false);
  if (TOTAL_PORTS > 9  && reportPINs[9])  outputPort(9,  readPort(9,  portConfigInputs[9]),  false);
  if (TOTAL_PORTS > 10 && reportPINs[10]) outputPort(10, readPort(10, portConfigInputs[10]), false);
  if (TOTAL_PORTS > 11 && reportPINs[11]) outputPort(11, readPort(11, portConfigInputs[11]), false);
  if (TOTAL_PORTS > 12 && reportPINs[12]) outputPort(12, readPort(12, portConfigInputs[12]), false);
  if (TOTAL_PORTS > 13 && reportPINs[13]) outputPort(13, readPort(13, portConfigInputs[13]), false);
  if (TOTAL_PORTS > 14 && reportPINs[14]) outputPort(14, readPort(14, portConfigInputs[14]), false);
  if (TOTAL_PORTS > 15 && reportPINs[15]) outputPort(15, readPort(15, portConfigInputs[15]), false);
}

void setPinModeCallback(byte pin, int mode) {
  if (Firmata.getPinMode(pin) == PIN_MODE_IGNORE) return;
  if (Firmata.getPinMode(pin) == PIN_MODE_I2C && isI2CEnabled && mode != PIN_MODE_I2C) disableI2CPins();
  if (IS_PIN_DIGITAL(pin) && mode != PIN_MODE_SERVO)
    if (servoPinMap[pin] < MAX_SERVOS && servos[servoPinMap[pin]].attached()) detachServo(pin);
  if (IS_PIN_ANALOG(pin)) reportAnalogCallback(PIN_TO_ANALOG(pin), mode == PIN_MODE_ANALOG ? 1 : 0);
  if (IS_PIN_DIGITAL(pin)) {
    if (mode == INPUT || mode == PIN_MODE_PULLUP) portConfigInputs[pin / 8] |=  (1 << (pin & 7));
    else                                          portConfigInputs[pin / 8] &= ~(1 << (pin & 7));
  }
  Firmata.setPinState(pin, 0);
  switch (mode) {
    case PIN_MODE_ANALOG:
      if (IS_PIN_ANALOG(pin)) {
        if (IS_PIN_DIGITAL(pin)) { pinMode(PIN_TO_DIGITAL(pin), INPUT);
#if ARDUINO <= 100
          digitalWrite(PIN_TO_DIGITAL(pin), LOW);
#endif
        }
        Firmata.setPinMode(pin, PIN_MODE_ANALOG);
      } break;
    case INPUT:
      if (IS_PIN_DIGITAL(pin)) { pinMode(PIN_TO_DIGITAL(pin), INPUT);
#if ARDUINO <= 100
        digitalWrite(PIN_TO_DIGITAL(pin), LOW);
#endif
        Firmata.setPinMode(pin, INPUT);
      } break;
    case PIN_MODE_PULLUP:
      if (IS_PIN_DIGITAL(pin)) { pinMode(PIN_TO_DIGITAL(pin), INPUT_PULLUP); Firmata.setPinMode(pin, PIN_MODE_PULLUP); Firmata.setPinState(pin, 1); } break;
    case OUTPUT:
      if (IS_PIN_DIGITAL(pin)) {
        if (Firmata.getPinMode(pin) == PIN_MODE_PWM) digitalWrite(PIN_TO_DIGITAL(pin), LOW);
        pinMode(PIN_TO_DIGITAL(pin), OUTPUT); Firmata.setPinMode(pin, OUTPUT);
      } break;
    case PIN_MODE_PWM:
      if (IS_PIN_PWM(pin)) { pinMode(PIN_TO_PWM(pin), OUTPUT); analogWrite(PIN_TO_PWM(pin), 0); Firmata.setPinMode(pin, PIN_MODE_PWM); } break;
    case PIN_MODE_SERVO:
      if (IS_PIN_DIGITAL(pin)) {
        Firmata.setPinMode(pin, PIN_MODE_SERVO);
        if (servoPinMap[pin] == 255 || !servos[servoPinMap[pin]].attached()) attachServo(pin, -1, -1);
      } break;
    case PIN_MODE_I2C:
      if (IS_PIN_I2C(pin)) Firmata.setPinMode(pin, PIN_MODE_I2C); break;
    case PIN_MODE_SERIAL:
#ifdef FIRMATA_SERIAL_FEATURE
      serialFeature.handlePinMode(pin, PIN_MODE_SERIAL);
#endif
      break;
    default: Firmata.sendString("Unknown pin mode");
  }
}

void setPinValueCallback(byte pin, int value) {
  if (pin < TOTAL_PINS && IS_PIN_DIGITAL(pin))
    if (Firmata.getPinMode(pin) == OUTPUT) { Firmata.setPinState(pin, value); digitalWrite(PIN_TO_DIGITAL(pin), value); }
}

void analogWriteCallback(byte pin, int value) {
  if (pin < TOTAL_PINS) {
    switch (Firmata.getPinMode(pin)) {
      case PIN_MODE_SERVO: if (IS_PIN_DIGITAL(pin)) servos[servoPinMap[pin]].write(value); Firmata.setPinState(pin, value); break;
      case PIN_MODE_PWM:   if (IS_PIN_PWM(pin))     analogWrite(PIN_TO_PWM(pin), value);   Firmata.setPinState(pin, value); break;
    }
  }
}

void digitalWriteCallback(byte port, int value) {
  byte pin, lastPin, pinValue, mask = 1, pinWriteMask = 0;
  if (port < TOTAL_PORTS) {
    lastPin = port * 8 + 8;
    if (lastPin > TOTAL_PINS) lastPin = TOTAL_PINS;
    for (pin = port * 8; pin < lastPin; pin++) {
      if (IS_PIN_DIGITAL(pin)) {
        if (Firmata.getPinMode(pin) == OUTPUT || Firmata.getPinMode(pin) == INPUT) {
          pinValue = ((byte)value & mask) ? 1 : 0;
          // Met à jour le TTL brut — la logique anti-bruit est dans updateWakeLogic()
          if (pin == instructionPin && syncReceived) ttlRaw = (pinValue == 1);
          if (pin == syncPin && pinValue == 1 && !syncReceived && progPhase == PHASE_IDLE) {
            syncReceived   = true;
            unsigned long now = millis();
            sessionStart   = now;
            sessionStarted = true;
            progPhase      = PHASE_BASELINE;
            baselineLastLog = 0;
            emergencyPaused = false;
            digitalWrite(stimulationPin, LOW);
            Serial.print("SESSION_START,");  Serial.println(formatTime(0));
            Serial.print("BASELINE_START,"); Serial.print(formatTime(0));
            Serial.print(",target_ms=");     Serial.println(BASELINE_CUMUL_MS);
        }
          if (Firmata.getPinMode(pin) == OUTPUT) pinWriteMask |= mask;
          else if (Firmata.getPinMode(pin) == INPUT && pinValue == 1 && Firmata.getPinState(pin) != 1) {
#if ARDUINO > 100
            pinMode(pin, INPUT_PULLUP);
#else
            pinWriteMask |= mask;
#endif
          }
          Firmata.setPinState(pin, pinValue);
        }
      }
      mask = mask << 1;
    }
    writePort(port, (byte)value, pinWriteMask);
  }
}

void reportAnalogCallback(byte analogPin, int value) {
  if (analogPin < TOTAL_ANALOG_PINS) {
    if (value == 0) analogInputsToReport &= ~(1 << analogPin);
    else { analogInputsToReport |= (1 << analogPin); if (!isResetting) Firmata.sendAnalog(analogPin, analogRead(analogPin)); }
  }
}

void reportDigitalCallback(byte port, int value) {
  if (port < TOTAL_PORTS) { reportPINs[port] = (byte)value; if (value) outputPort(port, readPort(port, portConfigInputs[port]), true); }
}

/*==============================================================================
 * SYSEX — inclut la commande custom START
 *============================================================================*/
void sysexCallback(byte command, byte argc, byte *argv) {
  byte mode, stopTX, slaveAddress, data; int slaveRegister; unsigned int delayTime;

  // ── Commande custom START ──────────────────────────────────────────────────
  if (command == SYSEX_CMD_START) {
    if (progPhase == PHASE_IDLE) {
      unsigned long now = millis();
      digitalWrite(stimulationPin, LOW);
      emergencyPaused = false;

      sessionStart    = now;
      sessionStarted  = true;
      progPhase       = PHASE_BASELINE;
      baselineLastLog = 0;

      Serial.print("SESSION_START,");
      Serial.println(formatTime(0));

      Serial.print("BASELINE_START,");
      Serial.print(formatTime(0));

      Serial.print(",target_ms=");
      Serial.println(BASELINE_CUMUL_MS);
    }
    return;
  }
  // ── Arrêt d'urgence prioritaire ───────────────────────────────────────────────
  if (command == SYSEX_CMD_PAUSE) {
    emergencyPause(millis());
    return;
  }

  // ── Reprise après arrêt d'urgence ─────────────────────────────────────────────
  if (command == SYSEX_CMD_RESUME) {
    if (emergencyPaused) {
      emergencyResume(millis());
    }
    return;
  }

  if (command == SYSEX_CMD_STOP) {
    unsigned long now = millis();
    digitalWrite(stimulationPin, LOW);
    if (sessionStarted) {
      Serial.print("SESSION_STOP,");
      Serial.println(formatTime(now - sessionStart));
    }
    progPhase  = PHASE_IDLE;
    stimState  = SS_AWAKE;
    return;
  }

  switch (command) {
    case I2C_REQUEST:
      mode = argv[1] & I2C_READ_WRITE_MODE_MASK;
      if (argv[1] & I2C_10BIT_ADDRESS_MODE_MASK) { Firmata.sendString("10-bit addressing not supported"); return; }
      slaveAddress = argv[0];
      stopTX = (argv[1] & I2C_END_TX_MASK) ? I2C_RESTART_TX : I2C_STOP_TX;
      switch (mode) {
        case I2C_WRITE:
          Wire.beginTransmission(slaveAddress);
          for (byte i = 2; i < argc; i += 2) { data = argv[i] + (argv[i+1] << 7); wireWrite(data); }
          Wire.endTransmission(); delayMicroseconds(70); break;
        case I2C_READ:
          slaveRegister = (argc == 6) ? argv[2] + (argv[3] << 7) : I2C_REGISTER_NOT_SPECIFIED;
          data = (argc == 6) ? argv[4] + (argv[5] << 7) : argv[2] + (argv[3] << 7);
          readAndReportData(slaveAddress, slaveRegister, data, stopTX); break;
        case I2C_READ_CONTINUOUSLY:
          if ((queryIndex + 1) >= I2C_MAX_QUERIES) { Firmata.sendString("too many queries"); break; }
          slaveRegister = (argc == 6) ? argv[2] + (argv[3] << 7) : (int)I2C_REGISTER_NOT_SPECIFIED;
          data = (argc == 6) ? argv[4] + (argv[5] << 7) : argv[2] + (argv[3] << 7);
          queryIndex++; query[queryIndex] = { slaveAddress, slaveRegister, data, stopTX }; break;
        case I2C_STOP_READING: {
          byte skip = 0;
          if (queryIndex <= 0) { queryIndex = -1; }
          else {
            for (byte i = 0; i < queryIndex + 1; i++) if (query[i].addr == slaveAddress) { skip = i; break; }
            for (byte i = skip; i < queryIndex + 1; i++) if (i < I2C_MAX_QUERIES) query[i] = query[i+1];
            queryIndex--;
          }
          break; }
        default: break;
      } break;
    case I2C_CONFIG:
      delayTime = argv[0] + (argv[1] << 7);
      if (argc > 1 && delayTime > 0) i2cReadDelayTime = delayTime;
      if (!isI2CEnabled) enableI2CPins(); break;
    case SERVO_CONFIG:
      if (argc > 4) {
        byte pin = argv[0]; int minP = argv[1]+(argv[2]<<7), maxP = argv[3]+(argv[4]<<7);
        if (IS_PIN_DIGITAL(pin)) { if (servoPinMap[pin]<MAX_SERVOS && servos[servoPinMap[pin]].attached()) detachServo(pin); attachServo(pin,minP,maxP); setPinModeCallback(pin,PIN_MODE_SERVO); }
      } break;
    case SAMPLING_INTERVAL:
      if (argc > 1) { samplingInterval = argv[0]+(argv[1]<<7); if (samplingInterval < MINIMUM_SAMPLING_INTERVAL) samplingInterval = MINIMUM_SAMPLING_INTERVAL; } break;
    case EXTENDED_ANALOG:
      if (argc > 1) { int val=argv[1]; if(argc>2) val|=(argv[2]<<7); if(argc>3) val|=(argv[3]<<14); analogWriteCallback(argv[0],val); } break;
    case CAPABILITY_QUERY:
      Firmata.write(START_SYSEX); Firmata.write(CAPABILITY_RESPONSE);
      for (byte pin = 0; pin < TOTAL_PINS; pin++) {
        if (IS_PIN_DIGITAL(pin)) { Firmata.write((byte)INPUT);Firmata.write(1);Firmata.write((byte)PIN_MODE_PULLUP);Firmata.write(1);Firmata.write((byte)OUTPUT);Firmata.write(1); }
        if (IS_PIN_ANALOG(pin))  { Firmata.write(PIN_MODE_ANALOG);Firmata.write(10); }
        if (IS_PIN_PWM(pin))     { Firmata.write(PIN_MODE_PWM);Firmata.write(DEFAULT_PWM_RESOLUTION); }
        if (IS_PIN_DIGITAL(pin)) { Firmata.write(PIN_MODE_SERVO);Firmata.write(14); }
        if (IS_PIN_I2C(pin))     { Firmata.write(PIN_MODE_I2C);Firmata.write(1); }
#ifdef FIRMATA_SERIAL_FEATURE
        serialFeature.handleCapability(pin);
#endif
        Firmata.write(127);
      }
      Firmata.write(END_SYSEX); break;
    case PIN_STATE_QUERY:
      if (argc > 0) {
        byte pin = argv[0]; Firmata.write(START_SYSEX); Firmata.write(PIN_STATE_RESPONSE); Firmata.write(pin);
        if (pin < TOTAL_PINS) { Firmata.write(Firmata.getPinMode(pin)); Firmata.write((byte)Firmata.getPinState(pin)&0x7F); if(Firmata.getPinState(pin)&0xFF80) Firmata.write((byte)(Firmata.getPinState(pin)>>7)&0x7F); if(Firmata.getPinState(pin)&0xC000) Firmata.write((byte)(Firmata.getPinState(pin)>>14)&0x7F); }
        Firmata.write(END_SYSEX);
      } break;
    case ANALOG_MAPPING_QUERY:
      Firmata.write(START_SYSEX); Firmata.write(ANALOG_MAPPING_RESPONSE);
      for (byte pin=0;pin<TOTAL_PINS;pin++) Firmata.write(IS_PIN_ANALOG(pin)?PIN_TO_ANALOG(pin):127);
      Firmata.write(END_SYSEX); break;
    case SERIAL_MESSAGE:
#ifdef FIRMATA_SERIAL_FEATURE
      serialFeature.handleSysex(command, argc, argv);
#endif
      break;
  }
}

/*==============================================================================
 * SYSTEM RESET
 *============================================================================*/
void systemResetCallback() {
  isResetting = true;
#ifdef FIRMATA_SERIAL_FEATURE
  serialFeature.reset();
#endif
  if (isI2CEnabled) disableI2CPins();
  for (byte i = 0; i < TOTAL_PORTS; i++) { reportPINs[i]=false; portConfigInputs[i]=0; previousPINs[i]=0; }
  for (byte i = 0; i < TOTAL_PINS;  i++) {
    if (IS_PIN_ANALOG(i))       setPinModeCallback(i, PIN_MODE_ANALOG);
    else if (IS_PIN_DIGITAL(i)) setPinModeCallback(i, OUTPUT);
    servoPinMap[i] = 255;
  }
  analogInputsToReport = 0; detachedServoCount = 0; servoCount = 0;

  // Reset TTL / wake logic
  ttlRaw             = false;
  wakeConfirmed      = false;
  ttlWasHigh         = false;
  prewakeSinceMs     = 0;
  noprewakeSinceMs   = 0;
  currentTTLStart    = 0;
  ttlHistCount       = 0;
  ttlHistHead        = 0;
  for (uint8_t k = 0; k < TTL_HISTORY_SIZE; k++) {
    ttlHistStart[k] = 0;
    ttlHistEnd[k]   = 0;
  }
  stimulationEnabled = true;
  emergencyPaused = false;
  syncReceived = false;

  // Reset protocole
  progPhase         = PHASE_IDLE;
  stimState         = SS_AWAKE;
  baselineCumulMs   = 0;
  baselineLastOnset = 0;
  baselineLastLog   = 0;
  sleepOnsetTime    = 0;
  stimPhaseStart    = 0;
  stimOnStart       = 0;
  currentBlock      = ' ';
  blockRepIdx       = 0;
  blockRepTotal     = 0;
  blockOnMs         = 0;
  blockOffMs        = 0;
  sessionStarted    = false;

  isResetting = false;
}

/*==============================================================================
 * SETUP
 *============================================================================*/
void setup() {
  pinMode(stimulationPin, OUTPUT);
  pinMode(syncPin, INPUT);
  digitalWrite(stimulationPin, LOW);
  randomSeed(analogRead(0));

  Firmata.setFirmwareVersion(FIRMATA_FIRMWARE_MAJOR_VERSION, FIRMATA_FIRMWARE_MINOR_VERSION);
  Firmata.attach(ANALOG_MESSAGE,        analogWriteCallback);
  Firmata.attach(DIGITAL_MESSAGE,       digitalWriteCallback);
  Firmata.attach(REPORT_ANALOG,         reportAnalogCallback);
  Firmata.attach(REPORT_DIGITAL,        reportDigitalCallback);
  Firmata.attach(SET_PIN_MODE,          setPinModeCallback);
  Firmata.attach(SET_DIGITAL_PIN_VALUE, setPinValueCallback);
  Firmata.attach(START_SYSEX,           sysexCallback);
  Firmata.attach(SYSTEM_RESET,          systemResetCallback);
  Firmata.begin(57600);
  while (!Serial) { ; }

  systemResetCallback();

  Serial.println("# SleepStim v4 pret — en attente du START (SysEx)");
  Serial.println("# Blocs : A([100,150,200,300]ms x1+60s) | B(10x100ms+5s) | C(10x100ms+10s) | D(10x100ms+20s)");
}

/*==============================================================================
 * LOOP
 *============================================================================*/
void loop() {
  byte pin, analogPin;

  checkDigitalInputs();

  while (Firmata.available())
    Firmata.processInput();

  // Mise à jour de la logique anti-bruit (indépendante de Firmata)
  updateWakeLogic();

  currentMillis = millis();
  if (currentMillis - previousMillis > samplingInterval) {
    previousMillis += samplingInterval;
    for (pin = 0; pin < TOTAL_PINS; pin++) {
      if (IS_PIN_ANALOG(pin) && Firmata.getPinMode(pin) == PIN_MODE_ANALOG) {
        analogPin = PIN_TO_ANALOG(pin);
        if (analogInputsToReport & (1 << analogPin))
          Firmata.sendAnalog(analogPin, analogRead(analogPin));
      }
    }
    if (queryIndex > -1)
      for (byte i = 0; i < queryIndex + 1; i++)
        readAndReportData(query[i].addr, query[i].reg, query[i].bytes, query[i].stopTX);
  }

#ifdef FIRMATA_SERIAL_FEATURE
  serialFeature.update();
#endif
  /*
  * Sécurité prioritaire :
  * pendant une pause d'urgence, la sortie reste forcée à LOW et aucune logique
  * de baseline ou de stimulation n'est exécutée.
  */
  if (emergencyPaused) {
    digitalWrite(stimulationPin, LOW);
    return;
  }

  if (progPhase == PHASE_BASELINE) {
    baselineLogic();
  } else if (progPhase == PHASE_STIM) {
    stimulationLogic();
  }

}
