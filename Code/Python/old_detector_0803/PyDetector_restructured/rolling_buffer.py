# =============================================================================
# rolling_buffer.py
# Brique générique : accumulation glissante sur une fenêtre temporelle (en s).
# Remplace les 2 `deque` dupliqués (mean_buffers / acceleration_buffers)
# dans l'ancien PyProcessor.
# =============================================================================

from collections import deque
import numpy as np


class RollingWindowStat:
    """
    Accumule des valeurs (scalaires) associées à une durée dt, et ne garde
    que la fenêtre glissante des `window_duration` dernières secondes.

    Usage :
        moy = RollingWindowStat(window_duration=self.time_value_moy)
        moy.push(buffer_duration, current_mean)
        moy.mean()   # -> moyenne glissante
        moy.var()    # -> variance glissante
    """

    def __init__(self, window_duration: float):
        self.window_duration = window_duration
        self._buf = deque()      # deque[(dt, value)]
        self._elapsed = 0.0

    def push(self, dt: float, value: float) -> None:
        self._buf.append((dt, value))
        self._elapsed += dt
        while self._elapsed > self.window_duration and self._buf:
            old_dt, _ = self._buf.popleft()
            self._elapsed -= old_dt

    def values(self):
        return [v for _, v in self._buf]

    def mean(self) -> float:
        vals = self.values()
        return float(np.mean(vals)) if vals else float("nan")

    def var(self) -> float:
        vals = self.values()
        return float(np.var(vals)) if vals else float("nan")

    def is_empty(self) -> bool:
        return len(self._buf) == 0

    def reset(self) -> None:
        self._buf.clear()
        self._elapsed = 0.0
