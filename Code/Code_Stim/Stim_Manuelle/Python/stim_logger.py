"""
stim_manual_sysex.py — terminal de contrôle pour manual_stim_firmata.ino
------------------------------------------------------------------------------
Construit et envoie les trames SysEx custom (START/STOP/STIM) en pyserial brut.
L'Arduino tourne un StandardFirmata étendu -> reste compatible avec le plugin
ArduinoOutput d'Open Ephys (protocole Firmata standard intact), tant que ce
script n'a pas la main sur le port en même temps que le plugin.

Dépendance : pip install pyserial

Usage :
    python stim_manual_sysex.py --port /dev/ttyACM0

Commandes au prompt :
    START       -> démarre la session
    STOP        -> coupe le gate immédiatement si stim en cours, arrête la session
    <duree_s>   -> ex: 0.1  -> stim continue de 100 ms
"""

import argparse
import serial
import threading
import time
import sys

START_SYSEX = 0xF0
END_SYSEX = 0xF7

SYSEX_CMD_START = 0x7F
SYSEX_CMD_STOP = 0x7E
SYSEX_CMD_STIM = 0x7D


def parse_args():
    p = argparse.ArgumentParser(description="Terminal SysEx pour manual_stim_firmata.ino")
    p.add_argument("--port", required=True, help="Port série (ex: /dev/ttyACM0 ou COM5)")
    p.add_argument("--baud", type=int, default=57600, help="Baudrate (défaut: 57600, matche Firmata.begin)")
    p.add_argument("--out", default="stim_times.txt", help="Fichier de log (défaut: stim_times.txt)")
    p.add_argument("--boot-delay", type=float, default=2.0, help="Délai après ouverture du port (défaut: 2.0s)")
    return p.parse_args()


def send_sysex(ser, cmd, data_bytes=None):
    msg = bytearray([START_SYSEX, cmd])
    if data_bytes:
        msg.extend(data_bytes)
    msg.append(END_SYSEX)
    ser.write(msg)
    ser.flush()


def duration_to_bytes(duration_s):
    """Encode une durée en secondes -> 2 octets Firmata 7-bit, unité = centisecondes."""
    duration_cs = int(round(duration_s * 100))
    if duration_cs > 16383:  # 14-bit max
        duration_cs = 16383
    lsb = duration_cs & 0x7F
    msb = (duration_cs >> 7) & 0x7F
    return [lsb, msb]


LOG_PREFIXES = ("SESSION", "STIM")


def read_serial(ser, log_path, stop_event):
    with open(log_path, "a") as f:
        while not stop_event.is_set():
            try:
                raw = ser.readline()
            except serial.SerialException:
                print("\n[ERREUR] Connexion série perdue.")
                stop_event.set()
                break

            if not raw:
                continue

            line = raw.decode(errors="ignore").strip()
            if not line:
                continue

            print(f"\n[ARDUINO] {line}\n> ", end="", flush=True)

            if line.startswith(LOG_PREFIXES):
                f.write(line + "\n")
                f.flush()


def main():
    args = parse_args()

    try:
        ser = serial.Serial(args.port, args.baud)
    except serial.SerialException as e:
        print(f"[ERREUR] Impossible d'ouvrir {args.port} : {e}")
        sys.exit(1)

    time.sleep(args.boot_delay)
    ser.reset_input_buffer()

    print(f"Connecté à {args.port} @ {args.baud} baud (SysEx). Log -> {args.out}")
    print("Commandes : START | STOP | <duree_s>  (Ctrl+C pour quitter)\n")

    stop_event = threading.Event()
    thread = threading.Thread(target=read_serial, args=(ser, args.out, stop_event), daemon=True)
    thread.start()

    try:
        while not stop_event.is_set():
            cmd = input("> ").strip()
            if not cmd:
                continue

            if cmd.upper() == "START":
                send_sysex(ser, SYSEX_CMD_START)
            elif cmd.upper() == "STOP":
                send_sysex(ser, SYSEX_CMD_STOP)
            else:
                try:
                    duration = float(cmd)
                    if duration <= 0:
                        print("# ERR: duree invalide")
                        continue
                    send_sysex(ser, SYSEX_CMD_STIM, duration_to_bytes(duration))
                except ValueError:
                    print("# ERR: commande non reconnue (START | STOP | <duree_s>)")
    except KeyboardInterrupt:
        print("\nFermeture...")
    finally:
        stop_event.set()
        try:
            send_sysex(ser, SYSEX_CMD_STOP)  # sécurité : coupe le gate à la fermeture
        except Exception:
            pass
        ser.close()


if __name__ == "__main__":
    main()
