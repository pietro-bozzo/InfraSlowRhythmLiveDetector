# =============================================================================
# config_ISR.py — Configuration du Python Processor ISR (Open-Ephys)
# Modifier ce fichier entre les sessions/rats. Ne pas toucher le .py principal.
# =============================================================================

# --- TTL events from Python processor ---
self.ttl_ON           = 7   # TTL line used for avalanche state
self.ttl_IS           = 4   # TTL line used for InfraSlow state
self.ttl_wake_REM     = 1   # TTL line used for Wake/REM state
self.ttl_thresholding = 3   # TTL line used for indicating threshold calculation started

# --- User interaction via TTL toggle panel (panel index = value + 1) ---
self.ligne_threshold_integration = 9   # TTL to trigger threshold calculation
self.ligne_stop_IS_now           = 14  # TTL to stop IS detection immediately
self.ligne_print                 = 19  # TTL to print debug information in the console 

# --- Detection parameters ---
self.time_limit_integration  = 20.0  # seconds to calculate thresholds
self.percentage              = 40    # percentile for mean firing rate threshold
self.percentage_accel        = 70    # percentile for acceleration threshold
self.max_time_ON             = 14    # maximum duration of avalanche (seconds)
self.time_value_moy          = 8     # time window for moving mean (seconds)
self.time_value_acceleration = 8     # time window for moving acceleration (seconds)
self.multiplior_tresh        = 3     # multiplier for threshold comparison of spike rate
self.multiplior_tresh_accel  = 1     # multiplier for threshold comparison of acceleration
self.max_time_OFF            = 16    # maximum duration of an OFF period (seconds)
self.min_time_OFF            = 0.5   # minimum duration of OFF to count (seconds)
self.min_time_ON             = 0.3   # minimum duration of ON to count (seconds)

# --- Channel indices (position in channel map, not electrode number) ---
self.mean_spike_rate_channel     = 32   # channel for mean firing rate
self.accel_channel_1             = 128  # accelerometer axis 1
self.accel_channel_2             = 129  # accelerometer axis 2
self.accel_channel_3             = 130  # accelerometer axis 3
self.n_channels                  = 142  # total number of channels in the stream

self.channels_val_debut = [25, 13, 32, 33, 34, 35, 126, 127, 128, 129, 130, 131, 132, 133] 
# channels for wich we print 20 first values when session is launched, to check if the channels are correct 

self.list_channels_debug_printed = [25, 13, 32, 33, 34, 35, 126, 127, 128, 129, 130, 131, 132, 133]                
# channels for which debug information will be printed in the debug file when clicking the debug TTL button ligne_print above all channels also printed in the console

# --- Saving ---
self.saving     = True
self.path       = "/home/guillaume/Documents/Tests_finaux_ISR/"
self.file_name  = "IS_wake_timings_debug.txt"
self.debug_name = "debugFile.txt"