# =============================================================================
# wake_rem_detector.py
# Brique Wake/REM : 2 critères indépendants (firing rate glissant vs seuil,
# variance accéléro glissante vs variance_init), chacun avec son propre TTL
# et son propre historique de transitions.
# =============================================================================


class WakeRemDetector:
    """
    Détecte le Wake/REM selon 2 critères parallèles :
      - "fr"    : moy_glissante > multiplior_tresh * threshold_value
      - "accel" : variance_glissante > multiplior_tresh_accel * variance_init

    Émet un TTL par critère à chaque update() (comportement identique à
    l'original : les 2 TTL sont réémis à chaque buffer, pas seulement sur
    front montant/descendant).

    Garde l'historique des instants de transition (start/end) pour chaque
    critère : nécessaire à ISStateMachine (condition sur L_time_OFFs).
    """

    def __init__(self, *, multiplior_tresh, multiplior_tresh_accel,
                 ttl_port, ttl_fr_id, ttl_accel_id, log_fn=None):
        self.multiplior_tresh = multiplior_tresh
        self.multiplior_tresh_accel = multiplior_tresh_accel
        self.ttl_port = ttl_port
        self.ttl_fr_id = ttl_fr_id
        self.ttl_accel_id = ttl_accel_id
        self.log_fn = log_fn

        self.state_fr = False
        self.state_accel = False
        self.transitions_fr = []       # instants de transition (s)
        self.transitions_accel = []

    @property
    def wake_state(self) -> bool:
        return self.state_fr or self.state_accel

    def last_transition_accel(self):
        return self.transitions_accel[-1] if self.transitions_accel else None

    def last_transition_fr(self):
        return self.transitions_fr[-1] if self.transitions_fr else None

    def update(self, *, moy_glissante: float, threshold_value: float,
               variance_glissante: float, variance_init: float, t: float) -> None:
        cond_accel = variance_glissante > self.multiplior_tresh_accel * variance_init
        cond_fr = moy_glissante > self.multiplior_tresh * threshold_value

        # --- critère accéléromètre ---
        self.ttl_port.set(self.ttl_accel_id, cond_accel)
        if cond_accel and not self.state_accel:
            self.transitions_accel.append(t)
            if self.log_fn:
                self.log_fn(f"[WAKE DETECTED] t={t:.1f}s")
        elif not cond_accel and self.state_accel:
            self.transitions_accel.append(t)
            if self.log_fn:
                self.log_fn(f"[WAKE ENDED] t={t:.1f}s")
        self.state_accel = cond_accel

        # --- critère firing rate ---
        self.ttl_port.set(self.ttl_fr_id, cond_fr)
        if cond_fr != self.state_fr:
            self.transitions_fr.append(t)
        self.state_fr = cond_fr

    def reset(self) -> None:
        self.state_fr = False
        self.state_accel = False
        self.ttl_port.set(self.ttl_fr_id, False)
        self.ttl_port.set(self.ttl_accel_id, False)
