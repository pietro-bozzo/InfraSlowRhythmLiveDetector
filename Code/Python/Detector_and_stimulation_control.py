# =============================================================================
# Python Processor for Open-Ephys Plugin
# =============================================================================
# Goal of this code:
#   - To be used as a Python Processor within the Open-Ephys signal processing chain.
#   - Detection and tracking of Infraslow Avalanches (IS) based on spike rate and 
#     accelerometer data.
#   - Tracks ON (avalanche) and OFF (inter-avalanche) periods, calculates thresholds,
#     and generates TTL events for:
#       * Avalanche state (ON)
#       * InfraSlow Rhythm state (IS)
#       * Wake/REM state (wake_REM)
#   - Allows user interaction via TTL toggle panel to:
#       * Recalculate thresholds
#       * Stop IS detection immediately
#   - Saves IS and Wake/REM intervals at the end of acquisition to a text file.
# =============================================================================

## Imports:
import numpy as np
import math
import oe_pyprocessor
from collections import deque  # useful for moving average calculation
import os
import fileinput

import time
import json
from datetime import datetime


# =============================================================================
# The main Python Processor class that will be instantiated by Open-Ephys
# =============================================================================
class PyProcessor:
    ### PARAMETERS OF INITIALIZATION ###
    def __init__(self, processor, num_channels, sample_rate):
        """ 
        A new processor is initialized whenever the plugin settings are updated

        Parameters:
        processor (object): Python Processor class object used for adding events from Python.
        num_channels (int): number of input channels in the selected stream.
        sample_rate (float): sample rate of the selected stream
        """
        print("Num Channels: ", num_channels, " | Sample Rate: ", sample_rate)
        # Retrieve information provided by Open-Ephys
        self.processor = processor
        self.num_channels = num_channels
        self.sample_rate = sample_rate

        # General and Step 1: threshold calculation
        self.time_counter = 0.0  # running counter for buffer time
        self.threshold_time_counter = 0.0  # timer for threshold integration
        self.buffer_points = []  # buffer for mean firing rate values
        self.accel_points = []   # buffer for acceleration values
        self.threshold_value = None   
        self.threshold_acceleration = None
        self.mean_acceleration_decay = None  # baseline acceleration

        # Moving average buffers
        self.mean_buffers = deque()          # stores tuples of (time, value) for spike rate
        self.mean_buffer_time = 0

        # Moving acceleration buffers
        self.acceleration_buffers = deque()  # stores tuples of (time, value) for acceleration
        self.acceleration_buffer_time = 0

        # Boolean states
        self.threshold_calculated = True     # True if thresholds have been calculated
        self.ON_state = False                # True/False avalanche state (False initially)
        self.IS_state = False                # True/False InfraSlow rhythm (False initially)
        self.wake_REM_state = False          # True/False Wake/REM (False initially)

        # TTL events from Python processor
        self.ttl_ON = 7              # TTL line used for avalanche state
        self.ttl_IS = 4              # TTL line used for InfraSlow state
        self.ttl_wake_REM = 1        # TTL line used for Wake/REM state
        self.ttl_thresholding = 3    # TTL line used for indicating that the user has chosen to thershold from there

        # User interaction via TTL toggle panel
        # Note: TTL panel index = value + 1
        self.ligne_threshold_integration = 9   # TTL to trigger threshold calculation
        self.ligne_stop_IS_now = 14            # TTL to stop IS detection immediately
        self.user_redo_tresh = False           # state associated with threshold integration TTL
        self.user_counter_decision = 0         # counts user-triggered threshold decisions
        self.user_stop_IS_now = False          # state associated with stop IS TTL

        self.ligne_print = 19
        self.event_print = 0
        self.debuglist = []  # list to store debug messages for printing at the end of acquisition
        self.global_t0 = -1  # global time reference for recording sessions

        # Avalanche (ON) and inter-avalanche (OFF) timing
        self.start_time_ON = -1
        self.end_time_ON = 0
        self.start_time_OFF = -1        
        self.end_time_OFF = 0
        self.duration_OFF = -1  # must be -1 initially to calculate the first OFF period correctly

        # Lists recording OFF and ON times
        self.L_time_OFFs = []  # durations of OFF periods
        self.L_time_ONs = []   # durations of ON periods
        # Lists recording IS and wake/REM timings (start, end, start, ...)
        self.L_time_IS = []
        self.L_time_wake_REM = []      

        # ADJUSTABLE PARAMETERS
        self.time_limit_integration = 20.0  # seconds to calculate thresholds
        self.percentage = 40                 # percentile for mean firing rate threshold
        self.percentage_accel = 70           # percentile for acceleration threshold
        self.max_time_ON = 14                # maximum duration of avalanche (seconds)
        self.time_value_moy = 8              # time window for moving mean (seconds)
        self.time_value_acceleration = 8     # time window for moving acceleration (seconds)
        self.multiplior_tresh = 3            # multiplier for threshold comparison of spike rate
        self.multiplior_tresh_accel = 1      # multiplier for threshold comparison of acceleration
        self.max_time_OFF = 16                # maximum duration of an OFF period
        self.min_time_OFF = 0.5               # minimum duration of OFF to count (seconds)
        self.min_time_ON = 0.3                # minimum duration of ON to count (seconds)
        self.saving = True                    # whether to save IS and Wake timings to .txt
        self.path = "/media/data-103/Guillaume/InfraSlowRhythmLiveDetector/Output_oe/"  # save path
        self.file_name = "IS_wake_timings_Perceval_1.txt"  # name of the file you will create with the timings
        self.debug_name = "debug.txt"
        self.debug_path = os.path.abspath(self.path + self.debug_name)
        # in .py it begins at 0 and in O-E it begins at 1 /!\ :
        self.mean_spike_rate_channel = 32     # channel index (position of the channels in the channel map, not the number) for mean firing rate
        self.accel_channel_1 = 33             # channel index for accelerometer component 1
        self.accel_channel_2 = 34             # channel index for accelerometer component 2
        self.accel_channel_3 = 35             # channel index for accelerometer component 3

        # ---- STIMULATION PROTOCOL ----
# Liste de stimulations : (id, frequence_Hz, duree_s)
# id correspond à la ligne TTL du panneau (0-indexed en Python, donc ligne id+1 dans OE)
        self.stim_list_raw = [
    (0,  1.0, 0.5),
    (1,  2.0, 0.5),
    (2,  4.0, 0.5),
    (3,  8.0, 0.5),
    (4, 10.0, 0.5),
    (5, 20.0, 0.5),
    (6, 40.0, 0.5),
    (7, 80.0, 0.5),
    (8,  0.5, 1.0),
    (9,  0.1, 2.0),
        ]
# Mélange aléatoire de l'ordre des stimulations
        import random
        self.stim_order = list(range(len(self.stim_list_raw)))
        random.shuffle(self.stim_order)
        print("Stim order:", self.stim_order)

        self.stim_current_index = 0      # index dans stim_order (quel type de stim on est)
        self.stim_count = 0              # nb de stim envoyées pour le type courant
        self.stim_max_per_type = 100     # nb de stim avant de passer au type suivant
        self.stim_interval = 60.0        # intervalle entre deux stim (secondes)
        self.stim_timer = 0.0            # timer depuis la dernière stim
        self.stim_timer_active = False   # True si le timer tourne (IS_state et pas wake)
        self.stim_done = False           # True si toutes les stim ont été envoyées
        self.ttl_stim = 5                # ligne TTL pour signaler une stimulation

        pass
    
    # communication with the user : 

    def handle_ttl_event(self, source_node, channel, sample_number, line, state):
        """
        Handle incoming TTL events from the Open-Ephys system.

        Parameters:
            source_node (int): ID of the processor that generated this event.
            channel (str): Name of the event channel.
            sample_number (int): Sample number when the event occurred.
            line (int): The TTL line on which the event was generated (0-255).
            state (bool): State of the event: True (ON) or False (OFF).

        Functionality:
            - Monitors specific TTL lines that are used for user interactions.
            - Handles requests to recalculate thresholds or stop InfraSlow (IS) detection immediately.
            - Updates internal flags and triggers Python TTL events back to Open-Ephys.
        """

        # -------------------------------
        # TTL control panel logic
        # -------------------------------

        # If user presses the TTL line to trigger threshold integration
        if (line == self.ligne_threshold_integration and state == True) and not self.user_redo_tresh:
            self.user_redo_tresh = True          # mark that threshold recalculation is requested
            self.user_counter_decision += 1      # increment user decision counter
            self.processor.add_python_event(self.ttl_thresholding, True)  # send TTL event to indicate threshold calculation started

        # If user releases the threshold integration TTL line
        if (line == self.ligne_threshold_integration and state == False):
            self.processor.add_python_event(self.ttl_thresholding, False)  # send TTL event to indicate threshold calculation stopped

        # If user presses the TTL line to immediately stop InfraSlow detection
        if line == self.ligne_stop_IS_now and state == True:
            self.user_stop_IS_now = True
            # optional: could also trigger a TTL event here if desired
            # self.processor.add_python_event(3, True)

        # If user releases the stop IS TTL line
        if line == self.ligne_stop_IS_now and state == False:
            self.user_stop_IS_now = False

        if line == self.ligne_print and state == True and self.event_print == 0 :
           # print(f"[OE DEBUG] time_counter = {self.time_counter:.3f} s")
            self.event_print += 1

        if line == self.ligne_print and state == False:
            self.event_print = 0

        return


    # We have our initialization then the loop : 
    def process(self, data):
        """
        Process each incoming data buffer.

        Parameters:
        data - N x M numpy array, where N = num_channels, M = num of samples in the buffer.
        """

        # ---- STEP 0: Retrieve data + update time counters + instantaneous and sliding means + instantaneous and sliding acceleration ----

        # Retrieve mean spike rate channel
        mean_spike = data[self.mean_spike_rate_channel, :]  # currently set to the 33rd channel (modifiable)
        
        # Retrieve accelerometer channels, placed just after mean firing rate (note: risk of change depending on XML)
        accel1 = np.mean(data[self.accel_channel_1, :])
        accel2 = np.mean(data[self.accel_channel_2, :])
        accel3 = np.mean(data[self.accel_channel_3, :])

        # Calculate buffer duration
        buffer_duration = mean_spike.shape[0] / self.sample_rate  # duration of this buffer
        self.time_counter += buffer_duration  # increment global time counter
        self.threshold_time_counter += buffer_duration  # increment threshold calculation timer

        ## Update sliding mean:
        # Compute current buffer mean (min could be used but is less robust)
        current_mean = np.mean(mean_spike)
        # Append current buffer to sliding window
        self.mean_buffers.append((buffer_duration, current_mean))
        self.mean_buffer_time += buffer_duration
        # Remove outdated values to maintain max sliding window duration
        while self.mean_buffer_time > self.time_value_moy:
            dt, val = self.mean_buffers.popleft()
            self.mean_buffer_time -= dt
        # Compute sliding mean
        moy_glissante = np.mean([v for _, v in self.mean_buffers])

        ## Update sliding acceleration mean:
        # Instantaneous acceleration norm
        norm_acceleration = ((accel1**2 + accel2**2 + accel3**2)**0.5) * 10000  # scaled for readability
        # Append current acceleration to sliding window
        self.acceleration_buffers.append((buffer_duration, norm_acceleration))
        self.acceleration_buffer_time += buffer_duration
        # Remove outdated values to maintain max sliding window duration
        while self.acceleration_buffer_time > self.time_value_acceleration:
            dt, val = self.acceleration_buffers.popleft()
            self.acceleration_buffer_time -= dt
        # Compute sliding acceleration
        acceleration_glissante = np.mean([v for _, v in self.acceleration_buffers])

        # ---- STEP 1: USER CONTROL ----

        if self.event_print == 1:
            self.event_print = 2
            mess = f"[OE DEBUG] time_counter = {self.time_counter:.3f} s"
            self.debuglist.append(mess)

        # WARNING: If the user clicks to start threshold calculation, they have 20 sec to unclick or it restarts
        # Until the user requests, the Python processor does not engage threshold calculation
        if self.user_counter_decision < 1:
            return
        

        # WARNING: If the user requests threshold calculation (self.user_redo_tresh) and it was already calculated or first iteration (self.threshold_calculated)
        if self.user_redo_tresh and self.user_counter_decision > 0 and self.threshold_calculated:
            # Reinitialize parameters to redo integration
            self.threshold_calculated = False
            self.threshold_time_counter = 0.0
            self.buffer_points = []
            self.accel_points = []
            # Reinitialize other detection parameters (STEP 4)
            self.ON_state = False
            self.IS_state = False
            self.wake_REM_state = False
            self.start_time_ON = -1
            self.end_time_ON = 0
            self.start_time_OFF = -1
            self.end_time_OFF = 0
            self.L_time_OFFs = []

            # Trigger Python TTL events to reset states
            self.processor.add_python_event(self.ttl_ON, self.ON_state)
            self.processor.add_python_event(self.ttl_IS, self.IS_state)
            self.processor.add_python_event(self.ttl_wake_REM, self.wake_REM_state)

        # If user requests to stop InfraSlow (IS):
        if self.user_stop_IS_now:
            # Reset detection parameters
            self.ON_state = False
            self.IS_state = False
            self.wake_REM_state = False
            self.start_time_ON = -1
            self.end_time_ON = 0
            self.start_time_OFF = -1
            self.end_time_OFF = 0
            self.L_time_OFFs = []

            # Trigger TTL events to reset states
            self.processor.add_python_event(self.ttl_ON, self.ON_state)
            self.processor.add_python_event(self.ttl_IS, self.IS_state)
            self.processor.add_python_event(self.ttl_wake_REM, self.wake_REM_state)

        # ---- STEP 2: THRESHOLD CALCULATION ----

        if not self.threshold_calculated:
            # Accumulate mean firing rate buffer values
            self.buffer_points.append(mean_spike)
            # Accumulate acceleration values
            self.accel_points.append(norm_acceleration)

            # If integration period finished (x seconds)
            if self.threshold_time_counter >= self.time_limit_integration:
                self.threshold_calculated = True  # thresholds are now calculated

                # METHOD: Take the x-th percentile
                all_values = np.concatenate(self.buffer_points)  # concatenate list of arrays
                self.threshold_value = np.percentile(all_values, self.percentage)  # compute threshold percentile

                # Threshold for acceleration (no need to concatenate, already correct form)
                self.threshold_acceleration = np.percentile(self.accel_points, self.percentage_accel)
                # Get resting mean of acceleration (baseline)
                self.mean_acceleration_decay = np.mean(self.accel_points)

                # Reset user redo button
                self.user_redo_tresh = False

            return  # Do not proceed to detection yet

        # ---- STEP 3: AVALANCHE AND INFRASLOW DETECTION ----

        ## WAKE or REM detection, may reset detection
        if self.threshold_acceleration is None:
            return
        condition_wake = np.abs(acceleration_glissante - self.mean_acceleration_decay) > \
                        np.abs(self.threshold_acceleration * self.multiplior_tresh_accel - self.mean_acceleration_decay)
        if self.threshold_value is None:
            return
        # REM/Wake detection based on mean (observe large spikes for REM)
        condition_rem_wake = moy_glissante > self.multiplior_tresh * self.threshold_value

        if condition_wake or condition_rem_wake:
            # Trigger TTL event
            self.processor.add_python_event(self.ttl_wake_REM, True)
            # Reset IS and avalanche states
            self.L_time_OFFs = []
            self.start_time_ON = -1
            self.start_time_OFF = -1
            self.ON_state = False
            # Record IS and wake/REM timings
            if self.IS_state:
                self.L_time_IS.append(self.time_counter)
            if not self.wake_REM_state:
                self.L_time_wake_REM.append(self.time_counter)
            # Change IS state to False
            self.IS_state = False
            self.wake_REM_state = True
            self.processor.add_python_event(self.ttl_IS, False)
            return
        else:
            # If no unusual movement/activity detected:
            # Record end of wake/REM
            if self.wake_REM_state:
                self.L_time_wake_REM.append(self.time_counter)
            # Indicate we are neither in REM nor Wake
            self.wake_REM_state = False
            self.processor.add_python_event(self.ttl_wake_REM, False)

            # Proceed with avalanche analysis

            ## STOP condition for excessively long OFF periods
            cond_max_OFF = (self.time_counter - self.start_time_OFF < self.max_time_OFF)
            if self.IS_state and self.start_time_OFF >= 0 and not cond_max_OFF:
                # Reset everything
                self.IS_state = False
                self.L_time_IS.append(self.time_counter)
                self.L_time_OFFs = []
                self.L_time_ONs = []
                self.start_time_OFF = -1
                self.start_time_ON = -1
                self.processor.add_python_event(self.ttl_IS, False)

            if self.duration_OFF < 0:
                # Directly compute beginning of OFF
                self.start_time_OFF = self.time_counter
                self.duration_OFF = 0

            # Avalanche decision
            ON_now = (current_mean - self.threshold_value) > 0

            ## Transition OFF -> ON (avalanche occurs)
            if ON_now and not self.ON_state:
                self.ON_state = True
                # Record avalanche start time
                self.start_time_ON = self.time_counter
                # Record last OFF interval (space between avalanches)
                if self.start_time_OFF >= 0:
                    self.end_time_OFF = self.time_counter
                    time_OFF = self.end_time_OFF - self.start_time_OFF
                    self.duration_OFF = time_OFF
                    # Do not reset start_time_OFF or record OFF yet (handled in ON->OFF transition)

                # Trigger avalanche event
                self.processor.add_python_event(self.ttl_ON, True)

            ## Transition ON -> OFF (end of avalanche)
            elif not ON_now and self.ON_state:
                self.ON_state = False
                if self.start_time_ON >= 0:
                    self.end_time_ON = self.time_counter
                    time_ON = self.end_time_ON - self.start_time_ON
                    self.start_time_ON = -1

                    # Case 1: ON too long, stop IS
                    if time_ON > self.max_time_ON:
                        if self.IS_state:
                            self.L_time_IS.append(self.time_counter)
                        self.L_time_OFFs = []
                        self.L_time_ONs = []
                        self.start_time_OFF = -1
                        self.IS_state = False
                        self.processor.add_python_event(self.ttl_IS, False)

                    # Case 3: ON sufficiently long but not too long
                    elif self.min_time_ON <= time_ON <= self.max_time_ON:
                        self.L_time_OFFs.append(self.duration_OFF)
                        self.duration_OFF = 0
                        self.start_time_OFF = self.time_counter
                        self.L_time_ONs.append(time_ON)

                    # Case 2: ON too short, ignore and continue the OFF time

                # Trigger end-of-avalanche event
                self.processor.add_python_event(self.ttl_ON, False)

            ## InfraSlow Rhythm (IS) detection
            if len(self.L_time_OFFs) >= 2 and not self.wake_REM_state:
                # Condition 1: no OFF interval too long
                cond_max = all(t < self.max_time_OFF for t in self.L_time_OFFs)
                # Condition 2: at least 2 OFF intervals sufficiently long
                long_OFFs = [t for t in self.L_time_OFFs if t > self.min_time_OFF]
                cond_min_OFFs = len(long_OFFs) >= 2

                if cond_max and cond_min_OFFs:
                    # Record IS start
                    if not self.IS_state:
                        self.L_time_IS.append(self.time_counter)
                        with open(self.debug_path, "a") as f:
                            print("IS detection : ", self.time_counter, file=f)
                    self.IS_state = True
                    self.processor.add_python_event(self.ttl_IS, True)
            
        # ---- STEP 4: STIMULATION PROTOCOL ----
        if not self.stim_done:
    # Le timer avance uniquement si IS_state=True et pas de wake
            if self.IS_state and not self.wake_REM_state:
        # Pause si l'accéléromètre dépasse le seuil
                accel_ok = not condition_wake  # réutilise la condition wake déjà calculée
                if accel_ok:
                    self.stim_timer += buffer_duration

            # Vérifier si c'est le moment d'envoyer une stim
                    if self.stim_timer >= self.stim_interval:
                        self.stim_timer = 0.0  # reset timer

                # Récupérer le type de stim courant
                        stim_idx = self.stim_order[self.stim_current_index]
                        tim_id, stim_freq, stim_dur = self.stim_list_raw[stim_idx]

                # Envoyer l'événement TTL de stimulation
                        self.processor.add_python_event(self.ttl_stim, True)
                        self.processor.add_python_event(self.ttl_stim, False)

                # Envoyer aussi sur la ligne correspondant à l'id de la stim
                # pour identifier le type dans OE
                        self.processor.add_python_event(stim_id, True)
                        self.processor.add_python_event(stim_id, False)

                # Log
                        msg = (f"STIM sent: type={stim_idx} id={stim_id} "
                       f"freq={stim_freq}Hz dur={stim_dur}s "
                       f"count={self.stim_count+1}/{self.stim_max_per_type} "
                       f"t={self.time_counter:.2f}s")
                        self.debuglist.append(msg)
                        with open(self.debug_path, "a") as f:
                            print(msg, file=f)

                        self.stim_count += 1

                # Passer au type suivant après stim_max_per_type stim
                        if self.stim_count >= self.stim_max_per_type:
                            self.stim_count = 0
                            self.stim_current_index += 1
                            self.stim_timer = 0.0  # reset timer au changement de type

                            if self.stim_current_index >= len(self.stim_order):
                                self.stim_done = True
                                msg = f"ALL STIM DONE at t={self.time_counter:.2f}s"
                                self.debuglist.append(msg)
                                with open(self.debug_path, "a") as f:
                                    print(msg, file=f)
                            else:
                                next_idx = self.stim_order[self.stim_current_index]
                                msg = (f"Switching to stim type {next_idx} "
                                       f"at t={self.time_counter:.2f}s")
                                self.debuglist.append(msg)
                                with open(self.debug_path, "a") as f:
                                    print(msg, file=f)
            else:
        # IS_state=False ou wake : on ne reset pas le timer,
        # on le met juste en pause en ne l'incrémentant pas
                pass

        return
    
    def start_acquisition(self):
        print("Début acquisition")

    def stop_acquisition(self):
        print("Fin acquisition")

    def start_recording(self, recording_dir):
        now = self.time_counter  # current time in seconds since acquisition start
        if self.global_t0 == -1:
            self.global_t0 = now  # Premier enregistrement = t0 session complète
        



    # At the end of acquisition: record IS and wake/REM intervals
    def stop_acquisition(self):
        if self.saving:  # If saving is enabled, write to path
            namedossier = os.path.abspath(self.path + self.file_name)
           # if not os.path.exists(namedossier):
           #     open(namedossier, "w").close()
            with open(namedossier, "a") as f:
                line_count = sum(1 for line in fileinput.input(namedossier))
                # Number the stop acquisitions
                print("STOP ACQUISITION NUMBER", int(line_count / 5) + 1, file=f)
                print("List of IS timing markers (starts with 'start'):", file=f)
                print(self.L_time_IS, file=f)
                print("List of wake/REM timing markers (starts with 'start'):", file=f)
                print(self.L_time_wake_REM, file=f)
                print("debug_ list:", file=f)
                print(self.debuglist, file=f)
                print("Temps début recording global t0 (s):", self.global_t0, file=f)
                print("Stim order (shuffled):", [self.stim_list_raw[i] for i in self.stim_order], file=f)
                print("Stim current index:", self.stim_current_index, file=f)
                print("Stim count on current type:", self.stim_count, file=f)
                print("Stim done:", self.stim_done, file=f)
        return
    