function [t, acc, a1, a2, a3, acc_glissante, mean_acceleration_decay, threshold_line, threshold_acceleration] = plotAccelerationWithThreshold(session, channels, intervals)

% INPUTS:
% session   : nom/path session
% channels  : [chX chY chZ]
% intervals : [start stop] en secondes

%% PARAMETERS (identiques au Python)
time_value_acceleration = 8;     % fenêtre glissante (s)
time_limit_integration  = 20;    % baseline (s)
percentage_accel        = 70;    % percentile
multiplior_tresh_accel = 1;      % multiplier

%% Load session
SetCurrentSession(session)

start_acc = intervals(1);
stop_acc  = intervals(2);

%% Load accelerometer
a1 = GetWidebandData(channels(1),'intervals',[start_acc stop_acc]);
a2 = GetWidebandData(channels(2),'intervals',[start_acc stop_acc]);
a3 = GetWidebandData(channels(3),'intervals',[start_acc stop_acc]);

t = a1(:,1);

%% Compute norm (comme Python)
acc = sqrt(a1(:,2).^2 + a2(:,2).^2 + a3(:,2).^2) * 10000;

%% Sampling rate
dt = mean(diff(t));
fs = 1 / dt;

%% Sliding mean (8 s)
window_size = round(time_value_acceleration * fs);
acc_glissante = movmean(acc, window_size);

%% Baseline (20 premières secondes)
t0 = t(1);
idx_baseline = t <= (t0 + time_limit_integration);

mean_acceleration_decay = mean(acc(idx_baseline));

%% Threshold percentile (sur baseline aussi !)
threshold_acceleration = prctile(acc(idx_baseline), percentage_accel);

%% Threshold "réel" utilisé dans Python
threshold_line = abs(threshold_acceleration * multiplior_tresh_accel - mean_acceleration_decay);

%% Condition wake (pour debug/validation)
condition_wake = abs(acc_glissante - mean_acceleration_decay) > threshold_line;

end