# =============================================================================
# is_state_machine.py
# Brique ISA : machine à états ON/OFF -> détection d'Infra-Slow Rhythm (IS).
# C'est le coeur de la logique métier, transcrit à l'identique depuis
# l'ancien PyProcessor.process(), juste isolé de tout le reste
# (thresholding, wake/rem, TTL sync...).
# =============================================================================


class ISStateMachine:
    """
    Reçoit à chaque buffer :
      - t                 : time_counter courant (s)
      - current_mean      : moyenne du firing rate sur ce buffer
      - active_threshold  : seuil courant (Phase 1 ou Phase 2, fourni par
                             ThresholdCalibrator)
      - wake_state        : bool (fourni par WakeRemDetector.wake_state)
      - wake_end_accel / wake_end_fr : dernier instant de transition de
                             chaque critère wake (fournis par
                             WakeRemDetector.last_transition_*())

    Emet ttl_ON / ttl_IS via TTLPort. Expose L_time_IS pour le logging.
    """

    def __init__(self, *, max_time_ON, max_time_OFF, min_time_ON, min_time_OFF,
                 ttl_port, ttl_on_id, ttl_is_id, log_fn=None):
        self.max_time_ON = max_time_ON
        self.max_time_OFF = max_time_OFF
        self.min_time_ON = min_time_ON
        self.min_time_OFF = min_time_OFF

        self.ttl_port = ttl_port
        self.ttl_on_id = ttl_on_id
        self.ttl_is_id = ttl_is_id
        self.log_fn = log_fn

        self.reset()

    # -------------------------------------------------------------------
    def reset(self) -> None:
        """Réinitialise complètement la state machine (redo threshold,
        stop IS now, ou tout simplement au démarrage)."""
        self.ON_state = False
        self.IS_state = False

        self.start_time_ON = -1
        self.end_time_ON = 0
        self.start_time_OFF = -1
        self.end_time_OFF = 0
        self.duration_OFF = -1

        self.L_time_OFFs = []
        self.L_time_ONs = []
        self.L_time_IS = []

        self.off_intervals = []
        self.on_intervals = []

        self.ttl_port.set(self.ttl_on_id, False)
        self.ttl_port.set(self.ttl_is_id, False)

    def force_stop_IS(self) -> None:
        """Equivalent du bloc `user_stop_IS_now` de l'ancien code : coupe
        tout sans réinitialiser les seuils."""
        self.ON_state = False
        self.IS_state = False
        self.start_time_ON = -1
        self.end_time_ON = 0
        self.start_time_OFF = -1
        self.end_time_OFF = 0
        self.L_time_OFFs = []
        self.ttl_port.set(self.ttl_on_id, False)
        self.ttl_port.set(self.ttl_is_id, False)

    # -------------------------------------------------------------------
    def update(self, *, t, current_mean, active_threshold, wake_state,
               wake_end_accel, wake_end_fr) -> None:

        # --- Cas Wake/REM : on coupe tout, pas de détection ON/OFF/IS -----
        if wake_state:
            self.L_time_OFFs = []
            self.start_time_ON = -1
            self.start_time_OFF = -1
            self.ON_state = False
            if self.IS_state:
                end_IS = self.on_intervals[-1]['end'] if self.on_intervals else t
                self.L_time_IS.append(end_IS)
            self.IS_state = False
            self.ttl_port.set(self.ttl_is_id, False)
            return

        # --- Fermeture d'IS si l'OFF courant dépasse max_time_OFF ---------
        cond_max_OFF = (t - self.start_time_OFF < self.max_time_OFF)
        if self.IS_state and self.start_time_OFF >= 0 and not cond_max_OFF:
            self.IS_state = False
            end_IS = self.on_intervals[-1]['end'] if (self.on_intervals and not self.ON_state) else t
            self.L_time_IS.append(end_IS)
            self.L_time_OFFs = []
            self.L_time_ONs = []
            self.start_time_OFF = -1
            self.start_time_ON = -1
            self.ttl_port.set(self.ttl_is_id, False)

        if self.duration_OFF < 0:
            self.start_time_OFF = t
            self.duration_OFF = 0

        # --- Détection ON/OFF ---------------------------------------------
        ON_now = (current_mean - active_threshold) > 0

        if ON_now and not self.ON_state:
            self.ON_state = True
            self.start_time_ON = t
            if self.start_time_OFF >= 0:
                self.end_time_OFF = t
                time_OFF = self.end_time_OFF - self.start_time_OFF
                self.duration_OFF = time_OFF
                self.off_intervals.append({
                    'start': self.start_time_OFF, 'end': self.end_time_OFF, 'duration': time_OFF,
                })
                if len(self.off_intervals) > 5:
                    self.off_intervals.pop(0)
            self.ttl_port.set(self.ttl_on_id, True)

        elif not ON_now and self.ON_state:
            self.ON_state = False
            if self.start_time_ON >= 0:
                self.end_time_ON = t
                time_ON = self.end_time_ON - self.start_time_ON

                self.on_intervals.append({
                    'start': self.start_time_ON, 'end': self.end_time_ON, 'duration': time_ON,
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
                    self.ttl_port.set(self.ttl_is_id, False)

                elif self.min_time_ON <= time_ON <= self.max_time_ON:
                    if (wake_end_accel is not None and wake_end_fr is not None and
                            self.end_time_OFF >= wake_end_accel and
                            self.end_time_OFF >= wake_end_fr):
                        self.L_time_OFFs.append(self.duration_OFF)
                    if wake_state:
                        self.L_time_OFFs = []
                    self.duration_OFF = 0
                    self.start_time_OFF = t
                    self.L_time_ONs.append(time_ON)

            self.ttl_port.set(self.ttl_on_id, False)

        # --- Détection IS : au moins 2 OFF valides dans la fenêtre --------
        if len(self.L_time_OFFs) >= 2 and not wake_state:
            cond_max = all(d < self.max_time_OFF for d in self.L_time_OFFs)
            long_OFFs = [d for d in self.L_time_OFFs if d > self.min_time_OFF]
            cond_min_OFFs = len(long_OFFs) >= 2

            if cond_max and cond_min_OFFs:
                if not self.IS_state:
                    n_back = 2
                    if len(self.off_intervals) >= n_back:
                        start_IS = self.off_intervals[-n_back]['end']
                    else:
                        start_IS = t
                    self.L_time_IS.append(start_IS)
                self.IS_state = True
                self.ttl_port.set(self.ttl_is_id, True)
