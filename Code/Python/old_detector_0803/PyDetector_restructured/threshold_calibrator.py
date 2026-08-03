# =============================================================================
# threshold_calibrator.py
# Brique thresholding : Phase 1 (seuil global sur trigger TTL utilisateur)
# + Phase 2 (raffinement automatique du seuil, accumulation SWS-only).
# =============================================================================

import numpy as np


class ThresholdCalibrator:
    """
    Encapsule toute la logique de calibration de seuil de l'ancien
    PyProcessor :
      - Phase 1 : accumulation sur `time_limit_integration`, déclenchée par
        l'utilisateur (TTL ligne_threshold_integration), calcule
        threshold_value = percentile(percentage) + variance_init (accéléro)
      - Phase 2 : une fois Phase 1 faite, accumulation automatique
        pendant les périodes SWS (wake_state == False), sur
        `time_limit_phase2`, calcule threshold_value_sws
        (percentile(percentage_sws))

    Ne connaît rien de la state machine ON/OFF/IS ni du Wake/REM : il
    reçoit juste `mean_spike`, `accel_norm`, `dt`, `wake_state` en entrée.
    """

    def __init__(self, *, time_limit_integration, percentage,
                 time_limit_integration_accel,
                 time_limit_phase2, percentage_sws,
                 ttl_port, ttl_thresholding_id, ttl_phase2_done_id):
        self.time_limit_integration = time_limit_integration
        self.percentage = percentage
        self.time_limit_integration_accel = time_limit_integration_accel
        self.time_limit_phase2 = time_limit_phase2
        self.percentage_sws = percentage_sws

        self.ttl_port = ttl_port
        self.ttl_thresholding_id = ttl_thresholding_id
        self.ttl_phase2_done_id = ttl_phase2_done_id

        self.reset()

    # -------------------------------------------------------------------
    def reset(self) -> None:
        """Relance une calibration Phase 1 + Phase 2 depuis zéro
        (appelé quand l'utilisateur redemande un threshold, cf.
        `ligne_threshold_integration`)."""
        self.calibrated = False           # Phase 1 en cours / faite
        self._time_counter = 0.0
        self._buffer_points = []
        self._accel_points = []
        self.threshold_value = None
        self.mean_acceleration_decay = None

        self._accel_init_buffer = []
        self._accel_init_time = 0.0
        self.accel_threshold_calculated = False
        self.variance_init = None

        self.phase2_done = False
        self._phase2_buffer_points = []
        self.phase2_sws_time = 0.0
        self.threshold_value_sws = None

    @property
    def active_threshold(self):
        return self.threshold_value_sws if self.phase2_done else self.threshold_value

    @property
    def is_ready(self) -> bool:
        """True dès que Phase 1 est calculée (utilisable pour la détection)."""
        return self.calibrated and self.threshold_value is not None

    # -------------------------------------------------------------------
    def update_phase1(self, mean_spike, accel_norm: float, dt: float, t: float, log_fn=None) -> None:
        """A appeler tant que `self.calibrated` est False."""
        self._time_counter += dt
        self._buffer_points.append(mean_spike)
        self._accel_points.append(accel_norm)

        if not self.accel_threshold_calculated:
            self._accel_init_buffer.append(accel_norm)
            self._accel_init_time += dt
            if self._accel_init_time >= self.time_limit_integration_accel:
                self.variance_init = np.var(self._accel_init_buffer)
                self.accel_threshold_calculated = True
                self._accel_init_buffer = []

        if self._time_counter >= self.time_limit_integration:
            self.calibrated = True
            all_values = np.concatenate(self._buffer_points)
            self.threshold_value = np.percentile(all_values, self.percentage)
            self.mean_acceleration_decay = np.mean(self._accel_points)
            if log_fn:
                log_fn(
                    f"[PHASE 1 DONE] t={t:.1f}s"
                    f" | threshold_value={self.threshold_value:.4f} (p{self.percentage})"
                    f" | variance_init={self.variance_init}"
                )

    def update_phase2(self, mean_spike, dt: float, wake_state: bool, t: float, log_fn=None) -> None:
        """A appeler à chaque process() une fois Phase 1 calibrée."""
        if self.phase2_done or wake_state:
            return
        self._phase2_buffer_points.append(mean_spike)
        self.phase2_sws_time += dt

        if self.phase2_sws_time >= self.time_limit_phase2:
            all_sws_values = np.concatenate(self._phase2_buffer_points)
            self.threshold_value_sws = np.percentile(all_sws_values, self.percentage_sws)
            self.phase2_done = True
            self.ttl_port.set(self.ttl_phase2_done_id, True)
            if log_fn:
                log_fn(
                    f"[PHASE 2 DONE] t={t:.1f}s"
                    f" | threshold_value_sws={self.threshold_value_sws:.4f} (p{self.percentage_sws})"
                    f" | SWS accumulated={self.phase2_sws_time:.1f}s"
                )
