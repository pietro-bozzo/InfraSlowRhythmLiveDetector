# =============================================================================
# Python Processor for Open-Ephys Plugin — Parallel Multi-Config Detector
# =============================================================================
# Ce fichier ne doit PAS être modifié entre les sessions.
# Toute la configuration (canaux, TTL, détecteurs) est dans oe_config.py.
#
# Chemin du fichier de config (seule constante à adapter si besoin) :
CONFIG_PATH = "/mnt/hubel-data-103/Guillaume/InfraSlowRhythmLiveDetector/Code/Python/Multitest_processor/OE_multitest_CONFIG.py"
# =============================================================================

import numpy as np
import oe_pyprocessor
from collections import deque
import os


# =============================================================================
# ISDetector : un détecteur indépendant avec ses propres paramètres et état
# (doit rester dans ce fichier : il est référencé dans oe_config.py)
# =============================================================================
class ISDetector:

    def __init__(self,
                 name,
                 description="",
                 # Phase 1
                 time_limit_integration=30.0,
                 time_limit_integration_accel=10.0,
                 percentage=20,
                 # Phase 2
                 time_limit_phase2=300.0,
                 percentage_sws=40,
                 # Wake/REM detection
                 multiplior_tresh=3,
                 multiplior_tresh_accel=1.5,
                 # ON/OFF/IS detection
                 max_time_ON=14,
                 max_time_OFF=16,
                 min_time_ON=0.3,
                 min_time_OFF=0.5,
                 # Accel sliding window
                 bin_duration_accel=1.0):

        self.name = name
        self.description = description

        self.time_limit_integration = time_limit_integration
        self.time_limit_integration_accel = time_limit_integration_accel
        self.percentage = percentage

        self.time_limit_phase2 = time_limit_phase2
        self.percentage_sws = percentage_sws

        self.multiplior_tresh = multiplior_tresh
        self.multiplior_tresh_accel = multiplior_tresh_accel

        self.max_time_ON = max_time_ON
        self.max_time_OFF = max_time_OFF
        self.min_time_ON = min_time_ON
        self.min_time_OFF = min_time_OFF

        self.bin_duration_accel = bin_duration_accel

        self.reset_all()

    # -------------------------------------------------------------------------
    def reset_all(self):
        """Réinitialise tout : phases 1 & 2 + états de détection."""

        # Phase 1
        self.threshold_calculated = False
        self.threshold_value = None
        self.threshold_time_counter = 0.0
        self.buffer_points = []
        self.accel_points = []
        self.variance_init = None
        self.accel_init_buffer = []
        self.accel_init_time = 0.0
        self.accel_threshold_calculated = False
        self.mean_acceleration_decay = None

        # Phase 2
        self.phase2_buffer_points = []
        self.phase2_sws_time = 0.0
        self.phase2_done = False
        self.threshold_value_sws = None

        self._reset_detection_states()

    # -------------------------------------------------------------------------
    def _reset_detection_states(self):
        """Réinitialise uniquement les états de détection (garde les seuils)."""
        self.ON_state = False
        self.IS_state = False
        self.wake_REM_state_fr = False
        self.wake_REM_state_accel = False

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

    # =========================================================================
    # PHASE 1
    # =========================================================================
    def accumulate_phase1(self, mean_spike, norm_acceleration, buffer_duration):
        """Accumule les données pour la Phase 1. Retourne True quand terminée."""
        if self.threshold_calculated:
            return True

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
            all_values = np.concatenate(self.buffer_points)
            self.threshold_value = np.percentile(all_values, self.percentage)
            self.mean_acceleration_decay = np.mean(self.accel_points)
            self.threshold_calculated = True
            return True

        return False

    # =========================================================================
    # PHASE 2
    # =========================================================================
    def accumulate_phase2(self, mean_spike, buffer_duration, wake_REM_state):
        """Accumule les données SWS pour la Phase 2. Retourne True quand terminée."""
        if self.phase2_done:
            return True

        if not wake_REM_state:
            self.phase2_buffer_points.append(mean_spike)
            self.phase2_sws_time += buffer_duration

            if self.phase2_sws_time >= self.time_limit_phase2:
                all_sws_values = np.concatenate(self.phase2_buffer_points)
                self.threshold_value_sws = np.percentile(all_sws_values, self.percentage_sws)
                self.phase2_done = True
                return True

        return False

    # =========================================================================
    # DÉTECTION
    # =========================================================================
    def process_detection(self, current_mean, moy_glissante, variance_glissante,
                          buffer_duration, time_counter):
        """Exécute un pas de détection complet. Retourne (IS_state, wake_REM_state)."""

        if not self.threshold_calculated or self.variance_init is None:
            return self.IS_state, False

        active_threshold = self.threshold_value_sws if self.phase2_done else self.threshold_value

        # ---- Wake/REM ----
        condition_wake = variance_glissante > self.multiplior_tresh_accel * self.variance_init
        condition_rem_wake = moy_glissante > self.multiplior_tresh * self.threshold_value

        if condition_wake:
            if not self.wake_REM_state_accel:
                self.L_time_wake_REM_accel.append(time_counter)
            self.wake_REM_state_accel = True
        else:
            if self.wake_REM_state_accel:
                self.L_time_wake_REM_accel.append(time_counter)
            self.wake_REM_state_accel = False

        if condition_rem_wake:
            if not self.wake_REM_state_fr:
                self.L_time_wake_REM_fr.append(time_counter)
            self.wake_REM_state_fr = True
        else:
            if self.wake_REM_state_fr:
                self.L_time_wake_REM_fr.append(time_counter)
            self.wake_REM_state_fr = False

        wake_REM_state = self.wake_REM_state_fr or self.wake_REM_state_accel

        if wake_REM_state:
            self.L_time_OFFs = []
            self.start_time_ON = -1
            self.start_time_OFF = -1
            self.ON_state = False
            if self.IS_state:
                end_IS = self.on_intervals[-1]['end'] if len(self.on_intervals) > 0 else time_counter
                self.L_time_IS.append(end_IS)
            self.IS_state = False
            return False, True

        # ---- Stop IS si OFF trop long ----
        cond_max_OFF = (time_counter - self.start_time_OFF < self.max_time_OFF)
        if self.IS_state and self.start_time_OFF >= 0 and not cond_max_OFF:
            self.IS_state = False
            end_IS = (self.on_intervals[-1]['end']
                      if len(self.on_intervals) > 0 and not self.ON_state
                      else time_counter)
            self.L_time_IS.append(end_IS)
            self.L_time_OFFs = []
            self.L_time_ONs = []
            self.start_time_OFF = -1
            self.start_time_ON = -1

        if self.duration_OFF < 0:
            self.start_time_OFF = time_counter
            self.duration_OFF = 0

        ON_now = (current_mean - active_threshold) > 0

        # OFF → ON
        if ON_now and not self.ON_state:
            self.ON_state = True
            self.start_time_ON = time_counter
            if self.start_time_OFF >= 0:
                self.end_time_OFF = time_counter
                time_OFF = self.end_time_OFF - self.start_time_OFF
                self.duration_OFF = time_OFF
                self.off_intervals.append({
                    'start': self.start_time_OFF,
                    'end': self.end_time_OFF,
                    'duration': time_OFF,
                })
                if len(self.off_intervals) > 5:
                    self.off_intervals.pop(0)

        # ON → OFF
        elif not ON_now and self.ON_state:
            self.ON_state = False
            if self.start_time_ON >= 0:
                self.end_time_ON = time_counter
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

                elif self.min_time_ON <= time_ON <= self.max_time_ON:
                    if (len(self.L_time_wake_REM_accel) > 0 and
                            len(self.L_time_wake_REM_fr) > 0 and
                            self.end_time_OFF >= self.L_time_wake_REM_accel[-1] and
                            self.end_time_OFF >= self.L_time_wake_REM_fr[-1]):
                        self.L_time_OFFs.append(self.duration_OFF)
                    if wake_REM_state:
                        self.L_time_OFFs = []
                    self.duration_OFF = 0
                    self.start_time_OFF = time_counter
                    self.L_time_ONs.append(time_ON)

        # ---- IS ----
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
                        start_IS = time_counter
                    self.L_time_IS.append(start_IS)
                self.IS_state = True

        return self.IS_state, wake_REM_state


# =============================================================================
# PyProcessor : orchestrateur principal
# =============================================================================
class PyProcessor:

    def __init__(self, processor, num_channels, sample_rate):
        print("Num Channels:", num_channels, "| Sample Rate:", sample_rate)

        self.processor = processor
        self.num_channels = num_channels
        self.sample_rate = sample_rate

        self.time_counter = 0.0
        self.global_t0 = -1

        # Sliding windows partagées
        self.mean_buffers = deque()
        self.mean_buffer_time = 0.0
        self.acceleration_buffers = deque()
        self.acceleration_buffer_time = 0.0

        # États internes non configurables
        self.user_redo_tresh = False
        self.user_counter_decision = 0
        self.user_stop_IS_now = False
        self.event_print = 0
        self.debuglist = []
        self.all_phase1_done = False
        self.stim_count = 0
        self.stim_timer = 0.0
        self.stim_done = False

        # Charger la configuration externe
        self._load_config()

    # -------------------------------------------------------------------------
    def _load_config(self):
        """
        Charge oe_config.py via exec().
        Toutes les lignes 'self.xxx = ...' du fichier sont exécutées dans le
        contexte de cette instance, ce qui revient à les écrire dans __init__.
        ISDetector est injecté dans le namespace d'exécution pour être
        accessible depuis le fichier de config.
        """
        config_path = os.path.abspath(CONFIG_PATH)
        if not os.path.isfile(config_path):
            raise FileNotFoundError(
                f"[OE] Fichier de configuration introuvable : {config_path}\n"
                f"Créez ce fichier ou modifiez CONFIG_PATH en tête du script."
            )

        with open(config_path, "r") as f:
            config_code = f.read()

        # ISDetector doit être accessible dans le namespace du exec()
        exec(config_code, {"ISDetector": ISDetector, "self": self})

        print(f"[OE] Config chargée depuis : {config_path}")
        print(f"[OE] {len(self.detectors)} détecteur(s) : {[d.name for d in self.detectors]}")

        # Vérifications de sécurité
        required = [
            "time_value_moy", "bin_duration_accel",
            "ttl_ON", "ttl_IS", "ttl_thresholding", "ttl_wake_REM_fr",
            "ttl_wake_REM_accel", "ttl_phase2_done",
            "ligne_threshold_integration", "ligne_stop_IS_now", "ligne_print",
            "mean_spike_rate_channel", "accel_channel_1", "accel_channel_2", "accel_channel_3",
            "saving", "path", "file_name", "debug_name",
            "stim_max_per_type", "stim_interval", "ttl_stim",
            "detectors", "ref_det",
        ]
        missing = [k for k in required if not hasattr(self, k)]
        if missing:
            raise ValueError(f"[OE] Paramètres manquants dans oe_config.py : {missing}")

    # =========================================================================
    # TTL event handler
    # =========================================================================
    def handle_ttl_event(self, source_node, channel, sample_number, line, state):

        if line == self.ligne_threshold_integration and state == True and not self.user_redo_tresh:
            self.user_redo_tresh = True
            self.user_counter_decision += 1
            self.processor.add_python_event(self.ttl_thresholding, True)
            for det in self.detectors:
                det.reset_all()
            self.all_phase1_done = False
            print(f"[OE] Phase 1 démarrée pour {len(self.detectors)} détecteurs.")

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
    # Main processing loop
    # =========================================================================
    def process(self, data):

        # ---- Sliding windows partagées ----
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

        # ---- Debug print ----
        if self.event_print == 1:
            self.event_print = 2
            n_p1 = sum(1 for d in self.detectors if d.threshold_calculated)
            n_p2 = sum(1 for d in self.detectors if d.phase2_done)
            self.debuglist.append(
                f"[OE DEBUG] t={self.time_counter:.3f}s"
                f" | cur={current_mean:.4f} | moy={moy_glissante:.4f}"
                f" | accel={norm_acceleration:.4f} | var={variance_glissante:.4f}"
                f" | p1={n_p1}/{len(self.detectors)}"
                f" | p2={n_p2}/{len(self.detectors)}"
            )

        # ---- Attendre déclenchement user ----
        if self.user_counter_decision < 1:
            return

        # ---- Stop IS ----
        if self.user_stop_IS_now:
            for det in self.detectors:
                det._reset_detection_states()
            self.processor.add_python_event(self.ttl_ON, False)
            self.processor.add_python_event(self.ttl_IS, False)
            self.processor.add_python_event(self.ttl_wake_REM_fr, False)
            self.processor.add_python_event(self.ttl_wake_REM_accel, False)

        # =========================================================================
        # PHASE 1 (parallèle) — bloquante jusqu'à ce que tous les détecteurs aient fini
        # =========================================================================
        if not self.all_phase1_done:
            all_done = True
            for det in self.detectors:
                done = det.accumulate_phase1(mean_spike, norm_acceleration, buffer_duration)
                if not done:
                    all_done = False
            if all_done:
                self.all_phase1_done = True
                self.user_redo_tresh = False
                self.processor.add_python_event(self.ttl_thresholding, False)
                print(f"[OE] Phase 1 terminée (t={self.time_counter:.1f}s)")
                for det in self.detectors:
                    print(f"  {det.name}: thresh_fr={det.threshold_value:.4f}"
                          f" | variance_init={det.variance_init:.6f}")
            return

        # =========================================================================
        # PHASE 1 terminée → détection + Phase 2 en parallèle
        # =========================================================================
        phase2_was_done_ref = self.ref_det.phase2_done

        for det in self.detectors:
            is_state, wake_REM_state = det.process_detection(
                current_mean, moy_glissante, variance_glissante,
                buffer_duration, self.time_counter
            )
            det.accumulate_phase2(mean_spike, buffer_duration, wake_REM_state)

        # TTL phase2_done quand ref_det passe en Phase 2
        if not phase2_was_done_ref and self.ref_det.phase2_done:
            self.processor.add_python_event(self.ttl_phase2_done, True)
            print(f"[OE] Phase 2 terminée pour ref_det (t={self.time_counter:.1f}s)"
                  f" | thresh_sws={self.ref_det.threshold_value_sws:.4f}")

        # TTL de sortie depuis ref_det
        self.processor.add_python_event(self.ttl_IS, self.ref_det.IS_state)
        self.processor.add_python_event(self.ttl_ON, self.ref_det.ON_state)
        self.processor.add_python_event(self.ttl_wake_REM_fr, self.ref_det.wake_REM_state_fr)
        self.processor.add_python_event(self.ttl_wake_REM_accel, self.ref_det.wake_REM_state_accel)

        # ---- Stimulation ----
        if not self.stim_done:
            ref_IS = self.ref_det.IS_state
            ref_wake = self.ref_det.wake_REM_state_fr or self.ref_det.wake_REM_state_accel

            if ref_IS and not ref_wake:
                self.stim_timer += buffer_duration
                if self.stim_timer >= self.stim_interval:
                    self.stim_timer = 0.0
                    self.processor.add_python_event(self.ttl_stim, True)
                    self.processor.add_python_event(self.ttl_stim, False)
                    self.stim_count += 1
                    msg = (f"[STIM] count={self.stim_count}/{self.stim_max_per_type}"
                           f" t={self.time_counter:.2f}s")
                    self.debuglist.append(msg)
                    if self.stim_count >= self.stim_max_per_type:
                        self.stim_done = True
            else:
                self.stim_timer = 0.0

    # =========================================================================
    # Callbacks
    # =========================================================================
    def start_acquisition(self):
        print("[OE] Début acquisition")

    def start_recording(self, recording_dir):
        if self.global_t0 == -1:
            self.global_t0 = self.time_counter

    def stop_acquisition(self):
        if not self.saving:
            return

        namedossier = os.path.abspath(self.path + self.file_name)
        debug_path  = os.path.abspath(self.path + self.debug_name)

        try:
            with open(namedossier, "r") as f_read:
                line_count = sum(1 for _ in f_read)
        except FileNotFoundError:
            line_count = 0

        with open(namedossier, "a") as f:
            print(f"STOP ACQUISITION NUMBER {int(line_count / 5) + 1}", file=f)
            print(f"Config: {CONFIG_PATH}", file=f)
            print(f"global_t0 (s): {self.global_t0}", file=f)
            print("", file=f)

            for det in self.detectors:
                print(f"=== {det.name} : {det.description} ===", file=f)
                print(f"  threshold_value (Phase 1, p{det.percentage}): {det.threshold_value}", file=f)
                print(f"  threshold_value_sws (Phase 2, p{det.percentage_sws}): {det.threshold_value_sws}", file=f)
                print(f"  phase2_sws_time_accumulated (s): {det.phase2_sws_time:.1f}", file=f)
                print(f"  variance_init: {det.variance_init}", file=f)
                print(f"  IS timing markers: {det.L_time_IS}", file=f)
                print(f"  wake/REM (FR) markers: {det.L_time_wake_REM_fr}", file=f)
                print(f"  wake/REM (accel) markers: {det.L_time_wake_REM_accel}", file=f)
                print("", file=f)

            print(f"debug list: {self.debuglist}", file=f)

        with open(debug_path, "a") as f:
            print(f"[stop_acquisition] t={self.time_counter:.1f}s", file=f)
            for det in self.detectors:
                print(f"  {det.name}: phase2_done={det.phase2_done}"
                      f" | sws_time={det.phase2_sws_time:.1f}s"
                      f" | thresh_sws={det.threshold_value_sws}", file=f)