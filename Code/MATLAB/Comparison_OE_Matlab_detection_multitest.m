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

%filename = 'InfraSlowRhythmLiveDetector/Output_oe/Tests_sessions_finaux/IS_wake_timings_parallel_V5_karadoc0305.txt';
filename = '/mnt/hubel-data-103/Guillaume/OpenEphys_Stimulation_Tests/Output_oe/MULTITEST/IS_wake_timings_parallel_MULTIPHASE2407.txt';
txt = fileread(filename);

R = regions(session, ...
    regions='nr', ...
    events=["InfraSlowRhythm/slownr","InfraSlowRhythm/slowavalnr"], ...
    states=["sws","rem"]);

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
stop  = 8000;%L_start_stop(2); % Session stop time (s)

start_reccord_sec = 1970; %1580; % Chosen cumulative session time (s) % Je crois avoir compris : sion regarde sleep1, c'est quand sleep 1 commence dans la session totale. Pas automatisable, ou alors en récupérant les temps deb fin de chaque recording node...
decay_from_open_ephys = seconds(start_reccord_sec - start);   %26*60 + 40; % seconds

% Align Open Ephys time with cumulative MATLAB session time
start_sec_decay = decay_from_open_ephys + start; % (s)

% Maximum valid time in Open Ephys detection list
time_end_reccord_oe = stop - start_sec_decay; % (s)


%% Stimulation

%% LOAD STIMULATION FILE

stim_filename = '/mnt/hubel-data-103/Guillaume/OpenEphys_Stimulation_Tests/Output_oe/MULTITEST/stim_20260724_115429.csv';
stim_table = readtable(stim_filename);

% Keep only STIM_START and STIM_END rows
stim_starts = stim_table.t_pc_ms(strcmp(stim_table.event, 'STIM_START')) / 1000;
stim_ends   = stim_table.t_pc_ms(strcmp(stim_table.event, 'STIM_END'))   / 1000;

% Pair them into [start, end] intervals
n_stim = min(length(stim_starts), length(stim_ends));
stim_intervals_raw = [stim_starts(1:n_stim), stim_ends(1:n_stim)];

% Filter out intervals beyond valid OE recording time
valid_stim = stim_intervals_raw(:,1) < seconds(time_end_reccord_oe);
stim_intervals_raw = stim_intervals_raw(valid_stim, :);

% Apply temporal alignment offset (same as OE intervals)
stim_intervals = stim_intervals_raw + seconds(start_sec_decay);

stim_intervals = stim_intervals;



%% =========================================================================
% LOAD OPEN EPHYS MULTI-RUN DETECTION RESULTS
% =========================================================================


% On coupe avant la partie inutile (stim/debug)
%txt = regexp(txt, 'Stim order', 'split');
%txt = txt{1};
blocks = regexp(txt, 'STOP ACQUISITION NUMBER \d+', 'split');
txt = blocks{end};

%% =========================================================================
% SPLIT PAR CONFIG (chaque bloc = un run)
% =========================================================================

blocks = regexp(txt, 'IS timing markers', 'split');

% Le premier bloc contient juste le header → on l'enlève
blocks = blocks(2:end);

nRuns = 2;%numel(blocks);

IS_all = cell(nRuns,1);
wake_fr_all = cell(nRuns,1);
wake_accel_all = cell(nRuns,1);

%% =========================================================================
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

%% =========================================================================
% PLOT COMPARAISON
% =========================================================================

figure;

for i = 1:nRuns

    ax = subplot(nRuns,1,i); hold on

    % FIRING RATE
    R.plotFiringRates(start, stop, step=5, smooth=45, ax=ax);

    xline(seconds(start_sec_decay), 'r--', 'LineWidth', 1);

    % MATLAB ground truth
    PlotIntervals(us_intervals, ...
        'legend','MATLAB (Pietro)', ...
        'Color',[0 1 0], ...
        'alpha',0.4)

    % Nettoyage IS (IMPORTANT)
    B = IS_all{i};
    %B = SubtractIntervals(B, wake_fr_all{i});
    %B = SubtractIntervals(B, wake_accel_all{i});

    % OE IS
    PlotIntervals(B, ...
        'color',[0.4 0 1], ...
        'alpha',0.5, ...
        'legend',sprintf('IS OE run %d', i))

    % WAKE FR
    PlotIntervals(wake_fr_all{i}, ...
        'color',[1 0 0], ...
        'legend','Wake FR')

    % WAKE ACCEL
    PlotIntervals(wake_accel_all{i}, ...
        'color',[1 0 0.5], ...
        'legend','Wake Accel')

    % Stimulation intervals
    PlotIntervals(stim_intervals, 'color', [0.93 0.85 0.04], 'alpha', 1.0, 'legend', 'Stimulations (STIM)', 'bottom', false)

    title(sprintf('RUN %d', i))

end

%% =========================================================================
% F-SCORE PAR RUN
% =========================================================================

F_scores = zeros(nRuns,1);
Precision_all = zeros(nRuns,1);
Recall_all = zeros(nRuns,1);

for i = 1:nRuns

    A = us_intervals;

    % Nettoyage IS
    B = IS_all{i};
    B = SubtractIntervals(B, wake_fr_all{i});
    B = SubtractIntervals(B, wake_accel_all{i});

    if isempty(B)
        continue
    end

    % --- TP ---
    TP = IntersectIntervals(A,B);
    TP_time = sum(TP(:,2) - TP(:,1));

    % --- FP ---
    FP = SubtractIntervals(B,A);
    FP_time = sum(FP(:,2) - FP(:,1));

    % --- FN ---
    FN = SubtractIntervals(A,B);
    FN_time = sum(FN(:,2) - FN(:,1));

    % --- METRICS ---
    Precision = TP_time / (TP_time + FP_time + eps);
    Recall    = TP_time / (TP_time + FN_time + eps);
    F_score   = 2 * (Precision * Recall) / (Precision + Recall + eps);

    Precision_all(i) = Precision;
    Recall_all(i) = Recall;
    F_scores(i) = F_score;

    fprintf('\n===== RUN %d =====\n', i);
    fprintf('Precision : %.2f %%\n', Precision*100);
    fprintf('Recall    : %.2f %%\n', Recall*100);
    fprintf('F-score   : %.2f %%\n', F_score*100);

end

%% =========================================================================
% PLOT SCORES
% =========================================================================

figure;
plot(1:nRuns, F_scores*100, '-o', 'LineWidth', 2)
hold on
plot(1:nRuns, Precision_all*100, '--', 'LineWidth', 1.5)
plot(1:nRuns, Recall_all*100, '--', 'LineWidth', 1.5)

legend('F-score','Precision','Recall')
xlabel('Run index')
ylabel('Score (%)')
title('Performance vs configuration')
grid on