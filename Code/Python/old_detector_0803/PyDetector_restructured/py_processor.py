# =============================================================================
# py_processor.py — Orchestrateur (API Open-Ephys inchangée)
#
# Ce fichier est le seul que OE charge. Il ne contient plus de logique
# métier : il charge la config, instancie les briques, et à chaque
# process() fait juste circuler les données entre elles dans le bon ordre.
#
# Briques :
#   RollingWindowStat    -> rolling_buffer.py    (moy/var glissantes)
#   TTLPort              -> ttl_port.py          (TTL + sync pulse)
#   ThresholdCalibrator  -> threshold_calibrator.py  (Phase 1 / Phase 2)
#   WakeRemDetector       -> wake_rem_detector.py    (Wake/REM fr + accel)
#   ISStateMachine        -> is_state_machine.py     (ON/OFF/IS)
# =============================================================================

CONFIG_PATH = "/mnt/hubel-data-103/Guillaume/InfraSlowRhythmLiveDetector/Code/Python/PyDetector_restructured/OE_restructured_CONFIG.py"

import os
import fileinput
import numpy as np
import math
import oe_pyprocessor
import time
import json
from datetime import datetime

from rolling_buffer import RollingWindowStat
from ttl_port import TTLPort
from threshold_calibrator import ThresholdCalibrator
from wake_rem_detector import WakeRemDetector
from is_state_machine import ISStateMachine


class PyProcessor:

    def __init__(self, processor, num_channels, sample_rate):
        print("Num Channels: ", num_channels, " | Sample Rate: ", sample_rate)

        self.processor = processor
        self.num_channels = num_channels
        self.sample_rate = sample_rate

        self.time_counter = 0.0
        self.debuglist = []
        self.global_t0 = -1

        self.user_redo_tresh = False
        self.user_counter_decision = 0
        self.user_stop_IS_now = False
        self.event_print = 0

        self._load_config()
        self.debug_path = os.path.abspath(self.path + self.debug_name)

        # --- Wiring des briques ------------------------------------------
        self.ttl_port = TTLPort(self.processor)

        self.moy_glissante_buf = RollingWindowStat(self.time_value_moy)
        self.var_glissante_buf = RollingWindowStat(self.bin_duration_accel)

        self.calibrator = ThresholdCalibrator(
            time_limit_integration=self.time_limit_integration,
            percentage=self.percentage,
            time_limit_integration_accel=self.time_limit_integration_accel,
            time_limit_phase2=self.time_limit_phase2,
            percentage_sws=self.percentage_sws,
            ttl_port=self.ttl_port,
            ttl_thresholding_id=self.ttl_thresholding,
            ttl_phase2_done_id=self.ttl_phase2_done,
        )

        self.wake_rem = WakeRemDetector(
            multiplior_tresh=self.multiplior_tresh,
            multiplior_tresh_accel=self.multiplior_tresh_accel,
            ttl_port=self.ttl_port,
            ttl_fr_id=self.ttl_wake_REM_fr,
            ttl_accel_id=self.ttl_wake_REM_accel,
            log_fn=lambda msg: self._debug_file_log(msg),
        )

        self.is_detector = ISStateMachine(
            max_time_ON=self.max_time_ON,
            max_time_OFF=self.max_time_OFF,
            min_time_ON=self.min_time_ON,
            min_time_OFF=self.min_time_OFF,
            ttl_port=self.ttl_port,
            ttl_on_id=self.ttl_ON,
            ttl_is_id=self.ttl_IS,
        )

    # -------------------------------------------------------------------
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
            "ttl_wake_REM_fr", "ttl_wake_REM_accel", "ttl_phase2_done",
            "ligne_threshold_integration", "ligne_stop_IS_now", "ligne_print",
            "mean_spike_rate_channel", "accel_channel_1", "accel_channel_2", "accel_channel_3",
            "time_limit_integration", "time_limit_integration_accel", "percentage",
            "time_limit_phase2", "percentage_sws",
            "multiplior_tresh", "multiplior_tresh_accel",
            "max_time_ON", "max_time_OFF", "min_time_OFF", "min_time_ON",
            "saving", "path", "file_name", "debug_name", "ttl_sync",
        ]
        missing = [k for k in required if not hasattr(self, k)]
        if missing:
            raise ValueError(f"[OE] Paramètres manquants dans le fichier de config : {missing}")

    def _debug_file_log(self, msg: str) -> None:
        with open(self.debug_path, "a") as f:
            print(msg, file=f)

    # -------------------------------------------------------------------
    def handle_ttl_event(self, source_node, channel, sample_number, line, state):
        if (line == self.ligne_threshold_integration and state is True) and not self.user_redo_tresh:
            self.user_redo_tresh = True
            self.user_counter_decision += 1
            self.ttl_port.set(self.ttl_thresholding, True)

        if line == self.ligne_threshold_integration and state is False:
            self.ttl_port.set(self.ttl_thresholding, False)

        if line == self.ligne_stop_IS_now and state is True:
            self.user_stop_IS_now = True

        if line == self.ligne_stop_IS_now and state is False:
            self.user_stop_IS_now = False

        if line == self.ligne_print and state is True and self.event_print == 0:
            self.event_print += 1

        if line == self.ligne_print and state is False:
            self.event_print = 0

    # -------------------------------------------------------------------
    def process(self, data):
        self.ttl_port.update_sync_pulse(self.ttl_sync, self.time_counter)

        mean_spike = data[self.mean_spike_rate_channel, :]
        accel1 = np.mean(data[self.accel_channel_1, :])
        accel2 = np.mean(data[self.accel_channel_2, :])
        accel3 = np.mean(data[self.accel_channel_3, :])

        buffer_duration = mean_spike.shape[0] / self.sample_rate
        self.time_counter += buffer_duration

        current_mean = np.mean(mean_spike)
        norm_acceleration = ((accel1 ** 2 + accel2 ** 2 + accel3 ** 2) ** 0.5) * 10000

        self.moy_glissante_buf.push(buffer_duration, current_mean)
        self.var_glissante_buf.push(buffer_duration, norm_acceleration)
        moy_glissante = self.moy_glissante_buf.mean()
        variance_glissante = self.var_glissante_buf.var()

        if self.event_print == 1:
            self.event_print = 2
            self.debuglist.append(
                f"[OE DEBUG] t={self.time_counter:.3f}s"
                f" | current_mean={current_mean:.4f}"
                f" | moy_glissante={moy_glissante:.4f}"
                f" | norm_accel={norm_acceleration:.4f}"
                f" | var_glissante={variance_glissante:.4f}"
                f" | phase2_sws_time={self.calibrator.phase2_sws_time:.1f}s"
                f" | phase2_done={self.calibrator.phase2_done}"
            )

        if self.user_counter_decision < 1:
            return

        # --- Redo threshold (re-trigger utilisateur) -----------------------
        if self.user_redo_tresh and self.user_counter_decision > 0 and self.calibrator.calibrated:
            self.calibrator.reset()
            self.wake_rem.reset()
            self.is_detector.reset()

        # --- Stop IS now (coupe la détection sans recalibrer) --------------
        if self.user_stop_IS_now:
            self.is_detector.force_stop_IS()
            self.wake_rem.reset()

        # --- Phase 1 : calibration en cours ---------------------------------
        if not self.calibrator.calibrated:
            self.calibrator.update_phase1(
                mean_spike, norm_acceleration, buffer_duration, self.time_counter,
                log_fn=lambda msg: self.debuglist.append(msg),
            )
            if self.calibrator.calibrated:
                self.user_redo_tresh = False
            return

        if self.calibrator.threshold_value is None:
            return

        # --- Wake / REM ------------------------------------------------------
        self.wake_rem.update(
            moy_glissante=moy_glissante,
            threshold_value=self.calibrator.threshold_value,
            variance_glissante=variance_glissante,
            variance_init=self.calibrator.variance_init,
            t=self.time_counter,
        )
        wake_state = self.wake_rem.wake_state

        # --- Phase 2 : raffinement du seuil (SWS-only) ------------------------
        self.calibrator.update_phase2(
            mean_spike, buffer_duration, wake_state, self.time_counter,
            log_fn=lambda msg: self.debuglist.append(msg),
        )

        # --- Détection ON/OFF/IS ----------------------------------------------
        self.is_detector.update(
            t=self.time_counter,
            current_mean=current_mean,
            active_threshold=self.calibrator.active_threshold,
            wake_state=wake_state,
            wake_end_accel=self.wake_rem.last_transition_accel(),
            wake_end_fr=self.wake_rem.last_transition_fr(),
        )

    # -------------------------------------------------------------------
    def start_recording(self, recording_dir):
        if self.global_t0 == -1:
            self.global_t0 = self.time_counter
        self.ttl_port.arm_sync_pulse()

    def stop_acquisition(self):
        if self.saving:
            namedossier = os.path.abspath(self.path + self.file_name)
            with open(namedossier, "a") as f:
                line_count = sum(1 for _ in fileinput.input(namedossier))
                print("STOP ACQUISITION NUMBER", int(line_count / 5) + 1, file=f)
                print("List of IS timing markers (starts with 'start'):", file=f)
                print(self.is_detector.L_time_IS, file=f)
                print("List of wake/REM (firing rate) timing markers (starts with 'start'):", file=f)
                print(self.wake_rem.transitions_fr, file=f)
                print("List of wake/REM (accelerometer) timing markers (starts with 'start'):", file=f)
                print(self.wake_rem.transitions_accel, file=f)
                print("Phase 2 SWS threshold:", self.calibrator.threshold_value_sws, file=f)
                print("Phase 2 SWS time accumulated (s):", self.calibrator.phase2_sws_time, file=f)
                print("debug_ list:", file=f)
                print(self.debuglist, file=f)
                print("Temps début recording global t0 (s):", self.global_t0, file=f)
