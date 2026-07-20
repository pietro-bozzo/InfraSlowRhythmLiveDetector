/*
  StandardFirmata + Manual Stim Protocol
  ------------------------------------------------
  Base: StandardFirmata (c) Hans-Christoph Steiner et al.
  Même architecture que SleepStim v4, mais sans logique automatique
  (pas de wake detection, pas de blocs) : la stim est déclenchée
  manuellement en envoyant une durée, depuis un script Python.

  - stimulationPin (11) : gate vers Agilent 33250A (Trig In panneau arrière)
      Générateur en mode Burst -> Gated. HIGH tant que la stim est active.

  ── COMMANDES SYSEX CUSTOM ────────────────────────────────────────────────────
    Plage 0x7D-0x7F réservée à l'usage utilisateur dans Firmata :
      SYSEX_CMD_START (0x7F) : démarre la session
      SYSEX_CMD_STOP  (0x7E) : coupe le gate si actif + arrête la session
      SYSEX_CMD_STIM  (0x7D) : déclenche une stim manuelle
          payload = 2 octets Firmata (7 bits chacun) encodant la durée
          en CENTISECONDES (LSB, MSB) -> duration_ms = (lsb | msb<<7) * 10
          ex: 0.5s = 50 cs -> lsb=50, msb=0

    Aucun risque de collision avec les paquets Firmata binaires normaux :
    le plugin ArduinoOutput continue de voir un Arduino Firmata standard.

  ── SÉCURITÉ ───────────────────────────────────────────────────────────────────
    MAX_STIM_DURATION_MS : clamp dur, aucune stim ne peut dépasser cette durée
    même si une valeur aberrante est envoyée par erreur.
    Envoyer STOP à tout moment coupe le gate immédiatement (non-bloquant,
    aucun delay() n'est utilisé nulle part dans ce sketch).

  ── LOG SÉRIE ────────────────────────────────────────────────────────────────
    SESSION_START,<t>
    STIM_START,<t>,duration_ms=<n>
    STIM_END,<t>
    STIM_ABORT,<t>,reason=<...>
    SESSION_STOP,<t>
*/

#include <Servo.h>
#include <Wire.h>
#include <Firmata.h>

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

// ── Commandes SysEx custom ─────────────────────────────────────────────────────
#define SYSEX_CMD_START  0x7F
#define SYSEX_CMD_STOP   0x7E
#define SYSEX_CMD_STIM   0x7D

// ── Broches ───────────────────────────────────────────────────────────────────
#define stimulationPin  11

// ── Sécurité ──────────────────────────────────────────────────────────────────
#define MAX_STIM_DURATION_MS  1000UL   // 1s max, ajuster si besoin

// ── États ─────────────────────────────────────────────────────────────────────
bool          sessionActive = false;
unsigned long sessionStart  = 0;

bool          stimActive    = false;
unsigned long stimStartTime = 0;
unsigned long stimEndTime   = 0;

// ── Variables Firmata (boilerplate standard) ──────────────────────────────────
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
  static char buf[12];
  unsigned long s = ms / 1000;
  sprintf(buf, "%02lu:%02lu.%03lu", s / 60, s % 60, ms % 1000);
  return buf;
}

// ── LOG ───────────────────────────────────────────────────────────────────────
void logSessionStart(unsigned long now) { Serial.print("SESSION_START,"); Serial.println(formatTime(now - sessionStart)); }
void logSessionStop(unsigned long now)  { Serial.print("SESSION_STOP,");  Serial.println(formatTime(now - sessionStart)); }
void logStimStart(unsigned long now, unsigned long duration_ms) {
  Serial.print("STIM_START,"); Serial.print(formatTime(now - sessionStart));
  Serial.print(",duration_ms="); Serial.println(duration_ms);
}
void logStimEnd(unsigned long now) { Serial.print("STIM_END,"); Serial.println(formatTime(now - sessionStart)); }
void logStimAbort(unsigned long now, const char* reason) {
  Serial.print("STIM_ABORT,"); Serial.print(formatTime(now - sessionStart));
  Serial.print(",reason="); Serial.println(reason);
}

// ── Logique de stim manuelle (non-bloquante) ──────────────────────────────────
void startStim(unsigned long duration_ms) {
  unsigned long now = millis();
  stimStartTime = now;
  stimEndTime   = now + duration_ms;
  stimActive    = true;
  digitalWrite(stimulationPin, HIGH);
  logStimStart(now, duration_ms);
}

void abortStim(const char* reason) {
  if (stimActive) {
    digitalWrite(stimulationPin, LOW);
    stimActive = false;
    logStimAbort(millis(), reason);
  }
}

// À appeler à chaque loop() : coupe le gate quand la durée est écoulée
void updateStimLogic() {
  if (stimActive && millis() >= stimEndTime) {
    digitalWrite(stimulationPin, LOW);
    stimActive = false;
    logStimEnd(millis());
  }
}

/*==============================================================================
 * FONCTIONS FIRMATA (boilerplate standard, inchangé)
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
 * SYSEX — inclut les commandes custom START / STOP / STIM
 *============================================================================*/
void sysexCallback(byte command, byte argc, byte *argv) {
  byte mode, stopTX, slaveAddress, data; int slaveRegister; unsigned int delayTime;

  // ── START ─────────────────────────────────────────────────────────────────
  if (command == SYSEX_CMD_START) {
    if (!sessionActive) {
      sessionActive = true;
      sessionStart  = millis();
      logSessionStart(sessionStart);
    }
    return;
  }

  // ── STOP : coupe une stim en cours + termine la session ─────────────────────
  if (command == SYSEX_CMD_STOP) {
    abortStim("manual_stop");
    if (sessionActive) logSessionStop(millis());
    sessionActive = false;
    return;
  }

  // ── STIM : déclenche une stim manuelle de <duration_cs> centisecondes ───────
  if (command == SYSEX_CMD_STIM) {
    if (!sessionActive) { Serial.println("# ERR: session inactive, envoyer START d'abord"); return; }
    if (stimActive)     { Serial.println("# ERR: stim deja active, envoyer STOP d'abord"); return; }
    if (argc < 2) return;

    unsigned int  duration_cs = argv[0] | (argv[1] << 7);
    unsigned long duration_ms = (unsigned long)duration_cs * 10UL;
    if (duration_ms == 0) return;

    if (duration_ms > MAX_STIM_DURATION_MS) {
      Serial.println("# WARNING: duree clampee au max autorise");
      duration_ms = MAX_STIM_DURATION_MS;
    }
    startStim(duration_ms);
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

  digitalWrite(stimulationPin, LOW);
  sessionActive = false;
  sessionStart  = 0;
  stimActive    = false;
  stimStartTime = 0;
  stimEndTime   = 0;

  isResetting = false;
}

/*==============================================================================
 * SETUP
 *============================================================================*/
void setup() {
  pinMode(stimulationPin, OUTPUT);
  digitalWrite(stimulationPin, LOW);

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

  Serial.println("# Manual Stim ready — SysEx : START(0x7F) | STOP(0x7E) | STIM(0x7D, duration_cs)");
}

/*==============================================================================
 * LOOP
 *============================================================================*/
void loop() {
  byte pin, analogPin;

  checkDigitalInputs();

  while (Firmata.available())
    Firmata.processInput();

  updateStimLogic();  // non-bloquant : coupe le gate quand la duree est ecoulee

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
}
