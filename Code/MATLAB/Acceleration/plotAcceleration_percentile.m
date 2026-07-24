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

%session = '/mnt/hubel-data-131/perceval/Rat003_20231212/Rat003_20231212.xml'; % Change recording day here
%session = '/mnt/hubel-data-149/Rat012/Rat012_2025-12-16/Rat012_2025-12-16.xml';
session = "/mnt/hubel-data-149/Lumos_Rat013/2026-05-29_11-40-47/2026-05-29_11-40-47/Record Node 131/experiment1/recording1/continuous/Rat013_29052026/Rat013_29052026.xml" ;
[filebase,basename] = fileparts(session);

filename = '/mnt/hubel-data-103/Guillaume/InfraSlowRhythmLiveDetector/Output_oe/Tests_sessions_finaux/LUMOS/LUMOS_OE/IS_wake_timings_Lumos.txt';
txt = fileread(filename);

% R = regions(session, ...
%     regions='nr', ...
%     phases='sleepm', ...
%     events=["InfraSlowRhythm/slownr","InfraSlowRhythm/slowavalnr"], ...
%     states=["sws","rem"]);

R = regions(session, ...
    regions='nr');

% Load MATLAB-detected intervals (ground truth reference)
us_intervals = R.eventIntervals('slownr');      % InfraSlow Rhythm (MATLAB detection)
us_avals     = R.eventIntervals('slowavalnr');  % Avalanches

channels = [128 129 130];

interval = [0 1000];

start_acc = interval(1);
stop_acc  = interval(2);


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
start = 0; %L_start_stop(1); % Session start time (s)
stop  = 1000; %L_start_stop(2); % Session stop time (s)

start_reccord_sec = start_acc; %1580; % Chosen cumulative session time (s) % Je crois avoir compris : sion regarde sleep1, c'est quand sleep 1 commence dans la session totale. Pas automatisable, ou alors en récupérant les temps deb fin de chaque recording node...
decay_from_open_ephys = seconds(start_reccord_sec - start);   %26*60 + 40; % seconds

% Align Open Ephys time with cumulative MATLAB session time
start_sec_decay = decay_from_open_ephys + start; % (s)

% Maximum valid time in Open Ephys detection list
time_end_reccord_oe = seconds(seconds(stop_acc) - start_sec_decay); % (s)



%% =========================================================================
% LOAD OPEN EPHYS MULTI-RUN DETECTION RESULTS
% =========================================================================


% On coupe avant la partie inutile (stim/debug)
txt = regexp(txt, 'Stim order', 'split');
txt = txt{1};

% % =========================================================================
% SPLIT PAR CONFIG (chaque bloc = un run)
% =========================================================================

blocks = regexp(txt, 'List of IS timing markers', 'split');

% Le premier bloc contient juste le header → on l'enlève
blocks = blocks(2:end);

nRuns = 1;% numel(blocks);

IS_all = cell(nRuns,1);
wake_fr_all = cell(nRuns,1);
wake_accel_all = cell(nRuns,1);

% % =========================================================================
% PARSE CHAQUE RUN
% =========================================================================

for i = 1:nRuns

    block = blocks{i};

    % Extraire toutes les listes []
    tokens = regexp(block, '\[(.*?)\]', 'tokens');

    % Format attendu :
    % tokens{1} = IS
    % tokens{2} = wake FR
    % tokens{3} = wake accel

    % --- IS ---
    if length(tokens) >= 1
        IS_list = str2num(tokens{1}{1});
    else
        IS_list = [];
    end

    % --- WAKE FR ---
    if length(tokens) >= 2
        wake_fr_list = str2num(tokens{2}{1});
    else
        wake_fr_list = [];
    end

    % --- WAKE ACCEL ---
    if length(tokens) >= 3
        wake_accel_list = str2num(tokens{3}{1});
    else
        wake_accel_list = [];
    end

    % -------- CLEAN TEMPS --------
    IS_list = IS_list(IS_list < time_end_reccord_oe);
    wake_fr_list = wake_fr_list(wake_fr_list < time_end_reccord_oe);
    wake_accel_list = wake_accel_list(wake_accel_list < time_end_reccord_oe);

    % -------- FORMAT Nx2 --------
    IS_all{i} = formatage_list(IS_list, seconds(start_sec_decay));
    wake_fr_all{i} = formatage_list(wake_fr_list, seconds(start_sec_decay));
    wake_accel_all{i} = formatage_list(wake_accel_list, seconds(start_sec_decay));

end

SetCurrentSession(session)

a1 = GetWidebandData(channels(1),'intervals',[start_acc stop_acc]);
a2 = GetWidebandData(channels(2),'intervals',[start_acc stop_acc]);
a3 = GetWidebandData(channels(3),'intervals',[start_acc stop_acc]);

% a = cell(141,1);
% 
% for i = 1:141
%     l = GetWidebandData(i,'intervals',[0 1]);
%     a{i} = l;
% end

acc = sqrt(a1(:,2).^2 + a2(:,2).^2 + a3(:,2).^2) * 0.008;

t = a1(:,1);  % temps

% mask_interval = (t >= 830) & (t <= 860);
% moyenne sur cet intervalle
% meanacc = mean(acc(mask_interval));
% 
% thresh = 15;
% 
% mask = abs(acc - meanacc) > thresh;
% 
% % temps
% tvec = t;
% 
% % gap max autorisé (en secondes)
% max_gap = 2;
% 
% % indices des points actifs
% idx = find(mask);
% 
% if isempty(idx)
%     acc_intervals = [];
% else
%     % différence de temps entre points actifs consécutifs
%     dt = diff(tvec(idx));
% 
%     % endroits où on casse un intervalle
%     split_points = find(dt > max_gap);
% 
%     % débuts et fins d'intervalles
%     start_idx = [idx(1); idx(split_points + 1)];
%     end_idx   = [idx(split_points); idx(end)];
% 
%     % construction des intervalles
%     acc_intervals = [tvec(start_idx), tvec(end_idx)];
% end

%% --- PARAMETRES ---
baseline_interval = [1970 1980];
window_size = 3;        % 1 seconde
step = 0.1;             % pas de glissement (plus petit = plus précis)
multiplior = 1;
%min_duration = 15;       % secondes

%% --- 1. VARIANCE DE REFERENCE ---
mask_base = (t >= baseline_interval(1)) & (t <= baseline_interval(2));
var_init = var(acc(mask_base));

%% --- 2. FENETRE GLISSANTE ---
t_start = t(1);
t_end   = t(end);

dt = median(diff(t));                 % pas d'échantillonnage
win_samples = round(window_size / dt);

var_sliding = movvar(acc, win_samples);

% associer à des temps (centrés)
t_centers = t;

%% --- 3. DETECTION WAKE ---
wake_mask = var_sliding > multiplior * var_init;

%% --- 4. CONVERSION EN INTERVALLES ---
idx = find(wake_mask);

ecart_int = 1;

if isempty(idx)
    acc_intervals = [];
else
    dt = diff(t_centers(idx));

    % on fusionne les fenêtres proches (gap < window_size)
    split_points = find(dt > ecart_int*window_size);

    start_idx = [idx(1); idx(split_points + 1)];
    end_idx   = [idx(split_points); idx(end)];

    acc_intervals = [t_centers(start_idx), ...
                     t_centers(end_idx) + window_size];
end

%% --- 5. FILTRAGE PAR DUREE MIN ---
durations = acc_intervals(:,2) - acc_intervals(:,1);
%acc_intervals = acc_intervals(durations >= min_duration, :);


%% =========================================================================
% PLOT COMPARAISON
% =========================================================================

figure;

ax = axes;        % crée un axe
hold(ax, 'on');   % active le hold sur cet axe

R.plotFiringRates(start_acc, stop_acc, step=5, smooth=45, ax=ax);

plot(ax, t, acc);

plot(ax, t(wake_mask), acc(wake_mask), 'r.', 'MarkerSize', 8);

%yline(ax, meanacc, '--r', 'Mean [830-860]');

xlabel(ax, 'Time');
ylabel(ax, 'Acceleration');
title(ax, sprintf('Acceleration magnitude | Multiplior = %.2f | Thresholding time = %.1fs | Window_size = %.1f', multiplior, baseline_interval(2)-baseline_interval(1), window_size));
grid(ax, 'on');

for i = 1:nRuns

    hold(ax, 'on');

    % WAKE ACCEL
    PlotIntervals(wake_accel_all{i}, ...
        'color',[1 0 0.5], ...
        'legend','Wake Accel', ax=ax)

    title(sprintf('RUN %d', i))

end

PlotIntervals(acc_intervals, ...
    'color',[0 0.7 0], ...
    'legend','Acc > Fixed_threshold', ...
    ax=ax)
