# =============================================================================
# Configuration file for the classic PyProcessor (two-phase, single detector)
# Only this file should be modified between sessions.
# =============================================================================

# -----------------------------------------------------------------------
# Shared sliding windows
# -----------------------------------------------------------------------

# Duration of the sliding window used to compute the mean firing rate (s).
# Larger = smoother but more delayed response to state changes.
self.time_value_moy = 8

# Duration of the sliding window used to compute the mean acceleration (s).
# Only used in v3/debug (absolute accel mode); kept here for interoperability.
self.time_value_acceleration = 8

# Duration of the sliding window used to compute the acceleration variance (s).
# Used in the classic/parallel versions (variance-based wake detection).
# Shorter = more reactive to movement bursts.
self.bin_duration_accel = 1.0

# -----------------------------------------------------------------------
# Output TTL lines (sent from Python processor to Open-Ephys)
# Note: TTL panel index in Open-Ephys = value + 1
# -----------------------------------------------------------------------

# TTL line signaling an ON (avalanche) state.
self.ttl_ON = 7

# TTL line signaling an InfraSlow Rhythm (IS) state.
self.ttl_IS = 4

# TTL line high during Phase 1 threshold integration.
self.ttl_thresholding = 3

# TTL line signaling wake/REM detected via firing rate.
self.ttl_wake_REM_fr = 1

# TTL line signaling wake/REM detected via accelerometer.
self.ttl_wake_REM_accel = 12

# TTL line that fires once when Phase 2 threshold computation is complete.
self.ttl_phase2_done = 6

# TTL line used to trigger a stimulation pulse.
self.ttl_stim = 5

self.ttl_sync = 4  # TTL envoyé à l'Arduino pour synchroniser le démarrage

# -----------------------------------------------------------------------
# Input TTL lines (received from the user toggle panel in Open-Ephys)
# Note: TTL panel index in Open-Ephys = value + 1
# -----------------------------------------------------------------------

# TTL line the user presses to start/restart threshold integration (Phase 1).
self.ligne_threshold_integration = 9

# TTL line the user presses to immediately stop IS detection and reset states.
self.ligne_stop_IS_now = 14

# TTL line the user presses to trigger a one-shot debug print to the log file.
self.ligne_print = 19

# -----------------------------------------------------------------------
# Channel indices
# Position in the channel map (0-indexed), not the physical channel number.
# -----------------------------------------------------------------------

# Channel carrying the pre-computed mean spike rate (output of a spike sorter
# or a MUA rate estimator upstream in the Open-Ephys chain).
self.mean_spike_rate_channel = 32

# Three axes of the accelerometer (X, Y, Z).
# The norm sqrt(x²+y²+z²) is used for movement detection.
self.accel_channel_1 = 128
self.accel_channel_2 = 129
self.accel_channel_3 = 130

# -----------------------------------------------------------------------
# Phase 1 — wake/REM threshold computation
# Triggered by the user; data are accumulated for time_limit_integration seconds.
# -----------------------------------------------------------------------

# Duration of Phase 1 accumulation (s).
# Must be long enough to capture a representative baseline firing rate.
self.time_limit_integration = 30.0

# Duration of the sub-window used to estimate the resting acceleration variance (s).
# Must be <= time_limit_integration. The animal should be still during this period.
self.time_limit_integration_accel = 10.0

# Percentile of the firing rate distribution used as the Phase 1 FR threshold.
# Also used as the IS detection threshold until Phase 2 is complete.
# Lower = more sensitive (detects more avalanches), higher = more conservative.
self.percentage = 20

# -----------------------------------------------------------------------
# Phase 2 — SWS-specific threshold refinement
# Starts automatically after Phase 1; accumulates only during non-wake/REM periods.
# -----------------------------------------------------------------------

# Amount of pure SWS data to accumulate before computing the Phase 2 threshold (s).
# Wake/REM episodes pause accumulation without discarding existing data.
self.time_limit_phase2 = 300.0

# Percentile of the SWS-only firing rate distribution used as the Phase 2 IS threshold.
# Replaces the Phase 1 threshold once Phase 2 is complete.
# Typically higher than `percentage` because the SWS distribution is narrower.
self.percentage_sws = 40

# -----------------------------------------------------------------------
# Wake/REM detection thresholds
# -----------------------------------------------------------------------

# Firing rate multiplier: wake/REM is flagged when the sliding mean FR exceeds
# multiplior_tresh * threshold_value (Phase 1 FR threshold).
# Higher = less sensitive to FR-based wake detection.
self.multiplior_tresh = 4

# Acceleration multiplier: wake/REM is flagged when the sliding acceleration
# variance exceeds multiplior_tresh_accel * variance_init (Phase 1 accel variance).
# Higher = less sensitive to movement-based wake detection.
# Set > 1.5 to avoid triggering on REM micro-movements.
self.multiplior_tresh_accel = 1.5

# Percentile of the acceleration distribution used as the absolute accel threshold.
# Only used in v3/debug (absolute accel mode); kept here for interoperability.
self.percentage_accel = 70

# -----------------------------------------------------------------------
# ON / OFF / IS detection
# -----------------------------------------------------------------------

# Maximum duration of a single ON (avalanche) period (s).
# An ON longer than this resets IS detection (interpreted as sustained firing,
# not a discrete avalanche).
self.max_time_ON = 14

# Maximum duration of an OFF (inter-avalanche) period (s).
# An OFF longer than this ends the current IS episode.
self.max_time_OFF = 16

# Minimum duration of an OFF period to be counted toward IS detection (s).
# Very short OFFs (< min_time_OFF) are ignored when evaluating the IS rhythm.
self.min_time_OFF = 0.5

# Minimum duration of an ON period to be counted as a valid avalanche (s).
# Very brief ON transients (< min_time_ON) are ignored.
self.min_time_ON = 0.3

# -----------------------------------------------------------------------
# Stimulation protocol
# -----------------------------------------------------------------------

# Maximum number of stimulation pulses to deliver before stopping.
self.stim_max_per_type = 100

# Minimum interval between two stimulation pulses (s).
# The timer resets whenever the reference detector leaves IS state.
self.stim_interval = 60.0

# Whether the stimulation timer is currently active (internal state; set to False).
self.stim_timer_active = False

# -----------------------------------------------------------------------
# File saving
# -----------------------------------------------------------------------

# Whether to save IS and wake/REM timing markers at the end of acquisition.
self.saving = True

# Directory where output files will be written (must exist).
self.path = "/home/lab-openephys/open-ephys/Detectors/Detectors outputs/"

# Name of the main output file storing IS and wake/REM timing markers.
self.file_name = "IS_wake_timings_classic.txt"

# Name of the real-time debug log file (wake/REM events, phase transitions, etc.).
self.debug_name = "debugTHRESHOLDS.txt"
