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

session = '/mnt/hubel-data-139/karadoc/Rat004_20240228/Rat004_20240228.xml'; % Change recording day here
[filebase,basename] = fileparts(session);

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

% !!TO MODIFY depending of the session!! Time offset applied in Open Ephys (File Reader start time) 
decay_from_open_ephys = 26*60 + 40; % seconds

% Align Open Ephys time with cumulative MATLAB session time
start_sec_decay = decay_from_open_ephys + start; % (s)

% Maximum valid time in Open Ephys detection list
time_end_reccord_oe = stop - start_sec_decay % (s)


%% LOAD OPEN EPHYS DETECTION RESULTS

% Raw timestamps detected by Open Ephys (start1, end1, start2, end2, ...)
Liste_timings_IS = [27.072300000000116, 200.24129999997285, 221.98859999996932, 438.3113999999342, 501.14639999992403, 502.3817999999238, 517.6964999999213, 598.6364999999082, 627.3701999999035, 637.8710999999018, 652.0142999998995, 685.6682999998941, 695.2319999998925, 889.9565999998609, 929.9792999998544, 1027.4054999998568, 1041.335699999929, 1137.6543000004274, 1161.0630000005485, 1244.43120000098, 1259.128200001056, 1265.9868000010915, 1283.1333000011803, 1393.3608000017507, 1414.46910000186, 1537.2636000024954, 1551.8115000025707, 1616.606100002906, 1652.368800003091, 1680.8469000032385, 1688.472300003278, 1700.080800003338, 1718.2710000034322, 1789.157400003799, 1841.8749000040718, 1925.179200004503, 1939.8336000045788, 1980.9852000047917, 2012.2110000049533, 2141.928000004622, 2168.9364000044734, 2433.013800003021, 2453.589600002908, 2567.3316000022824, 2593.062000002141, 2625.608400001962, 2778.9897000011183, 2798.905200001009, 2897.8650000004645, 2945.3640000002033, 2961.1260000001166, 3045.8573999996506, 3082.2377999994505, 3105.582599999322, 3224.692199998667, 3245.1188999985548, 3382.0352999978018, 3394.6235999977325, 3412.174799997636, 3414.5816999976228, 3720.960899995938, 3726.4349999959077, 3769.9721999956682, 3772.3364999956552, 3871.1684999951117, 3880.966499995058, 3908.379599994907, 3920.54189999484, 4150.858799994745, 4157.887799994856, 4627.297200002296, 4630.8969000023535, 4636.498800002442, 4750.262100004245, 4761.487200004423, 4955.892300007505, 4973.27310000778, 5125.802400010198, 5141.031900010439, 5307.725700013081, 5313.242400013169, 5403.682200014602, 5419.699800014856, 5482.577400015853, 5500.810200016142, 5548.905600016904, 5592.336300017592, 5660.815800018678];
Liste_timings_wake = [200.24129999997285, 209.44289999997136, 447.5342999999327, 497.5040999999246, 502.3817999999238, 509.1977999999227, 598.6364999999082, 604.3448999999073, 605.793299999907, 616.2515999999054, 637.8710999999018, 643.6646999999009, 906.7196999998582, 918.7541999998563, 1027.4054999998568, 1035.6911999998997, 1137.6543000004274, 1145.8548000004698, 1244.43120000098, 1253.7819000010284, 1265.9868000010915, 1275.912600001143, 1393.3608000017507, 1400.4324000017873, 1537.2636000024954, 1545.3576000025373, 1616.606100002906, 1616.6487000029063, 1616.7339000029067, 1617.3303000029098, 1618.2888000029147, 1618.8000000029174, 1618.8426000029176, 1621.8885000029334, 1624.6362000029476, 1640.4195000030293, 1640.9733000030321, 1648.9608000030735, 1680.8469000032385, 1681.336800003241, 1681.4220000032415, 1681.4646000032417, 1700.080800003338, 1707.2589000033752, 1801.5540000038632, 1805.558400003884, 1805.579700003884, 1805.601000003884, 1805.6436000038843, 1806.9855000038913, 1816.7409000039418, 1827.6678000039983, 1925.179200004503, 1934.082600004549, 1980.9852000047917, 1994.4468000048614, 1996.1934000048705, 1996.7685000048734, 1996.9602000048744, 1997.1093000048752, 2141.928000004622, 2142.4179000046192, 2142.439200004619, 2142.481800004619, 2142.630900004618, 2161.715700004513, 2433.013800003021, 2447.242200002943, 2567.3316000022824, 2576.5545000022316, 2577.023100002229, 2587.374900002172, 2625.608400001962, 2750.6181000012743, 2755.3041000012486, 2765.3577000011933, 2802.9096000009868, 2814.0921000009253, 2814.2199000009246, 2814.283800000924, 2814.518100000923, 2814.6033000009224, 2814.6246000009223, 2814.858900000921, 2815.6470000009167, 2837.394300000797, 2837.415600000797, 2837.4795000007966, 2838.352800000792, 2846.127300000749, 2852.879400000712, 2870.686200000614, 2871.090900000612, 2879.4831000005656, 2884.12650000054, 2896.2249000004736, 2945.3640000002033, 2951.8605000001676, 3045.8573999996506, 3056.2730999995933, 3057.764099999585, 3057.785399999585, 3057.8492999995847, 3072.3971999995047, 3105.582599999322, 3199.984199998803, 3208.3976999987567, 3218.6429999987004, 3245.1188999985548, 3253.5323999985085, 3259.3046999984767, 3259.3259999984766, 3259.3472999984765, 3294.343199998284, 3294.9395999982808, 3294.9608999982806, 3298.198499998263, 3380.0756999978125, 3394.6235999977325, 3398.010299997714, 3400.8431999976983, 3408.8306999976544, 3414.5816999976228, 3429.960299997538, 3431.6855999975287, 3444.891599997456, 3445.487999997453, 3445.5092999974527, 3445.5305999974526, 3455.1368999973997, 3456.372299997393, 3457.7567999973853, 3469.9190999973184, 3707.8826999960097, 3707.9039999960096, 3707.989199996009, 3708.031799996009, 3708.0530999960088, 3708.3299999960072, 3719.256899995947, 3726.4349999959077, 3745.7540999958014, 3750.0992999957775, 3763.9655999957013, 3772.3364999956552, 3786.905699995575, 3790.590599995555, 3802.6037999954888, 3820.8578999953884, 3829.2074999953425, 3840.6881999952793, 3866.588999995137, 3880.966499995058, 3889.3586999950116, 3892.915799994992, 3905.312399994924, 3920.54189999484, 3920.56319999484, 3920.58449999484, 3920.60579999484, 3920.6270999948397, 4063.4222999940544, 4063.7417999940526, 4139.18639999456, 4157.887799994856, 4385.989499998472, 4390.142999998538, 4603.782000001924, 4603.803300001924, 4603.995000001927, 4604.058900001928, 4604.101500001929, 4607.5521000019835, 4620.268200002185, 4630.8969000023535, 4632.984300002387, 4750.262100004245, 4753.05240000429, 4955.892300007505, 4959.38550000756, 4960.322700007575, 4964.43360000764, 5128.997400010248, 5131.809000010293, 5482.577400015853, 5492.758800016014, 5548.905600016904, 5548.990800016905, 5549.225100016909, 5554.592700016994, 5569.417500017229, 5581.6224000174225, 5660.815800018678, 5670.826800018836];

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

Precision_time = 100 * TP_time / (TP_time + FP_time)
FP_pct = 100 * FP_time / TotalB;
FN_pct = 100 * FN_time / TotalA;
Recall_time = 100 * TP_time / (TP_time + FN_time)

% 4) F-score

F_score = (2 * Precision_time * Recall_time) / (Precision_time + Recall_time)


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