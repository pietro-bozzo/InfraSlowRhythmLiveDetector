% =========================================================================
% ANALYSIS PIPELINE — Ultra-Slow Avalanches in Nucleus Reuniens
%
% This script allows:
% 1) Loading a recording day and selecting a specific session (phase)
% 2) Visualizing population firing rate together with:
%       - UltraSlow Rhythm periods
%       - Avalanches
%       - Brain states (SWS / REM)
% 3) Determining the correct start time to use in Open Ephys (File Reader)
% 4) Verifying absence of movement using accelerometer signals
%
% REQUIREMENTS:
% - FMAToolbox
% - Regions toolbox
%
% IMPORTANT CONCEPTS:
% - One recording day (e.g., 20240228) may contain multiple sessions
%   (e.g., 20240228_08-53-14).
% - In MATLAB: load the entire day (.xml) and select the session via "phases".
% - In Open Ephys: directly select the specific session folder (Raw data).
%
% Typical session phases:
%   1) sleepm
%   2) tachem
%   3) sleepn  (may not be detected if the animal did not sleep)
%   4) tachea
%   5) sleeps

% By Nathan Mimouni, 2026
% =========================================================================


%% LOAD SESSION AND SELECT PHASE

session = '/mnt/hubel-data-139/karadoc/Rat004_20240228/Rat004_20240228.xml'; % Change recording day here
% session = '/mnt/hubel-data-131/perceval/Rat003_20231215/Rat003_20231215.xml';

[filebase,basename] = fileparts(session);

% Load Nucleus Reuniens region during selected phase
R = regions(session, ...
    regions='nr', ...
    phases='sleepm', ...
    events=["InfraSlowRhythm/slownr","InfraSlowRhythm/slowavalnr"], ...
    states=["sws","rem"]);

% "states" overlays SWS and REM as colored background on plots
%  Phases : 
%   1) sleepm
%   2) tachem
%   3) sleepn  (may not be detected if the animal did not sleep)
%   4) tachea
%   5) sleeps

% LOAD EVENT INTERVALS (ULTRASLOW & AVALANCHES)

% UltraSlow Rhythm periods
is_intervals = R.eventIntervals('slownr');

% Avalanches
is_avals = R.eventIntervals('slowavalnr');

% Display cumulative session time boundaries
eventIntervals(R)


%% VISUALIZE SESSION: FIRING RATE + EVENTS + STATES

% Extract session time limits
L_start_stop = eventIntervals(R);
start = L_start_stop(1); % session start time (s)
stop  = L_start_stop(2); % session end time (s)

% Convert to hh:mm:ss format (reference for Open Ephys)
t = seconds(start - L_start_stop(1));
t.Format = 'hh:mm:ss';

% Plot population mean firing rate
R.plotFiringRates(start, stop, step=5, smooth=45);

% Overlay UltraSlow periods (green)
PlotIntervals(is_intervals,'legend','US','Color',[0,1,0]);

% Overlay avalanches (red)
PlotIntervals(is_avals,'color',[0.8,0.2,0.2],'legend','avalanches');

% Display figure on right screen
plotOnScreen('right');


%% DETERMINE START TIME FOR OPEN-EPHYS FILE READER

% Strategy:
% - Identify the beginning of a sufficiently long UltraSlow (green) period
% - Put its cumulative time (in seconds, read on the plot made juste before) as start_reccord_sec
% - Convert this into hh:mm:ss relative to session start
% - Enter this value into the Open Ephys File Reader "start" field

L_start_stop = eventIntervals(R);

start_reccord_sec = 1580; % Chosen cumulative session time (s)

t = seconds(start_reccord_sec - L_start_stop(1));
t.Format = 'hh:mm:ss' % Time to use in Open Ephys (see the terminal for the result)


%% VERIFY MOVEMENT USING ACCELEROMETER

% Purpose:
% Ensure that the selected analysis window does not correspond
% to a movement period (which would bias neural activity measures).
%
% Accelerometer channels are not easily visualized in Open Ephys,
% so this step is required to monitor motion offline.

SetCurrentSession(session)

start_acc = 25000; % Start time (s)
stop_acc  = 26500; % Stop time (s)

% Load 3 accelerometer components /!\ the channels won't be the same than
% 128, ... you have to check that (on neuroscope)
a1 = GetWidebandData(128,'intervals',[start_acc stop_acc]); % X
a2 = GetWidebandData(129,'intervals',[start_acc stop_acc]); % Y
a3 = GetWidebandData(130,'intervals',[start_acc stop_acc]); % Z

% Time vector
t = a1(:,1);

% Compute Euclidean norm of acceleration
acceleration = zeros(numel(a3(:,1)),2);
acceleration(:,1) = t;
acceleration(:,2) = sqrt(a1(:,2).^2 + a2(:,2).^2 + a3(:,2).^2);

% Plot acceleration norm
figure
plot(t,acceleration(:,2))
title('Acceleration norm')
xlabel('time (s)')
ylabel('µm/s²')

