"""
stim_logger_v4.py
-----------------
Logger pour StandardFirmata_SleepStim_v4.

La commande START est envoyée à l'Arduino sous forme de message SysEx Firmata
custom (0xF0 0x7F 0xF7) — aucun risque de collision avec les paquets Firmata.

Usage :
    python stim_logger_v4.py --port /dev/ttyACM0
    python stim_logger_v4.py --port COM3 --baud 57600 --out session_01.csv

Commandes :
    START   → envoie le SysEx de démarrage à l'Arduino + définit t=0 local
    STOP    → ferme le fichier et quitte
    q       → idem STOP
"""

import serial
import argparse
import csv
import time
import sys
import threading
import queue
from datetime import datetime

# ── SysEx custom START : 0xF0 0x7F 0xF7 ──────────────────────────────────────
SYSEX_START = bytes([0xF0, 0x7F, 0xF7])

SYSEX_STOP  = bytes([0xF0, 0x7E, 0xF7])

SYSEX_PAUSE   = bytes([0xF0, 0x7D, 0xF7])
SYSEX_UNPAUSE = bytes([0xF0, 0x7C, 0xF7])

# ── Événements Arduino à enregistrer ──────────────────────────────────────────
TRACKED_EVENTS = {
    "SESSION_START", "SESSION_STOP",
    "BASELINE_START", "BASELINE_PROGRESS", "BASELINE_DONE",
    "SLEEP_START", "SLEEP_END",
    "BLOCK_WAIT", "BLOCK_START", "BLOCK_END",
    "STIM_START", "STIM_END",
    "INTER_BLOCK_PAUSE",
    "SESSION_PAUSE", "SESSION_UNPAUSE",
}

CSV_FIELDS = [
    "event", "t_pc_ms", "t_pc_fmt",
    "block", "on_ms", "off_ms", "rep", "duration_ms", "cumul_ms",
    "raw_arduino",
]


def parse_args():
    p = argparse.ArgumentParser(description="Logger stimulation v4")
    p.add_argument("--port",  required=True)
    p.add_argument("--baud",  type=int, default=57600)
    p.add_argument("--out",   default=None)
    return p.parse_args()


def format_ms(ms):
    ms = int(ms)
    return f"{ms // 60000:02d}:{(ms % 60000) // 1000:02d}.{ms % 1000:03d}"


def parse_fields(line: str) -> dict:
    row = {f: "" for f in CSV_FIELDS}
    row["raw_arduino"] = line
    parts = line.split(",")
    if not parts:
        return row
    row["event"] = parts[0].strip()
    for part in parts[1:]:
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip(); v = v.strip()
            mapping = {"block": "block", "on_ms": "on_ms", "off_ms": "off_ms",
                       "rep": "rep", "duration_ms": "duration_ms", "cumul_ms": "cumul_ms"}
            if k in mapping:
                row[mapping[k]] = v
    return row


def serial_reader(ser, q):
    while True:
        try:
            line = ser.readline().decode("utf-8", errors="replace").strip()
            if line:
                q.put(("serial", line))
        except Exception:
            break


def stdin_reader(q):
    while True:
        try:
            q.put(("stdin", input()))
        except EOFError:
            break


def main():
    args     = parse_args()
    out_file = args.out or f"stim_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    print(f"Connexion sur {args.port} à {args.baud} baud…")
    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
    except serial.SerialException as e:
        print(f"Erreur : {e}"); sys.exit(1)

    time.sleep(2)
    ser.reset_input_buffer()

    shared_q = queue.Queue()
    threading.Thread(target=serial_reader, args=(ser, shared_q), daemon=True).start()
    threading.Thread(target=stdin_reader,  args=(shared_q,),     daemon=True).start()

    baseline_pc    = None
    session_active = False
    session_paused = False
    running        = True

    print()
    print("Commandes : START | STOP | PAUSE | UNPAUSE | q")
    print("(START optionnel si TTL OE connecté à syncPin Arduino)")
    print(f"Sortie CSV : {out_file}")
    print()

    csvfile = open(out_file, "w", newline="", encoding="utf-8")
    writer  = csv.DictWriter(csvfile, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    csvfile.flush()

    def write_row(row: dict):
        writer.writerow(row)
        csvfile.flush()
        t   = row.get("t_pc_fmt", "??:??.???")
        ev  = row.get("event", "")
        blk = f" bloc={row['block']}"        if row.get("block")       else ""
        on  = f" on={row['on_ms']}ms"        if row.get("on_ms")       else ""
        dr  = f" dur={row['duration_ms']}ms" if row.get("duration_ms") else ""
        rep = f" {row['rep']}"               if row.get("rep")         else ""
        cum = f" cumul={row['cumul_ms']}ms"  if row.get("cumul_ms")    else ""
        print(f"  [{t}] {ev}{blk}{on}{dr}{rep}{cum}")

    try:
        while running:
            try:
                source, line = shared_q.get(timeout=0.1)
            except queue.Empty:
                continue

            # ── Commandes utilisateur ────────────────────────────────────────
            if source == "stdin":
                cmd = line.strip().upper()

                if cmd in ("Q", "QUIT", "STOP"):
                    try:
                        ser.write(SYSEX_STOP)
                    except Exception as e:
                        print("  Erreur envoi STOP : {}".format(e))
                    print("  -> STOP envoye a l Arduino.")
                    running = False
                    continue

                if cmd in ("E", "EXIT", "P", "PAUSE") and session_active and not session_paused:
                    try:
                        ser.write(SYSEX_PAUSE)
                        session_paused = True
                        ser.flush()
                        print("ARRÊT D'URGENCE ENVOYÉ")
                        print("Attente de la confirmation de l'Arduino.")
                    except Exception as e:
                        print(f"  ERREUR ENVOI ARRÊT D'URGENCE : {e}")
                    continue

                if cmd == "UNPAUSE" and session_active and session_paused:
                    ser.write(SYSEX_UNPAUSE)
                    session_paused = False
                    print("  → UNPAUSE envoyé. Protocole repris.")
                    continue

                if cmd == "START" and not session_active:
                    # Envoi du SysEx custom — propre, aucune interférence Firmata
                    try:
                        ser.write(SYSEX_START)
                    except Exception as e:
                        print(f"  Erreur envoi SysEx : {e}")
                    baseline_pc    = time.time()
                    session_active = True
                    row = {f: "" for f in CSV_FIELDS}
                    row.update(event="BASELINE_PC", t_pc_ms=0,
                               t_pc_fmt="00:00.000", raw_arduino="USER_START")
                    write_row(row)
                    print(f"  → SysEx START envoyé. t=0 défini. Fichier : {out_file}")
                    continue

                if cmd == "START" and session_active:
                    print("  Session déjà active.")
                    continue

                print(f"  Inconnu : '{line}' — commandes : START | STOP | q")
                continue

            # ── Données Arduino ──────────────────────────────────────────────
            if line.startswith("#"):
                print(f"  [Arduino] {line}")
                continue

            event_key = line.split(",")[0].strip()

            if event_key not in TRACKED_EVENTS:
                # Filtrer le bruit Firmata silencieusement
                if any(x in line for x in ("Unknown pin mode", "I2C:", "Max servo")):
                    pass
                else:
                    print(f"  [raw] {line}")
                continue

            if not session_active:
                print(f"  [avant session] {line}")
                continue

            # Démarrage automatique côté PC calé sur SESSION_START Arduino
            # (déclenché par le TTL OE → plus besoin de taper START manuellement)
            if event_key == "SESSION_START" and not session_active:
                baseline_pc    = time.time()
                session_active = True
                row = {f: "" for f in CSV_FIELDS}
                row.update(event="BASELINE_PC", t_pc_ms=0, t_pc_fmt="00:00.000", raw_arduino="USER_START")
                write_row(row)
                print(f"  → Session démarrée automatiquement (TTL OE reçu par Arduino). t=0 défini. Fichier : {out_file}")

            t_ms = int((time.time() - baseline_pc) * 1000)
            row  = parse_fields(line)
            row["t_pc_ms"]  = t_ms
            row["t_pc_fmt"] = format_ms(t_ms)
            write_row(row)

    except KeyboardInterrupt:
        ser.write(SYSEX_PAUSE)  # sécurité : coupe la stim si Ctrl+C
        print("\nInterruption clavier.")
    finally:
        csvfile.close()
        ser.close()
        print(f"\nFichier sauvegardé : {out_file}")
        # Résumé
        print("\n── Résumé ────────────────────────────────────────────────")
        try:
            import collections
            counts = collections.Counter()
            total_dur = collections.defaultdict(int)
            with open(out_file, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r["event"] == "STIM_END" and r["block"]:
                        counts[r["block"]] += 1
                        try: total_dur[r["block"]] += int(r["duration_ms"])
                        except ValueError: pass
            if counts:
                for blk in sorted(counts):
                    print(f"  Bloc {blk} : {counts[blk]} stim, "
                          f"durée totale {total_dur[blk]} ms")
            else:
                print("  (aucune stimulation enregistrée)")
        except Exception:
            pass
        print("──────────────────────────────────────────────────────────")


if __name__ == "__main__":
    main()
