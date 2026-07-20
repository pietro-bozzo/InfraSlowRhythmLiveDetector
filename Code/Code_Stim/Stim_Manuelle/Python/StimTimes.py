import serial
import threading
import time

ser = serial.Serial("/dev/ttyACM2", 9600)

time.sleep(2)

# =========================
# Lecture Arduino
# =========================
def read_serial():

    with open("stim_times.txt", "a") as f:

        while True:

            line = ser.readline().decode(errors="ignore").strip()

            if line:
                print("\n[ARDUINO]", line)

                if line.startswith("SESSION") or line.startswith("STIM"):
                    f.write(line + "\n")
                    f.flush()

# thread lecture
thread = threading.Thread(target=read_serial)
thread.daemon = True
thread.start()

# =========================
# Ecriture utilisateur
# =========================
while True:

    cmd = input("> ")

    ser.write((cmd + "\n").encode())
