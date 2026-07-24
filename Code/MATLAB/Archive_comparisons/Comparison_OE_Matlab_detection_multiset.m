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

session = '/mnt/hubel-data-131/perceval/Rat003_20231214/Rat003_20231214.xml'; % Change recording day here
[filebase,basename] = fileparts(session);

filename = 'InfraSlowRhythmLiveDetector/Output_oe/Perceval_003_20231214/IS_multi_run.txt';
txt = fileread(filename);

R = regions(session, ...
    regions='nr', ...
    phases='sleepm', ...
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
stop  = L_start_stop(2); % Session stop time (s)

start_reccord_sec = 830; %1580; % Chosen cumulative session time (s) % Je crois avoir compris : sion regarde sleep1, c'est quand sleep 1 commence dans la session totale. Pas automatisable, ou alors en récupérant les temps deb fin de chaque recording node...
decay_from_open_ephys = seconds(start_reccord_sec - start);   %26*60 + 40; % seconds

% Align Open Ephys time with cumulative MATLAB session time
start_sec_decay = decay_from_open_ephys + start; % (s)

% Maximum valid time in Open Ephys detection list
time_end_reccord_oe = stop - start_sec_decay; % (s)



%% =========================================================================
% LOAD OPEN EPHYS MULTI-RUN DETECTION RESULTS
% =========================================================================


% Split par RUN
blocks = regexp(txt, 'RUN \d+ CONFIG:', 'split');
blocks = blocks(2:end); % premier élément vide

nRuns = numel(blocks);

IS_all = cell(nRuns,1);
wake_fr_all = cell(nRuns,1);
wake_accel_all = cell(nRuns,1);

for i = 1:nRuns

    current_block = run_blocks{i};

    % Extract lists inside []
    tokens = regexp(current_block, '\[(.*?)\]', 'tokens');

    % According to your file:
    % tokens{1} = IS
    % tokens{2} = WAKE
    Liste_IS = str2num(tokens{1}{1});
    Liste_WAKE = str2num(tokens{2}{1});

    % Cut invalid times
    Liste_IS   = Liste_IS(Liste_IS < time_end_reccord_oe);
    Liste_WAKE = Liste_WAKE(Liste_WAKE < time_end_reccord_oe);

    % Format into intervals
    IS_all{i} = formatage_list(Liste_IS, seconds(start_sec_decay));
    wake_all{i} = formatage_list(Liste_WAKE, seconds(start_sec_decay));

end

%% =========================================================================
% VISUAL COMPARISON — MULTI RUN
% =========================================================================

figure;

for i = 1:nRuns

    ax = subplot(nRuns,1,i); hold(ax,'on')

    % --- Firing rate background ---
    R.plotFiringRates(start,stop,step=5,smooth=45,ax=ax);

    axes(ax); hold on

    % --- MATLAB reference ---
    PlotIntervals(us_intervals, ...
        'legend','MATLAB (Pietro)', ...
        'Color',[0 1 0], ...
        'alpha',0.5)

    % --- OE IS ---
    PlotIntervals(IS_all{i}, ...
        'color',[0.4 0 1], ...
        'alpha',0.5, ...
        'legend',sprintf('OE IS - run %d', i))

    % --- OE WAKE ---
    PlotIntervals(wake_all{i}, ...
        'color',[1 0 0], ...
        'legend',sprintf('OE wake - run %d', i))

    title(sprintf('RUN %d comparison', i))

end

%% PERFORMANCE METRICS — TIME-BASED F-SCORE (currently used)

% Evaluate detection quality in terms of time overlap
% A = MATLAB detection (ground truth)
% B = Open Ephys detection

% Restrict MATLAB intervals to current session range
% index = (us_intervals(:,1) < stop & start < us_intervals(:,1));
% A = us_intervals(index,:);
% B = IS_OE_intervals;
% 
% % 1) Build all breakpoints between A and B
% t = unique([A(:); B(:)]);
% t = sort(t);
% 
% TP_time = 0; % True Positive time (correct detection)
% FP_time = 0; % False Positive time (detected but should not)
% FN_time = 0; % False Negative time (missed detection)
% 
% % Compute overlap segment by segment
% for i = 1:length(t)-1
%     dt = t(i+1) - t(i);
%     if dt == 0, continue, end
% 
%     inA = any(t(i) >= A(:,1) & t(i+1) <= A(:,2));
%     inB = any(t(i) >= B(:,1) & t(i+1) <= B(:,2));
% 
%     if inA && inB
%         TP_time = TP_time + dt;
%     elseif inB && ~inA
%         FP_time = FP_time + dt;
%     elseif inA && ~inB
%         FN_time = FN_time + dt;
%     end
% end
% 
% % 2) Normalize by total detected time
% 
% TotalB = TP_time + FP_time; % Total detected by Open Ephys
% TotalA = TP_time + FN_time; % Total true (MATLAB)
% 
% TP_pct = 100 * TP_time / TotalB;   % % of Open Ephys detection that is correct
% 
% % 3) Precision and Recall (time-based)
% 
% Precision_time = 100 * TP_time / (TP_time + FP_time)
% FP_pct = 100 * FP_time / TotalB;
% FN_pct = 100 * FN_time / TotalA;
% Recall_time = 100 * TP_time / (TP_time + FN_time)
% 
% % 4) F-score
% 
% F_score = (2 * Precision_time * Recall_time) / (Precision_time + Recall_time)
% 

%% ALTERNATIVE METHOD — INTERVAL INTERSECTION

% Compute overlap directly using interval intersection
A = us_intervals;
B = IS_OE_intervals;

TP_intervals = IntersectIntervals(A,B);
TP_time = sum(TP_intervals(:,2) - TP_intervals(:,1));

FP_intervals = SubtractIntervals(B, A);
FP_time = sum(FP_intervals(:,2) - FP_intervals(:,1));

FN_intervals = SubtractIntervals(A, B);
FN_time = sum(FN_intervals(:,2) - FN_intervals(:,1));

% Recompute metrics (same interpretation as above)

TotalB = TP_time + FP_time;
TotalA = TP_time + FN_time;

TP_pct = 100 * TP_time / TotalB;
FP_pct = 100 * FP_time / TotalB;
FN_pct = 100 * FN_time / TotalA;

Precision_time = 100 * TP_time / (TP_time + FP_time);
Recall_time = 100 * TP_time / (TP_time + FN_time);

F_score = (2 * Precision_time * Recall_time) / (Precision_time + Recall_time);

display(F_score);

% =========================================================================
% END OF PIPELINE
% =========================================================================