# =============================================================================
# Python Processor for Open-Ephys Plugin
# =============================================================================
# Ce fichier ne doit PAS être modifié entre les sessions.
# Toute la configuration est dans config_ISR.py.
#
CONFIG_PATH = "/mnt/hubel-data-103/Guillaume/InfraSlowRhythmLiveDetector/Code/Python/Debug_processor/OE_debug_CONFIG.py"
# =============================================================================

import sys
with open("/tmp/oe_python_env.txt", "w") as f:
    f.write(sys.executable + "\n")
    f.write(str(sys.path) + "\n")
    f.write(str(sys.version) + "\n")

import numpy as np
import oe_pyprocessor
from collections import deque
import os
import fileinput
import time
from datetime import datetime


# =============================================================================
class PyProcessor:

    def __init__(self, processor, num_channels, sample_rate):
        print("Num Channels:", num_channels, "| Sample Rate:", sample_rate)

        self.processor   = processor
        self.num_channels = num_channels
        self.sample_rate  = sample_rate

        # Runtime state (non configurable)
        self.time_counter           = 0.0
        self.threshold_time_counter = 0.0
        self.buffer_points          = []
        self.accel_points           = []
        self.threshold_value        = None
        self.threshold_acceleration = None
        self.mean_acceleration_decay = None

        self.mean_buffers             = deque()
        self.mean_buffer_time         = 0.0
        self.acceleration_buffers     = deque()
        self.acceleration_buffer_time = 0.0

        self.threshold_calculated = True
        self.ON_state             = False
        self.IS_state             = False
        self.wake_REM_state       = False

        self.user_redo_tresh       = False
        self.user_counter_decision = 0
        self.user_stop_IS_now      = False

        self.event_print = 0
        self.init_print  = 1
        self.debuglist   = []
        self.global_t0   = -1

        self.start_time_ON  = -1
        self.end_time_ON    = 0
        self.start_time_OFF = -1
        self.end_time_OFF   = 0
        self.duration_OFF   = -1

        self.L_time_OFFs     = []
        self.L_time_ONs      = []
        self.L_time_IS       = []
        self.L_time_wake_REM = []

        # Charger la configuration externe
        self._load_config()

    # -------------------------------------------------------------------------
    def _load_config(self):
        """
        Charge config_ISR.py via exec().
        Les lignes 'self.xxx = ...' du fichier sont exécutées dans le contexte
        de cette instance — équivalent à les écrire directement dans __init__.
        """
        config_path = os.path.abspath(CONFIG_PATH)
        if not os.path.isfile(config_path):
            raise FileNotFoundError(
                f"[ISR] Fichier de configuration introuvable : {config_path}\n"
                f"Créez ce fichier ou modifiez CONFIG_PATH en tête du script."
            )
        with open(config_path, "r") as f:
            config_code = f.read()

        exec(config_code, {"self": self, "__builtins__": __builtins__})

        # Dériver debug_path après chargement
        self.debug_path = os.path.abspath(self.path + self.debug_name)

        print(f"[ISR] Config chargée depuis : {config_path}")

        # Vérification des paramètres requis
        required = [
            "ttl_ON", "ttl_IS", "ttl_wake_REM", "ttl_thresholding",
            "ligne_threshold_integration", "ligne_stop_IS_now", "ligne_print",
            "time_limit_integration", "percentage", "percentage_accel",
            "max_time_ON", "time_value_moy", "time_value_acceleration",
            "multiplior_tresh", "multiplior_tresh_accel",
            "max_time_OFF", "min_time_OFF", "min_time_ON",
            "mean_spike_rate_channel", "accel_channel_1", "accel_channel_2", "accel_channel_3",
            "n_channels", "saving", "path", "file_name", "debug_name",
        ]
        missing = [k for k in required if not hasattr(self, k)]
        if missing:
            raise ValueError(f"[ISR] Paramètres manquants dans config_ISR.py : {missing}")

    # =========================================================================
    def handle_ttl_event(self, source_node, channel, sample_number, line, state):

        if line == self.ligne_threshold_integration and state == True and not self.user_redo_tresh:
            self.user_redo_tresh = True
            self.user_counter_decision += 1
            self.processor.add_python_event(self.ttl_thresholding, True)

        if line == self.ligne_threshold_integration and state == False:
            self.processor.add_python_event(self.ttl_thresholding, False)

        if line == self.ligne_stop_IS_now and state == True:
            self.user_stop_IS_now = True

        if line == self.ligne_stop_IS_now and state == False:
            self.user_stop_IS_now = False

        if line == self.ligne_print and state == True and self.event_print == 0:
            self.event_print += 1

        if line == self.ligne_print and state == False:
            self.event_print = 0

    # =========================================================================
    def process(self, data):

        # ---- STEP 0 : sliding means ----
        mean_spike = data[self.mean_spike_rate_channel, :]
        accel1 = np.mean(data[self.accel_channel_1, :])
        accel2 = np.mean(data[self.accel_channel_2, :])
        accel3 = np.mean(data[self.accel_channel_3, :])

        buffer_duration = mean_spike.shape[0] / self.sample_rate
        self.time_counter           += buffer_duration
        self.threshold_time_counter += buffer_duration

        current_mean = np.mean(mean_spike)
        self.mean_buffers.append((buffer_duration, current_mean))
        self.mean_buffer_time += buffer_duration
        while self.mean_buffer_time > self.time_value_moy:
            dt, _ = self.mean_buffers.popleft()
            self.mean_buffer_time -= dt
        moy_glissante = np.mean([v for _, v in self.mean_buffers])

        norm_acceleration = ((accel1**2 + accel2**2 + accel3**2)**0.5) * 10000
        self.acceleration_buffers.append((buffer_duration, norm_acceleration))
        self.acceleration_buffer_time += buffer_duration
        while self.acceleration_buffer_time > self.time_value_acceleration:
            dt, _ = self.acceleration_buffers.popleft()
            self.acceleration_buffer_time -= dt
        acceleration_glissante = np.mean([v for _, v in self.acceleration_buffers])

        # ---- STEP 1 : debug print ----
        if self.event_print == 1:
            self.event_print = 2
            self.debuglist.append(
                f"[OE DEBUG] t={self.time_counter:.3f}s | shape={data.shape}"
            )
            with open(self.debug_path, "a") as f:
                print("acceleration :", acceleration_glissante, file=f)
                for i in range(self.n_channels):
                    print(f"Channel {i} last : {data[i, -1]}", file=f)
                print("Valeurs du début", file=f)
                for i in self.list_channels_debug_printed:
                    print(f"Channel {i} first : {data[i, -1]}", file=f)

        if self.init_print == 1:
            self.init_print = 2
            with open(self.debug_path, "a") as f:
                for i in self.channels_val_debut:
                    print(f"Channel {i} first 20 : {data[i, :20]}", file=f)

        # ---- STEP 1 : user control ----
        if self.user_counter_decision < 1:
            return

        if self.user_redo_tresh and self.threshold_calculated:
            self.threshold_calculated    = False
            self.threshold_time_counter  = 0.0
            self.buffer_points           = []
            self.accel_points            = []
            self.ON_state                = False
            self.IS_state                = False
            self.wake_REM_state          = False
            self.start_time_ON           = -1
            self.end_time_ON             = 0
            self.start_time_OFF          = -1
            self.end_time_OFF            = 0
            self.L_time_OFFs             = []
            self.processor.add_python_event(self.ttl_ON,       False)
            self.processor.add_python_event(self.ttl_IS,       False)
            self.processor.add_python_event(self.ttl_wake_REM, False)

        if self.user_stop_IS_now:
            self.ON_state       = False
            self.IS_state       = False
            self.wake_REM_state = False
            self.start_time_ON  = -1
            self.end_time_ON    = 0
            self.start_time_OFF = -1
            self.end_time_OFF   = 0
            self.L_time_OFFs    = []
            self.processor.add_python_event(self.ttl_ON,       False)
            self.processor.add_python_event(self.ttl_IS,       False)
            self.processor.add_python_event(self.ttl_wake_REM, False)

        # ---- STEP 2 : threshold calculation ----
        if not self.threshold_calculated:
            self.buffer_points.append(mean_spike)
            self.accel_points.append(norm_acceleration)

            if self.threshold_time_counter >= self.time_limit_integration:
                all_values = np.concatenate(self.buffer_points)
                self.threshold_value         = np.percentile(all_values, self.percentage)
                self.threshold_acceleration  = np.percentile(self.accel_points, self.percentage_accel)
                self.mean_acceleration_decay = np.mean(self.accel_points)
                self.threshold_calculated    = True
                self.user_redo_tresh         = False

                with open(self.debug_path, "a") as f:
                    for i in range(self.n_channels):
                        print(f"Channel {i} mean : {np.mean(data[i, :]):.4f}", file=f)
            return

        # ---- STEP 3 : detection ----
        if self.threshold_acceleration is None or self.threshold_value is None:
            return

        condition_wake = (
            np.abs(acceleration_glissante - self.mean_acceleration_decay) >
            np.abs(self.threshold_acceleration * self.multiplior_tresh_accel
                   - self.mean_acceleration_decay)
        )
        condition_rem_wake = moy_glissante > self.multiplior_tresh * self.threshold_value

        if condition_wake or condition_rem_wake:
            self.processor.add_python_event(self.ttl_wake_REM, True)
            self.L_time_OFFs    = []
            self.start_time_ON  = -1
            self.start_time_OFF = -1
            self.ON_state       = False
            if self.IS_state:
                self.L_time_IS.append(self.time_counter)
            if not self.wake_REM_state:
                self.L_time_wake_REM.append(self.time_counter)
            self.IS_state       = False
            self.wake_REM_state = True
            self.processor.add_python_event(self.ttl_IS, False)
            return

        # Pas de wake/REM
        if self.wake_REM_state:
            self.L_time_wake_REM.append(self.time_counter)
        self.wake_REM_state = False
        self.processor.add_python_event(self.ttl_wake_REM, False)

        cond_max_OFF = (self.time_counter - self.start_time_OFF < self.max_time_OFF)
        if self.IS_state and self.start_time_OFF >= 0 and not cond_max_OFF:
            self.IS_state = False
            self.L_time_IS.append(self.time_counter)
            self.L_time_OFFs    = []
            self.L_time_ONs     = []
            self.start_time_OFF = -1
            self.start_time_ON  = -1
            self.processor.add_python_event(self.ttl_IS, False)

        if self.duration_OFF < 0:
            self.start_time_OFF = self.time_counter
            self.duration_OFF   = 0

        ON_now = (current_mean - self.threshold_value) > 0

        if ON_now and not self.ON_state:
            self.ON_state      = True
            self.start_time_ON = self.time_counter
            if self.start_time_OFF >= 0:
                self.end_time_OFF = self.time_counter
                self.duration_OFF = self.end_time_OFF - self.start_time_OFF
            self.processor.add_python_event(self.ttl_ON, True)

        elif not ON_now and self.ON_state:
            self.ON_state = False
            if self.start_time_ON >= 0:
                self.end_time_ON  = self.time_counter
                time_ON           = self.end_time_ON - self.start_time_ON
                self.start_time_ON = -1

                if time_ON > self.max_time_ON:
                    if self.IS_state:
                        self.L_time_IS.append(self.time_counter)
                    self.L_time_OFFs    = []
                    self.L_time_ONs     = []
                    self.start_time_OFF = -1
                    self.IS_state       = False
                    self.processor.add_python_event(self.ttl_IS, False)

                elif self.min_time_ON <= time_ON <= self.max_time_ON:
                    self.L_time_OFFs.append(self.duration_OFF)
                    self.duration_OFF   = 0
                    self.start_time_OFF = self.time_counter
                    self.L_time_ONs.append(time_ON)

            self.processor.add_python_event(self.ttl_ON, False)

        if len(self.L_time_OFFs) >= 2 and not self.wake_REM_state:
            cond_max      = all(t < self.max_time_OFF for t in self.L_time_OFFs)
            long_OFFs     = [t for t in self.L_time_OFFs if t > self.min_time_OFF]
            cond_min_OFFs = len(long_OFFs) >= 2

            if cond_max and cond_min_OFFs:
                if not self.IS_state:
                    self.L_time_IS.append(self.time_counter)
                    with open(self.debug_path, "a") as f:
                        print(f"IS detection : {self.time_counter}", file=f)
                self.IS_state = True
                self.processor.add_python_event(self.ttl_IS, True)

    # =========================================================================
    def start_acquisition(self):
        print("[ISR] Début acquisition")

    def start_recording(self, recording_dir):
        if self.global_t0 == -1:
            self.global_t0 = self.time_counter

    def stop_acquisition(self):
        print("[ISR] Fin acquisition")
        if not self.saving:
            return

        namedossier = os.path.abspath(self.path + self.file_name)
        try:
            with open(namedossier, "r") as f_read:
                line_count = sum(1 for _ in f_read)
        except FileNotFoundError:
            line_count = 0

        with open(namedossier, "a") as f:
            print(f"STOP ACQUISITION NUMBER {int(line_count / 5) + 1}", file=f)
            print(f"Config: {CONFIG_PATH}", file=f)
            print("List of IS timing markers (starts with 'start'):", file=f)
            print(self.L_time_IS, file=f)
            print("List of wake/REM timing markers (starts with 'start'):", file=f)
            print(self.L_time_wake_REM, file=f)
            print("debug list:", file=f)
            print(self.debuglist, file=f)
            print(f"global_t0 (s): {self.global_t0}", file=f)