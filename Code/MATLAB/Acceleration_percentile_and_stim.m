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
session = "/mnt/hubel-data-149/Lumos_Rat013/2026-06-11_11-21-30/Record Node 131/experiment1/recording1/continuous/Rat013_11062026/Rat013_11062026.xml" ;
[filebase,basename] = fileparts(session);

filename = '/mnt/hubel-data-149/Lumos_Rat013/2026-06-11_11-21-30/STIM_and_TIMINGS/IS_wake_timings_Lumos1106_V1.txt';
txt = fileread(filename);

% R = regions(session, ...
%     regions='nr', ...
%     phases='sleepm', ...
%     events=["InfraSlowRhythm/slownr","InfraSlowRhythm/slowavalnr"], ...
%     states=["sws","rem"]);

R=regions(session);

channels = [128 129 130];

interval = [0 8000];

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

start = 0; %L_start_stop(1); % Session start time (s)
stop  = 8000; %L_start_stop(2); % Session stop time (s)

start_reccord_sec = start_acc; %1580; % Chosen cumulative session time (s) % Je crois avoir compris : sion regarde sleep1, c'est quand sleep 1 commence dans la session totale. Pas automatisable, ou alors en récupérant les temps deb fin de chaque recording node...
decay_from_open_ephys = start_reccord_sec - start;   %26*60 + 40; % seconds

% Align Open Ephys time with cumulative MATLAB session time
start_sec_decay = decay_from_open_ephys + start; % (s)

% Maximum valid time in Open Ephys detection list
time_end_reccord_oe = stop_acc - start_sec_decay; % (s)



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

    % --- WAKE ACCEL ---
    if length(tokens) >= 3
        wake_accel_list = str2num(tokens{3}{1});
    else
        wake_accel_list = [];
    end

    wake_accel_list = wake_accel_list(wake_accel_list < time_end_reccord_oe);

    wake_accel_all{i} = formatage_list(wake_accel_list, start_sec_decay);

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

%% =========================================================================
% PLOT COMPARAISON
% =========================================================================

figure;

ax = axes;        % crée un axe
hold(ax, 'on');   % active le hold sur cet axe

plot(ax, t, acc);

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

%% LOAD STIMULATION FILE

stim_filename = '/mnt/hubel-data-149/Lumos_Rat013/2026-06-11_11-21-30/STIM_and_TIMINGS/stim_20260611_112020.csv';
stim_table = readtable(stim_filename);

% Keep only STIM_START and STIM_END rows
stim_starts = stim_table.t_pc_ms(strcmp(stim_table.event, 'STIM_START')) / 1000;
stim_ends   = stim_table.t_pc_ms(strcmp(stim_table.event, 'STIM_END'))   / 1000;

% Pair them into [start, end] intervals
n_stim = min(length(stim_starts), length(stim_ends));
stim_intervals_raw = [stim_starts(1:n_stim), stim_ends(1:n_stim)+5];

% Apply temporal alignment offset (same as OE intervals)
stim_intervals = stim_intervals_raw + start_sec_decay;

PlotIntervals(stim_intervals, 'color', [1 0 0], 'alpha', 0.8, 'legend', 'Stimulations (STIM)')
