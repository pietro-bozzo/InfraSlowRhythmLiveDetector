# =============================================================================
# Python Processor for Open-Ephys Plugin — classique (deux phases, mono-détecteur)
# Les paramètres sont chargés depuis OE_classique_CONFIG.py.
# Ce fichier ne doit pas être modifié entre les sessions.
# =============================================================================

CONFIG_PATH = "/mnt/hubel-data-103/Guillaume/InfraSlowRhythmLiveDetector/Code/Python/Classic_processor/OE_classic_CONFIG.py"

import numpy as np
import math
import oe_pyprocessor
from collections import deque
import os
import fileinput
import time
import json
from datetime import datetime


class PyProcessor:

    def __init__(self, processor, num_channels, sample_rate):
        print("Num Channels: ", num_channels, " | Sample Rate: ", sample_rate)

        self.processor = processor
        self.num_channels = num_channels
        self.sample_rate = sample_rate

        # -----------------------------------------------------------------------
        # États internes (non configurables)
        # -----------------------------------------------------------------------
        self.time_counter = 0.0
        self.threshold_time_counter = 0.0

        self.buffer_points = []
        self.accel_points = []
        self.threshold_value = None
        self.threshold_acceleration = None
        self.mean_acceleration_decay = None

        self.variance_init = None
        self.accel_bin_buffer = deque()
        self.accel_bin_time = 0.0
        self.accel_init_buffer = []
        self.accel_init_time = 0.0
        self.accel_threshold_calculated = False

        self.phase2_buffer_points = []
        self.phase2_sws_time = 0.0
        self.phase2_done = False
        self.threshold_value_sws = None

        self.mean_buffers = deque()
        self.mean_buffer_time = 0
        self.acceleration_buffers = deque()
        self.acceleration_buffer_time = 0

        self.threshold_calculated = True
        self.ON_state = False
        self.IS_state = False
        self.wake_REM_state_fr = False
        self.wake_REM_state_accel = False

        self.user_redo_tresh = False
        self.user_counter_decision = 0
        self.user_stop_IS_now = False
        self.event_print = 0
        self.debuglist = []
        self.global_t0 = -1

        self.start_time_ON = -1
        self.end_time_ON = 0
        self.start_time_OFF = -1
        self.end_time_OFF = 0
        self.duration_OFF = -1

        self.L_time_OFFs = []
        self.L_time_ONs = []
        self.L_time_IS = []
        self.L_time_wake_REM_fr = []
        self.L_time_wake_REM_accel = []

        self.off_intervals = []
        self.on_intervals = []

        self.stim_current_index = 0
        self.stim_count = 0
        self.stim_timer = 0.0
        self.stim_done = False

        # Chargement de la configuration externe
        self._load_config()

        # debug_path dérivé après chargement config
        self.debug_path = os.path.abspath(self.path + self.debug_name)

    # -------------------------------------------------------------------------
    def _load_config(self):
        config_path = os.path.abspath(CONFIG_PATH)
        if not os.path.isfile(config_path):
            raise FileNotFoundError(
                f"[OE] Fichier de configuration introuvable : {config_path}\n"
                f"Modifiez CONFIG_PATH en tête du script."
            )
        with open(config_path, "r") as f:
            config_code = f.read()
        exec(config_code, {"self": self})
        print(f"[OE] Config chargée depuis : {config_path}")

        required = [
            "time_value_moy", "bin_duration_accel",
            "ttl_ON", "ttl_IS", "ttl_thresholding",
            "ttl_wake_REM_fr", "ttl_wake_REM_accel", "ttl_phase2_done", "ttl_stim",
            "ligne_threshold_integration", "ligne_stop_IS_now", "ligne_print",
            "mean_spike_rate_channel", "accel_channel_1", "accel_channel_2", "accel_channel_3",
            "time_limit_integration", "time_limit_integration_accel", "percentage",
            "time_limit_phase2", "percentage_sws",
            "multiplior_tresh", "multiplior_tresh_accel",
            "max_time_ON", "max_time_OFF", "min_time_OFF", "min_time_ON",
            "stim_max_per_type", "stim_interval",
            "saving", "path", "file_name", "debug_name", "ttl_sync",
        ]
        missing = [k for k in required if not hasattr(self, k)]
        if missing:
            raise ValueError(f"[OE] Paramètres manquants dans le fichier de config : {missing}")

    # =========================================================================
    # Le reste du code est identique à l'original
    # =========================================================================

    def handle_ttl_event(self, source_node, channel, sample_number, line, state):

        if (line == self.ligne_threshold_integration and state == True) and not self.user_redo_tresh:
            self.user_redo_tresh = True
            self.user_counter_decision += 1
            self.processor.add_python_event(self.ttl_thresholding, True)

        if (line == self.ligne_threshold_integration and state == False):
            self.processor.add_python_event(self.ttl_thresholding, False)

        if line == self.ligne_stop_IS_now and state == True:
            self.user_stop_IS_now = True

        if line == self.ligne_stop_IS_now and state == False:
            self.user_stop_IS_now = False

        if line == self.ligne_print and state == True and self.event_print == 0:
            self.event_print += 1

        if line == self.ligne_print and state == False:
            self.event_print = 0

        return

    def process(self, data):

        if getattr(self, '_sync_ttl_pending', False):
            self._sync_ttl_pending = False
            self.processor.add_python_event(self.ttl_sync, True)
            self._sync_ttl_end_time = self.time_counter + 1.0

        # Couper le TTL de sync après 1 seconde
        if hasattr(self, '_sync_ttl_end_time') and self._sync_ttl_end_time > 0:
            if self.time_counter >= self._sync_ttl_end_time:
                self.processor.add_python_event(self.ttl_sync, False)
                self._sync_ttl_end_time = 0.0

        mean_spike = data[self.mean_spike_rate_channel, :]
        accel1 = np.mean(data[self.accel_channel_1, :])
        accel2 = np.mean(data[self.accel_channel_2, :])
        accel3 = np.mean(data[self.accel_channel_3, :])

        buffer_duration = mean_spike.shape[0] / self.sample_rate
        self.time_counter += buffer_duration

        current_mean = np.mean(mean_spike)

        self.mean_buffers.append((buffer_duration, current_mean))
        self.mean_buffer_time += buffer_duration
        while self.mean_buffer_time > self.time_value_moy:
            dt, val = self.mean_buffers.popleft()
            self.mean_buffer_time -= dt
        moy_glissante = np.mean([v for _, v in self.mean_buffers])

        norm_acceleration = ((accel1**2 + accel2**2 + accel3**2)**0.5) * 10000
        self.acceleration_buffers.append((buffer_duration, norm_acceleration))
        self.acceleration_buffer_time += buffer_duration
        while self.acceleration_buffer_time > self.bin_duration_accel:
            dt, val = self.acceleration_buffers.popleft()
            self.acceleration_buffer_time -= dt
        variance_glissante = np.var([v for _, v in self.acceleration_buffers])

        if self.event_print == 1:
            self.event_print = 2
            self.debuglist.append(
                f"[OE DEBUG] t={self.time_counter:.3f}s"
                f" | current_mean={current_mean:.4f}"
                f" | moy_glissante={moy_glissante:.4f}"
                f" | norm_accel={norm_acceleration:.4f}"
                f" | var_glissante={variance_glissante:.4f}"
                f" | phase2_sws_time={self.phase2_sws_time:.1f}s"
                f" | phase2_done={self.phase2_done}"
            )

        if self.user_counter_decision < 1:
            return

        if self.user_redo_tresh and self.user_counter_decision > 0 and self.threshold_calculated:
            self.threshold_calculated = False
            self.threshold_time_counter = 0.0
            self.buffer_points = []
            self.accel_points = []

            self.phase2_buffer_points = []
            self.phase2_sws_time = 0.0
            self.phase2_done = False
            self.threshold_value_sws = None
            self.accel_threshold_calculated = False
            self.accel_init_buffer = []
            self.accel_init_time = 0.0
            self.variance_init = None

            self.ON_state = False
            self.IS_state = False
            self.wake_REM_state_fr = False
            self.wake_REM_state_accel = False
            self.start_time_ON = -1
            self.end_time_ON = 0
            self.start_time_OFF = -1
            self.end_time_OFF = 0
            self.L_time_OFFs = []

            self.processor.add_python_event(self.ttl_ON, False)
            self.processor.add_python_event(self.ttl_IS, False)
            self.processor.add_python_event(self.ttl_wake_REM_fr, False)
            self.processor.add_python_event(self.ttl_wake_REM_accel, False)
            self.processor.add_python_event(self.ttl_phase2_done, False)

        if self.user_stop_IS_now:
            self.ON_state = False
            self.IS_state = False
            self.wake_REM_state_fr = False
            self.wake_REM_state_accel = False
            self.start_time_ON = -1
            self.end_time_ON = 0
            self.start_time_OFF = -1
            self.end_time_OFF = 0
            self.L_time_OFFs = []

            self.processor.add_python_event(self.ttl_ON, False)
            self.processor.add_python_event(self.ttl_IS, False)
            self.processor.add_python_event(self.ttl_wake_REM_fr, False)
            self.processor.add_python_event(self.ttl_wake_REM_accel, False)

        if not self.threshold_calculated:
            self.threshold_time_counter += buffer_duration
            self.buffer_points.append(mean_spike)
            self.accel_points.append(norm_acceleration)

            if not self.accel_threshold_calculated:
                self.accel_init_buffer.append(norm_acceleration)
                self.accel_init_time += buffer_duration
                if self.accel_init_time >= self.time_limit_integration_accel:
                    self.variance_init = np.var(self.accel_init_buffer)
                    self.accel_threshold_calculated = True
                    self.accel_init_buffer = []

            if self.threshold_time_counter >= self.time_limit_integration:
                self.threshold_calculated = True
                all_values = np.concatenate(self.buffer_points)
                self.threshold_value = np.percentile(all_values, self.percentage)
                self.mean_acceleration_decay = np.mean(self.accel_points)
                self.user_redo_tresh = False
                self.debuglist.append(
                    f"[PHASE 1 DONE] t={self.time_counter:.1f}s"
                    f" | threshold_value={self.threshold_value:.4f} (p{self.percentage})"
                    f" | variance_init={self.variance_init}"
                )

            return

        if self.threshold_value is None:
            return

        condition_wake = variance_glissante > self.multiplior_tresh_accel * self.variance_init
        condition_rem_wake = moy_glissante > self.multiplior_tresh * self.threshold_value

        if condition_wake:
            self.processor.add_python_event(self.ttl_wake_REM_accel, True)
            if not self.wake_REM_state_accel:
                self.L_time_wake_REM_accel.append(self.time_counter)
                with open(self.debug_path, "a") as f:
                    print(f"[WAKE DETECTED] t={self.time_counter:.1f}s", file=f)
            self.wake_REM_state_accel = True
        else:
            if self.wake_REM_state_accel:
                self.L_time_wake_REM_accel.append(self.time_counter)
                with open(self.debug_path, "a") as f:
                    print(f"[WAKE ENDED] t={self.time_counter:.1f}s", file=f)
            self.wake_REM_state_accel = False
            self.processor.add_python_event(self.ttl_wake_REM_accel, False)

        if condition_rem_wake:
            self.processor.add_python_event(self.ttl_wake_REM_fr, True)
            if not self.wake_REM_state_fr:
                self.L_time_wake_REM_fr.append(self.time_counter)
            self.wake_REM_state_fr = True
        else:
            if self.wake_REM_state_fr:
                self.L_time_wake_REM_fr.append(self.time_counter)
            self.wake_REM_state_fr = False
            self.processor.add_python_event(self.ttl_wake_REM_fr, False)

        wake_REM_state = self.wake_REM_state_fr or self.wake_REM_state_accel

        if not self.phase2_done and not wake_REM_state:
            self.phase2_buffer_points.append(mean_spike)
            self.phase2_sws_time += buffer_duration

            if self.phase2_sws_time >= self.time_limit_phase2:
                all_sws_values = np.concatenate(self.phase2_buffer_points)
                self.threshold_value_sws = np.percentile(all_sws_values, self.percentage_sws)
                self.phase2_done = True
                self.processor.add_python_event(self.ttl_phase2_done, True)
                self.debuglist.append(
                    f"[PHASE 2 DONE] t={self.time_counter:.1f}s"
                    f" | threshold_value_sws={self.threshold_value_sws:.4f} (p{self.percentage_sws})"
                    f" | SWS accumulated={self.phase2_sws_time:.1f}s"
                )

        active_threshold = self.threshold_value_sws if self.phase2_done else self.threshold_value

        if wake_REM_state:
            self.L_time_OFFs = []
            self.start_time_ON = -1
            self.start_time_OFF = -1
            self.ON_state = False
            if self.IS_state:
                end_IS = self.on_intervals[-1]['end'] if len(self.on_intervals) > 0 else self.time_counter
                self.L_time_IS.append(end_IS)
            self.IS_state = False
            self.processor.add_python_event(self.ttl_IS, False)
            return

        cond_max_OFF = (self.time_counter - self.start_time_OFF < self.max_time_OFF)
        if self.IS_state and self.start_time_OFF >= 0 and not cond_max_OFF:
            self.IS_state = False
            if self.on_intervals and not self.ON_state:
                end_IS = self.on_intervals[-1]['end']
            else:
                end_IS = self.time_counter
            self.L_time_IS.append(end_IS)
            self.L_time_OFFs = []
            self.L_time_ONs = []
            self.start_time_OFF = -1
            self.start_time_ON = -1
            self.processor.add_python_event(self.ttl_IS, False)

        if self.duration_OFF < 0:
            self.start_time_OFF = self.time_counter
            self.duration_OFF = 0

        ON_now = (current_mean - active_threshold) > 0

        if ON_now and not self.ON_state:
            self.ON_state = True
            self.start_time_ON = self.time_counter
            if self.start_time_OFF >= 0:
                self.end_time_OFF = self.time_counter
                time_OFF = self.end_time_OFF - self.start_time_OFF
                self.duration_OFF = time_OFF
                self.off_intervals.append({
                    'start': self.start_time_OFF,
                    'end': self.end_time_OFF,
                    'duration': time_OFF,
                })
                if len(self.off_intervals) > 5:
                    self.off_intervals.pop(0)
            self.processor.add_python_event(self.ttl_ON, True)

        elif not ON_now and self.ON_state:
            self.ON_state = False
            if self.start_time_ON >= 0:
                self.end_time_ON = self.time_counter
                time_ON = self.end_time_ON - self.start_time_ON

                self.on_intervals.append({
                    'start': self.start_time_ON,
                    'end': self.end_time_ON,
                    'duration': time_ON,
                })
                if len(self.on_intervals) > 5:
                    self.on_intervals.pop(0)

                self.start_time_ON = -1

                if time_ON > self.max_time_ON:
                    if self.IS_state:
                        self.L_time_IS.append(self.end_time_ON)
                    self.L_time_OFFs = []
                    self.L_time_ONs = []
                    self.start_time_OFF = -1
                    self.IS_state = False
                    self.processor.add_python_event(self.ttl_IS, False)

                elif self.min_time_ON <= time_ON <= self.max_time_ON:
                    if (len(self.L_time_wake_REM_accel) > 0 and len(self.L_time_wake_REM_fr) > 0 and
                            self.end_time_OFF >= self.L_time_wake_REM_accel[-1] and
                            self.end_time_OFF >= self.L_time_wake_REM_fr[-1]):
                        self.L_time_OFFs.append(self.duration_OFF)
                    if wake_REM_state:
                        self.L_time_OFFs = []
                    self.duration_OFF = 0
                    self.start_time_OFF = self.time_counter
                    self.L_time_ONs.append(time_ON)

            self.processor.add_python_event(self.ttl_ON, False)

        if len(self.L_time_OFFs) >= 2 and not wake_REM_state:
            cond_max = all(t < self.max_time_OFF for t in self.L_time_OFFs)
            long_OFFs = [t for t in self.L_time_OFFs if t > self.min_time_OFF]
            cond_min_OFFs = len(long_OFFs) >= 2

            if cond_max and cond_min_OFFs:
                if not self.IS_state:
                    n_back = 2
                    if len(self.off_intervals) >= n_back:
                        start_IS = self.off_intervals[-n_back]['end']
                    else:
                        start_IS = self.time_counter
                    self.L_time_IS.append(start_IS)
                self.IS_state = True
                self.processor.add_python_event(self.ttl_IS, True)

        return

    def start_recording(self, recording_dir):
        now = self.time_counter
        if self.global_t0 == -1:
            self.global_t0 = now
        self._sync_ttl_pending = True #Pour synchroniser arduino et python processor, on envoie un TTL de sync au début de l'acquisition 

    def stop_acquisition(self):
        if self.saving:
            namedossier = os.path.abspath(self.path + self.file_name)
            with open(namedossier, "a") as f:
                line_count = sum(1 for line in fileinput.input(namedossier))
                print("STOP ACQUISITION NUMBER", int(line_count / 5) + 1, file=f)
                print("List of IS timing markers (starts with 'start'):", file=f)
                print(self.L_time_IS, file=f)
                print("List of wake/REM (firing rate) timing markers (starts with 'start'):", file=f)
                print(self.L_time_wake_REM_fr, file=f)
                print("List of wake/REM (accelerometer) timing markers (starts with 'start'):", file=f)
                print(self.L_time_wake_REM_accel, file=f)
                print("Phase 2 SWS threshold:", self.threshold_value_sws, file=f)
                print("Phase 2 SWS time accumulated (s):", self.phase2_sws_time, file=f)
                print("debug_ list:", file=f)
                print(self.debuglist, file=f)
                print("Temps début recording global t0 (s):", self.global_t0, file=f)
        return