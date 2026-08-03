# =============================================================================
# Configuration file for the parallel multi-detector PyProcessor
# Only this file should be modified between sessions.
# The main code (oe_pyprocessor_parallel.py) must not be changed.
# =============================================================================
from datetime import datetime
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
# -----------------------------------------------------------------------
# Shared sliding windows
# (computed once and passed to all detectors at each buffer)
# -----------------------------------------------------------------------

# Duration of the sliding window used to compute the mean firing rate (s).
# Larger = smoother but more delayed response to state changes.
self.time_value_moy = 8

self.time_value_acceleration = 8

# Duration of the sliding window used to compute the acceleration variance (s).
# Shorter = more reactive to sudden movement bursts.
self.bin_duration_accel = 1.0
self.bin_duration_accel_window = 5.0
self.bin_real_wake_acc = 2.0#Ils sont inutiles en vrai, modifier direct dans les pramètres des IS Detector mais je les laisse pour la compatibilité avec OE_classic_CONFIG.py


# -----------------------------------------------------------------------
# Output TTL lines (sent from Python processor to Open-Ephys)
# Reflect the reference detector state only (self.ref_det).
# Note: TTL panel index in Open-Ephys = value + 1
# -----------------------------------------------------------------------

# TTL line signaling an ON (avalanche) state.
self.ttl_ON = 7

# TTL line signaling an InfraSlow Rhythm (IS) state.
self.ttl_IS = 4

# TTL line held high during Phase 1 threshold integration.
self.ttl_thresholding = 3

# TTL line signaling wake/REM detected via firing rate (reference detector).
self.ttl_wake_REM_fr = 1

# TTL line signaling wake/REM detected via accelerometer (reference detector).
self.ttl_wake_REM_accel = 12

#TTL line signaling real wake detected via the accelerometer.
self.ttl_real_wake_acc=13

# TTL line that fires once when the reference detector completes Phase 2.
self.ttl_phase2_done = 6

# TTL line used to trigger a stimulation pulse.
self.ttl_stim = 5

self.ttl_sync = 4  # TTL envoyé à l'Arduino pour synchroniser le démarrage

# -----------------------------------------------------------------------
# Input TTL lines (received from the user toggle panel in Open-Ephys)
# Note: TTL panel index in Open-Ephys = value + 1
# -----------------------------------------------------------------------

# TTL line the user presses to start/restart threshold integration (Phase 1)
# for all detectors simultaneously.
self.ligne_threshold_integration = 9

# TTL line the user presses to immediately stop IS detection and reset all
# detector states (thresholds are preserved).
self.ligne_stop_IS_now = 14

# TTL line the user presses to trigger a one-shot debug print to the log file.
self.ligne_print = 19

#Ajustement manuel du seuil de détection de l'IS (Phase 1) via le panneau de contrôle Open-Ephys
self.increase_threshold = 22

self.decrease_threshold = 23

self.pas_thresh_ajust = 0.1


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

self.n_channels = 142  # total number of channels in the stream


# -----------------------------------------------------------------------

self.debugging = False  # Whether to print debug info to the log file (phase transitions, stim events, etc.).

# -----------------------------------------------------------------------
# File saving
# -----------------------------------------------------------------------

# Whether to save IS and wake/REM timing markers at the end of acquisition.
self.saving = True

# Directory where output files will be written (must exist).
self.path = "/mnt/hubel-data-103/Guillaume/InfraSlowRhythmLiveDetector/Code/Python/FINAL_Detector/CONFIGS/Hubel_tests/Outputs_pyDetector/Perceval-12-12"

# Name of the main output file storing IS and wake/REM timing markers
# for every detector.
self.file_name = f"IS_wake_timings_FINAL_{timestamp}.txt"

# Name of the real-time debug log file (phase transitions, stim events, etc.).
self.debug_name = f"debug_FINAL_{timestamp}.txt"

# -----------------------------------------------------------------------
# Parallel detectors
# Add, remove, or edit ISDetector instances to define the parameter sweep.
# ISDetector is available directly (injected by the main code).
#
# ISDetector parameters:
#   name                       : short identifier, used in the output file
#   description                : human-readable label for the output file
#   time_limit_integration     : Phase 1 accumulation duration (s)         [default: 30.0]
#   time_limit_integration_accel : accel variance estimation window (s)    [default: 10.0]
#   percentage                 : Phase 1 FR threshold percentile            [default: 20]
#   time_limit_phase2          : SWS to accumulate before Phase 2 (s)      [default: 300.0]
#   percentage_sws             : Phase 2 FR threshold percentile            [default: 40]
#   multiplior_tresh           : FR wake/REM multiplier                     [default: 3]
#   multiplior_tresh_accel     : accel variance wake/REM multiplier         [default: 1.5]
#   max_time_ON                : max avalanche duration before IS reset (s) [default: 14]
#   max_time_OFF               : max inter-avalanche gap before IS end (s)  [default: 16]
#   min_time_ON                : min avalanche duration to count (s)        [default: 0.3]
#   min_time_OFF               : min inter-avalanche gap to count (s)       [default: 0.5]
# -----------------------------------------------------------------------
self.detectors = [

    # ---- Reference: exact replica of the classic v1 single-detector ----
    ISDetector(
        name='ref_v1',
        description='Exact replica of v1 (p20/p40, accel×1.2, phase2=5min)',
        time_limit_integration=30.0,
        time_limit_integration_accel=10.0,
        percentage=20,
        time_limit_phase2=300.0,
        percentage_sws=40,
        multiplior_tresh=3,
        multiplior_tresh_accel=1.2,
        max_time_ON=14,
        max_time_OFF=40,
        min_time_ON=0,
        min_time_OFF=0,
        bin_duration_accel=1.0,
        bin_duration_accel_window=5.0,
        bin_real_wake_acc=0.5
    ),

        ISDetector(
        name='5-1',
        description='duration_accel_window 5.0, real_wake_acc 1.0',
        time_limit_integration=30.0,
        time_limit_integration_accel=10.0,
        percentage=20,
        time_limit_phase2=300.0,
        percentage_sws=40,
        multiplior_tresh=3,
        multiplior_tresh_accel=1.2,
        max_time_ON=14,
        max_time_OFF=40,
        min_time_ON=0,
        min_time_OFF=0,
        bin_duration_accel=1.0,
        bin_duration_accel_window=5.0,
        bin_real_wake_acc=1.0
    ),

            ISDetector(
        name='5-1.5',
        description='duration_accel_window 5.0, real_wake_acc 1.5',
        time_limit_integration=30.0,
        time_limit_integration_accel=10.0,
        percentage=20,
        time_limit_phase2=300.0,
        percentage_sws=40,
        multiplior_tresh=3,
        multiplior_tresh_accel=1.2,
        max_time_ON=14,
        max_time_OFF=40,
        min_time_ON=0,
        min_time_OFF=0,
        bin_duration_accel=1.0,
        bin_duration_accel_window=5.0,
        bin_real_wake_acc=1.5
    ),

        ISDetector(
        name='3-0.3',
        description='duration_accel_window 3.0, real_wake_acc 0.3',
        time_limit_integration=30.0,
        time_limit_integration_accel=10.0,
        percentage=20,
        time_limit_phase2=300.0,
        percentage_sws=40,
        multiplior_tresh=3,
        multiplior_tresh_accel=1.2,
        max_time_ON=14,
        max_time_OFF=40,
        min_time_ON=0,
        min_time_OFF=0,
        bin_duration_accel=1.0,
        bin_duration_accel_window=3.0,
        bin_real_wake_acc=0.3
    ),

        ISDetector(
        name='3-0.6',
        description='duration_accel_window 3.0, real_wake_acc 0.6',
        time_limit_integration=30.0,
        time_limit_integration_accel=10.0,
        percentage=20,
        time_limit_phase2=300.0,
        percentage_sws=40,
        multiplior_tresh=3,
        multiplior_tresh_accel=1.2,
        max_time_ON=14,
        max_time_OFF=40,
        min_time_ON=0,
        min_time_OFF=0,
        bin_duration_accel=1.0,
        bin_duration_accel_window=3.0,
        bin_real_wake_acc=0.6
    ),

        ISDetector(
        name='3-0.9',
        description='duration_accel_window 3.0, real_wake_acc 0.9',
        time_limit_integration=30.0,
        time_limit_integration_accel=10.0,
        percentage=20,
        time_limit_phase2=300.0,
        percentage_sws=40,
        multiplior_tresh=3,
        multiplior_tresh_accel=1.2,
        max_time_ON=14,
        max_time_OFF=40,
        min_time_ON=0,
        min_time_OFF=0,
        bin_duration_accel=1.0,
        bin_duration_accel_window=3.0,
        bin_real_wake_acc=0.9
    ),

        ISDetector(
        name='7-0.7',
        description='duration_accel_window 7.0, real_wake_acc 0.7',
        time_limit_integration=30.0,
        time_limit_integration_accel=10.0,
        percentage=20,
        time_limit_phase2=300.0,
        percentage_sws=40,
        multiplior_tresh=3,
        multiplior_tresh_accel=1.2,
        max_time_ON=14,
        max_time_OFF=40,
        min_time_ON=0,
        min_time_OFF=0,
        bin_duration_accel=1.0,
        bin_duration_accel_window=7.0,
        bin_real_wake_acc=0.7
    ),

        ISDetector(
        name='7-1.4',
        description='duration_accel_window 7.0, real_wake_acc 1.4',
        time_limit_integration=30.0,
        time_limit_integration_accel=10.0,
        percentage=20,
        time_limit_phase2=300.0,
        percentage_sws=40,
        multiplior_tresh=3,
        multiplior_tresh_accel=1.2,
        max_time_ON=14,
        max_time_OFF=40,
        min_time_ON=0,
        min_time_OFF=0,
        bin_duration_accel=1.0,
        bin_duration_accel_window=7.0,
        bin_real_wake_acc=1.4
    ),

        ISDetector(
        name='7-2.1',
        description='duration_accel_window 7.0, real_wake_acc 2.1',
        time_limit_integration=30.0,
        time_limit_integration_accel=10.0,
        percentage=20,
        time_limit_phase2=300.0,
        percentage_sws=40,
        multiplior_tresh=3,
        multiplior_tresh_accel=1.2,
        max_time_ON=14,
        max_time_OFF=40,
        min_time_ON=0,
        min_time_OFF=0,
        bin_duration_accel=1.0,
        bin_duration_accel_window=7.0,
        bin_real_wake_acc=2.1
    ),

        ISDetector(
        name='7-3.5',
        description='duration_accel_window 7.0, real_wake_acc 3.5',
        time_limit_integration=30.0,
        time_limit_integration_accel=10.0,
        percentage=20,
        time_limit_phase2=300.0,
        percentage_sws=40,
        multiplior_tresh=3,
        multiplior_tresh_accel=1.2,
        max_time_ON=14,
        max_time_OFF=40,
        min_time_ON=0,
        min_time_OFF=0,
        bin_duration_accel=1.0,
        bin_duration_accel_window=7.0,
        bin_real_wake_acc=3.5
    ),



]

# The first detector in the list is used as the reference for TTL output and stimulation.
# Change this to point to a different detector if needed.
self.ref_det = self.detectors[0]
