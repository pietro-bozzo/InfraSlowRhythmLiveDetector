% =========================================================================
% PIPELINE — Comparison Between Open Ephys Detection and MATLAB Detection
%
% Objective:
% 1) Load timestamps detected online by Open Ephys during a ~2-hour session
% 2) Visually compare them with intervals detected offline in MATLAB
%    (Pietro's algorithms)
% 3) Quantitatively evaluate detection performance (precision, recall, F-score)

% DEPENDENCIES
% formatage_list.mat

% By Nathan Mimouni, 2026
% =========================================================================


%% LOAD SESSION FOR COMPARISON

% Load the same recording session used for MATLAB-based detection
% (same logic as sessions_analyse_UsAvals_Nath.m)

%session = '/mnt/hubel-data-140/karadoc/Rat004_20240305/Rat004_20240305.xml'; % Change recording day here
session = '/mnt/hubel-data-131/perceval/Rat003_20231212/Rat003_20231212.xml'; % Change recording day here

[filebase,basename] = fileparts(session);

filename = '/mnt/hubel-data-103/Guillaume/OpenEphys_Stimulation_Tests/Output_oe/RESTRUCTURED/accel_ttl_times2.txt';
txt = fileread(filename);

window_size_sec   = 4;     % taille de la fenetre glissante (s)
window_step_sec   = 0.023;  % pas de glissement (s) -> resolution temporelle du smoothing
accel_thresh_sec  = 1.5;   % seuil de cumul d'accel dans la fenetre pour la marquer "active"


R = regions(session, ...
    regions='nr', ...
    events=["InfraSlowRhythm/slownr","InfraSlowRhythm/slowavalnr"], ...
    states=["sws","rem"]);
%% If there is a problem with regions for some sessions : get rid of phases = 'sleepm'

% Load MATLAB-detected intervals (ground truth reference)
sws_intervals = R.eventIntervals('sws');      % InfraSlow Rhythm (MATLAB detection)
wake_intervals     = R.eventIntervals('other');  % Avalanches
rem_intervals = R.eventIntervals('rem');

% Load MATLAB-detected intervals (ground truth reference)
us_intervals = R.eventIntervals('slownr');      % InfraSlow Rhythm (MATLAB detection)
us_avals     = R.eventIntervals('slowavalnr');  % Avalanches


%% DETERMINE VALID TIME RANGE OF OPEN EPHYS RECORDING

% At the end of acquisition, Open Ephys exports a document containing
% sequences of start/end timestamps corresponding to detected intervals
% (InfraSlow, wake/sleep). cf Setup Code
%
% However, if acquisition was not manually stopped at the correct time,
% the detector may continue running and produce artificial intervals.
% Therefore, we must determine until which time the Open Ephys detections
% are valid and discard timestamps beyond that limit.
%
% This section:
% - Computes the valid recording end time (time_end_reccord_oe)
% - Computes the temporal offset between:
%     • cumulative session time (MATLAB)
%     • Open Ephys acquisition time (which starts at 0)
%
% This alignment is necessary to compare intervals between systems.

L_start_stop = eventIntervals(R);
start = L_start_stop(1); % Session start time (s)
%stop  = L_start_stop(2); % Session stop time (s)
stop =8000;

start_reccord_sec = 1970; %1580; % Chosen cumulative session time (s) % Je crois avoir compris : sion regarde sleep1, c'est quand sleep 1 commence dans la session totale. Pas automatisable, ou alors en récupérant les temps deb fin de chaque recording node...
decay_from_open_ephys = start_reccord_sec - start;   %26*60 + 40; % seconds

% Align Open Ephys time with cumulative MATLAB session time
start_sec_decay = decay_from_open_ephys + start; % (s)

% Maximum valid time in Open Ephys detection list
time_end_reccord_oe = stop - start_sec_decay; % (s)


%% LOAD OPEN EPHYS DETECTION RESULTS


%% --- 1. Lecture du fichier texte ---
txt = strrep(txt, '[', '');
txt = strrep(txt, ']', '');
liste = str2double(strsplit(txt, ','));
Liste_timings_wake_accel = liste(~isnan(liste));

Liste_timings_wake_accel = Liste_timings_wake_accel(Liste_timings_wake_accel<time_end_reccord_oe);
 
%% --- 2. Formatage en intervalles bruts (fonction existante) ---
wakeREM_accel_OE_intervals = formatage_list(Liste_timings_wake_accel, start_sec_decay);
% Attendu : [N x 2] = [t_start, t_end]
 
%% --- 3. Fenetre glissante : cumul d'accel par fenetre ---
t_min = min(wakeREM_accel_OE_intervals(:,1));
t_max = max(wakeREM_accel_OE_intervals(:,2));

window_starts = t_min:window_step_sec:(t_max - window_size_sec);
n_windows = numel(window_starts);
accel_duration_per_window = zeros(n_windows,1);

for i = 1:n_windows
    w_start = window_starts(i);
    w_end   = w_start + window_size_sec;
    dur = 0;
    for k = 1:size(wakeREM_accel_OE_intervals,1)
        ov_start = max(wakeREM_accel_OE_intervals(k,1), w_start);
        ov_end   = min(wakeREM_accel_OE_intervals(k,2), w_end);
        if ov_end > ov_start
            dur = dur + ov_end - ov_start;
        end
    end
    accel_duration_per_window(i) = dur;
end


is_active = accel_duration_per_window > accel_thresh_sec;
 
%% --- 4. Fusion des fenetres actives contigues -> intervalles smoothes ---
merged = [];
n = numel(window_starts);
i = 1;
while i <= n
    if is_active(i)
        seg_start = window_starts(i);
        while i <= n && is_active(i)
            i = i + 1;
        end
        seg_end = window_starts(i-1) + window_size_sec;
        merged = [merged; seg_start, seg_end]; %#ok<AGROW>
    else
        i = i + 1;
    end
end
smoothed_intervals = merged;
 

%% --- 5. Plot ---
figure; hold on;

PlotIntervals(sws_intervals,'color',[0 0 1],'legend','SWS', 'alpha', 0.2);
PlotIntervals(wake_intervals,'color',[1 0 0],'legend','WAKE', 'alpha', 0.2);
PlotIntervals(rem_intervals,'color',[1 0 0],'legend','rEM', 'alpha', 0.2);

% MATLAB detection (reference)
PlotIntervals(us_intervals,'legend','Pietro detection','Color',[0,1,0],'alpha',0.6)

 
y_raw    = 0.3;
y_smooth = 0.7;

for k = 1:size(wakeREM_accel_OE_intervals,1)
    plot([wakeREM_accel_OE_intervals(k,1) wakeREM_accel_OE_intervals(k,2)], [y_raw y_raw], ...
        'Color', 'b', 'LineWidth', 14);
end
for k = 1:size(smoothed_intervals,1)
    plot([smoothed_intervals(k,1) smoothed_intervals(k,2)], [y_smooth y_smooth], ...
        'Color', 'r', 'LineWidth', 14);
end

%ylim([0 3]);
yticks([y_raw y_smooth]);
yticklabels({'Bruts', sprintf('Smoothes (win=%gs, seuil=%gs)', window_size_sec, accel_thresh_sec)});
xlabel('Temps (s)');
title('Intervalles d''acceleration detectee : bruts vs smoothes');
grid on;
hold off;