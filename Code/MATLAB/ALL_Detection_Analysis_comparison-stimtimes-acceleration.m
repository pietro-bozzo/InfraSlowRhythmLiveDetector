%% LOAD AND PARSE OE OUTPUT FILE

filename = '/mnt/hubel-data-103/Guillaume/OpenEphys_Stimulation_Tests/Output_oe/FINAL_FORM/IS_wake_timings_classic2.txt';
txt = fileread(filename);

%session = '/mnt/hubel-data-131/perceval/Rat003_20231212/testGuillaume/continuous/Acquisition_Board-100.Rhythm Data-B/continuous.xml';
session = '/mnt/hubel-data-131/perceval/Rat003_20231212/Rat003_20231212.xml';
[filebase,basename] = fileparts(session);

R = regions(session, ...
    regions='nr', ...
    events=["InfraSlowRhythm/slownr","InfraSlowRhythm/slowavalnr"], ...
    states=["sws","rem"]);

% Load MATLAB-detected intervals (ground truth reference)
us_intervals = R.eventIntervals('slownr');      % InfraSlow Rhythm (MATLAB detection)
us_avals     = R.eventIntervals('slowavalnr');  % Avalanches

% Extraire le dernier bloc (après le dernier STOP ACQUISITION)
blocks = regexp(txt, 'STOP ACQUISITION NUMBER \d+', 'split');
last_block = blocks{end};

% Extraire les 3 listes entre crochets
IS_str = regexp(last_block, '\[(.*?)\]', 'tokens');
Liste_timings_IS         = str2num(IS_str{1}{1});
Liste_timings_wake_fr    = str2num(IS_str{2}{1});
Liste_timings_wake_accel = str2num(IS_str{3}{1});

fprintf('IS detections     : %d timestamps\n', length(Liste_timings_IS));
fprintf('Wake FR detections: %d timestamps\n', length(Liste_timings_wake_fr));
fprintf('Wake Accel detect.: %d timestamps\n', length(Liste_timings_wake_accel));


accel_channels = [128 129 130];

interval = [22000 24000];

start_acc = interval(1);
stop_acc  = interval(2);


%% PARAMÈTRES DE SESSION

start_reccord_sec = 0;   % à adapter : temps cumulé session au début du recording OE (s)

% Si tu n'as pas de session MATLAB associée, tu peux définir manuellement :
% start_sec_decay = start_reccord_sec;  % offset à appliquer
% time_end_reccord_oe = max des timestamps valides

% Sinon, avec une session MATLAB (comme dans le pipeline existant) :
% L_start_stop = eventIntervals(R);
% start = L_start_stop(1);
% stop  = L_start_stop(2);
% decay_from_open_ephys = seconds(start_reccord_sec - start);
% start_sec_decay = decay_from_open_ephys + start;
% time_end_reccord_oe = stop - start_sec_decay;

% Version standalone sans session MATLAB :

start = 0; %L_start_stop(1); % Session start time (s)
stop  = 8000; %L_start_stop(2); % Session stop time (s)

start_reccord_sec = 1970; % Chosen cumulative session time (s) % Je crois avoir compris : sion regarde sleep1, c'est quand sleep 1 commence dans la session totale. Pas automatisable, ou alors en récupérant les temps deb fin de chaque recording node...
decay_from_open_ephys = start_reccord_sec - start;   %26*60 + 40; % seconds

% Align Open Ephys time with cumulative MATLAB session time
start_sec_decay = decay_from_open_ephys + start; % (s)

% Maximum valid time in Open Ephys detection list
time_end_reccord_oe = stop_acc - start_sec_decay; % (s)

%% FILTRAGE ET FORMATAGE

Liste_timings_IS         = Liste_timings_IS(Liste_timings_IS < time_end_reccord_oe);
Liste_timings_wake_fr    = Liste_timings_wake_fr(Liste_timings_wake_fr < time_end_reccord_oe);
Liste_timings_wake_accel = Liste_timings_wake_accel(Liste_timings_wake_accel < time_end_reccord_oe);

IS_OE_intervals          = formatage_list(Liste_timings_IS,         start_sec_decay);
wakeREM_fr_OE_intervals  = formatage_list(Liste_timings_wake_fr,    start_sec_decay);
wakeREM_accel_OE_intervals = formatage_list(Liste_timings_wake_accel, start_sec_decay);


%% ACCELERATION


SetCurrentSession(session)

a1 = GetWidebandData(accel_channels(1),'intervals',[start_acc stop_acc]);
a2 = GetWidebandData(accel_channels(2),'intervals',[start_acc stop_acc]);
a3 = GetWidebandData(accel_channels(3),'intervals',[start_acc stop_acc]);

acc = sqrt(a1(:,2).^2 + a2(:,2).^2 + a3(:,2).^2) * 0.008;

t = a1(:,1);  % temps

%% VISUALISATION

figure;
hold on;

R.plotFiringRates(start_acc,stop_acc,step=5,smooth=45);

plot(t, acc);

PlotIntervals(IS_OE_intervals,          'color', [0.4 0 1],   'alpha', 0.5, 'legend', 'IS (OE)');
PlotIntervals(wakeREM_fr_OE_intervals,  'color', [1 0 0],     'alpha', 0.6, 'legend', 'Wake FR (OE)');
PlotIntervals(wakeREM_accel_OE_intervals, 'color', [1 0 0.4], 'alpha', 0.6, 'legend', 'Wake Accel (OE)');
PlotIntervals(us_intervals,'legend','Pietro detection','Color',[0,1,0],'alpha',0.6)


xlabel('Temps (s)');
title('Détections Open Ephys — Rat013');
legend('show', 'Location', 'best');
grid on;

ax = gca;
ax.FontSize = 13;
ax.LineWidth = 1.5;


%% LOAD STIMULATION FILE

stim_filename = '/mnt/hubel-data-103/Guillaume/OpenEphys_Stimulation_Tests/Output_oe/FINAL_FORM/stim_20260701_094347.csv';
stim_table = readtable(stim_filename);

% Keep only STIM_START and STIM_END rows
stim_starts = stim_table.t_pc_ms(strcmp(stim_table.event, 'STIM_START')) / 1000;
stim_ends   = stim_table.t_pc_ms(strcmp(stim_table.event, 'STIM_END'))   / 1000;

% Pair them into [start, end] intervals
n_stim = min(length(stim_starts), length(stim_ends));
stim_intervals_raw = [stim_starts(1:n_stim), stim_ends(1:n_stim)+10];

% Apply temporal alignment offset (same as OE intervals)
stim_intervals = stim_intervals_raw + start_sec_decay;

PlotIntervals(stim_intervals, 'color', [1 1 0], 'alpha', 1, 'legend', 'Stimulations (STIM)')



%% INFOS DE DEBUG (optionnel)

% Extraire et afficher les lignes de debug
debug_match = regexp(last_block, "debug_ list:\s*(\[.*?\])", 'tokens', 'dotall');
if ~isempty(debug_match)
    fprintf('\n--- Debug info ---\n%s\n', debug_match{1}{1});
end

% Afficher le seuil SWS si présent
sws_thresh = regexp(last_block, 'Phase 2 SWS threshold: ([\d.]+)', 'tokens');
if ~isempty(sws_thresh)
    fprintf('SWS threshold : %s\n', sws_thresh{1}{1});
end

sws_time = regexp(last_block, 'Phase 2 SWS time accumulated \(s\): ([\d.]+)', 'tokens');
if ~isempty(sws_time)
    fprintf('SWS accumulated: %s s\n', sws_time{1}{1});
end