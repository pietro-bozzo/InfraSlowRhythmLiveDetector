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

session = '/mnt/hubel-data-131/perceval/Rat003_20231218/Rat003_20231218.xml'; % Change recording day here
[filebase,basename] = fileparts(session);

R = regions(session, ...
    regions='nr', ...
    phases='sleeps', ...
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

% !!TO MODIFY depending of the session!! Time offset applied in Open Ephys (File Reader start time) 
decay_from_open_ephys = 8*60 + 05; % seconds

% Align Open Ephys time with cumulative MATLAB session time
start_sec_decay = decay_from_open_ephys + start; % (s)

% Maximum valid time in Open Ephys detection list
time_end_reccord_oe = stop - start_sec_decay % (s)


%% LOAD OPEN EPHYS DETECTION RESULTS

% Raw timestamps detected by Open Ephys (start1, end1, start2, end2, ...)
Liste_timings_IS = [...];        % InfraSlow detections (Open Ephys)
Liste_timings_wake = [...];      % Wake detections (Open Ephys)

% Format detection lists into Nx2 interval matrices
% Also apply temporal alignment offset (start_sec_decay)
IS_OE_intervals     = formatage_list(Liste_timings_IS,start_sec_decay);
wakeREM_OE_intervals = formatage_list(Liste_timings_wake,start_sec_decay);


%% VISUAL COMPARISON — MATLAB vs OPEN EPHYS DETECTION

R.plotFiringRates(start,stop,step=5,smooth=45);

% MATLAB detection (reference)
PlotIntervals(us_intervals,'legend','Pietro detection','Color',[0,1,0],'alpha',0.6)

% Open Ephys wake detection
PlotIntervals(wakeREM_OE_intervals,'color',[1 0 0],'legend','Nathan detection wake (OE)')

% Open Ephys InfraSlow detection
PlotIntervals(IS_OE_intervals,'color',[0.4 0 1],'alpha',0.5,'legend','Nathan detection IS (OE)')

plotOnScreen('right')


%% PERFORMANCE METRICS — TIME-BASED F-SCORE (currently used)

% Evaluate detection quality in terms of time overlap
% A = MATLAB detection (ground truth)
% B = Open Ephys detection

% Restrict MATLAB intervals to current session range
index = (us_intervals(:,1) < stop & start < us_intervals(:,1));
A = us_intervals(index,:);
B = IS_OE_intervals;

% 1) Build all breakpoints between A and B
t = unique([A(:); B(:)]);
t = sort(t);

TP_time = 0; % True Positive time (correct detection)
FP_time = 0; % False Positive time (detected but should not)
FN_time = 0; % False Negative time (missed detection)

% Compute overlap segment by segment
for i = 1:length(t)-1
    dt = t(i+1) - t(i);
    if dt == 0, continue, end

    inA = any(t(i) >= A(:,1) & t(i+1) <= A(:,2));
    inB = any(t(i) >= B(:,1) & t(i+1) <= B(:,2));

    if inA && inB
        TP_time = TP_time + dt;
    elseif inB && ~inA
        FP_time = FP_time + dt;
    elseif inA && ~inB
        FN_time = FN_time + dt;
    end
end

% 2) Normalize by total detected time

TotalB = TP_time + FP_time; % Total detected by Open Ephys
TotalA = TP_time + FN_time; % Total true (MATLAB)

TP_pct = 100 * TP_time / TotalB;   % % of Open Ephys detection that is correct

% 3) Precision and Recall (time-based)

Precision_time = 100 * TP_time / (TP_time + FP_time);
FP_pct = 100 * FP_time / TotalB;
FN_pct = 100 * FN_time / TotalA;
Recall_time = 100 * TP_time / (TP_time + FN_time);

% 4) F-score

F_score = (2 * Precision_time * Recall_time) / (Precision_time + Recall_time);


%% ALTERNATIVE METHOD — INTERVAL INTERSECTION

% Compute overlap directly using interval intersection
A = us_intervals;
B = IS_OE_intervals;

TP_intervals = IntersectIntervals(A,B);
TP_time_2 = sum(TP_intervals(:,2) - TP_intervals(:,1));

% Recompute metrics (same interpretation as above)

TotalB = TP_time + FP_time;
TotalA = TP_time + FN_time;

TP_pct = 100 * TP_time / TotalB;
FP_pct = 100 * FP_time / TotalB;
FN_pct = 100 * FN_time / TotalA;

Precision_time = 100 * TP_time / (TP_time + FP_time);
Recall_time = 100 * TP_time / (TP_time + FN_time);

F_score = (2 * Precision_time * Recall_time) / (Precision_time + Recall_time);

% =========================================================================
% END OF PIPELINE
% =========================================================================