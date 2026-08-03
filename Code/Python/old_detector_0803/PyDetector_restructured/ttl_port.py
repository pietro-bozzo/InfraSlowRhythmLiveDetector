# =============================================================================
# ttl_port.py
# Brique TTL : encapsule les appels à processor.add_python_event()
# + gère le pulse de synchronisation Arduino/Python au démarrage
# de l'acquisition (ex `_sync_ttl_pending` / `_sync_ttl_end_time`).
# =============================================================================


class TTLPort:
    """
    Toutes les briques (ISStateMachine, WakeRemDetector, ThresholdCalibrator)
    passent par cet objet pour émettre des TTL, au lieu d'appeler
    self.processor.add_python_event directement. Ça centralise le point de
    contact avec l'API Open-Ephys, et facilite le mock en test unitaire
    (il suffit de passer un faux `processor`).
    """

    def __init__(self, processor):
        self.processor = processor
        self._sync_pending = False
        self._sync_end_time = 0.0

    def set(self, ttl_id: int, state: bool) -> None:
        self.processor.add_python_event(ttl_id, state)

    # --- Pulse de synchronisation (1s) au démarrage d'enregistrement ---------

    def arm_sync_pulse(self) -> None:
        """A appeler dans start_recording()."""
        self._sync_pending = True

    def update_sync_pulse(self, ttl_sync_id: int, time_counter: float,
                           pulse_duration: float = 1.0) -> None:
        """A appeler à chaque process(), avant tout le reste."""
        if self._sync_pending:
            self._sync_pending = False
            self.set(ttl_sync_id, True)
            self._sync_end_time = time_counter + pulse_duration

        if self._sync_end_time > 0 and time_counter >= self._sync_end_time:
            self.set(ttl_sync_id, False)
            self._sync_end_time = 0.0
