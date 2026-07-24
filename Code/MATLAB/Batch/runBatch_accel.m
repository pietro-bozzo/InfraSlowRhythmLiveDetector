sessions = "IS_units_sessions.batch";

[lessessions,extra_args] = readBatchFile(sessions);

n_sessions = 1;%14+17;

channel = [128 129 130];

interval = [830 840];

args = repmat({channel, interval}, n_sessions, 1);

[t, acc, a1, a2, a3, acc_glissante, mean_acceleration_decay, threshold_line, threshold_accel] = runBatch(sessions, @plotAccelerationWithThreshold, args);

k = 1.2254858/32767;
a1i = a1{1}(:,2)*k;
a2i = a2{1}(:,2)*k;
a3i = a3{1}(:,2)*k;


%% Plot

% figure; hold on
% 
% nSessions = length(t);
% colors = lines(nSessions);
% 
% for i = 1:nSessions
% 
%     ti   = t{i};
%     acci = acc{i};
%     accg = acc_glissante{i};
%     base = mean_acceleration_decay{i};
%     thr  = threshold_line{i};
% 
%     % RAW (atténué)
%     plot(ti, acci, '--', 'Color', colors(i,:)*0.5);
% 
%     % SMOOTHED
%     plot(ti, accg, 'Color', colors(i,:), 'LineWidth', 1.5, ...
%         'DisplayName', ['Session ' num2str(i)]);
% 
%     % BASELINE
%     yline(base, '--', 'Color', colors(i,:)*0.8);
% 
%     % THRESHOLDS
%     yline(base + thr, ':', 'Color', colors(i,:));
%     yline(base - thr, ':', 'Color', colors(i,:));
% 
%     % CONDITION WAKE (recalculée ici)
%     condition_wake = abs(accg - base) > thr;
%     wake_idx = find(condition_wake);
% 
%     scatter(ti(wake_idx), accg(wake_idx), 10, ...
%         'MarkerEdgeColor', colors(i,:), ...
%         'MarkerFaceColor', colors(i,:));
% end
% 
% legend show
% xlabel('Time (s)')
% ylabel('Acceleration (µm/s²)')
% title('Acceleration + Wake Threshold (multi-session)')

nSessions = length(t);
colors = lines(nSessions);

%% =========================
%% FIGURE 1 : ACCELERATION
%% =========================
figure; hold on

for i = 1:nSessions
    ti   = t{i};
    acci = acc{i};
    
    %plot(ti, acci, 'Color', colors(i,:), ...
        %'DisplayName', ['Session ' num2str(i)]);
    a1i = a1{i}(:,2)*k;
    plot(ti, a1i, 'Color', [1 0 0]);
    a2i = a2{i}(:,2)*k;
    plot(ti, a2i, 'Color', [0 1 0]);
    a3i = a3{i}(:,2)*k;
    plot(ti, a3i, 'Color', [0 0 1]);
end

legend show
xlabel('Time (s)')
ylabel('Acceleration (µm/s²)')
title('Raw Acceleration (all sessions)')


%% =========================
%% FIGURE 2 : THRESHOLDS
%% =========================
figure; hold on

for i = 1:nSessions
    
    ti   = t{i};
    base = mean_acceleration_decay{i};
    thr  = threshold_line{i};
    thperc = threshold_accel{i};
    
    % Baseline
    yline(thr, '--', 'Color', colors(i,:), ...
        'DisplayName', ['Baseline S' num2str(i)]);
    
    % Thresholds
    yline(thperc, ':', 'Color', colors(i,:));
end

legend show
xlabel('Time (s)')
ylabel('Acceleration (µm/s²)')
title('Thresholds (per session)')


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%ù

%session = '/mnt/hubel-data-131/perceval/Rat003_20231214/Rat003_20231214.xml';
%filename = 'InfraSlowRhythmLiveDetector/Output_oe/Perceval_003_20231214/IS_wake_timings_Perceval_003_20231214_simple.txt';
%start_record_sec = 830;
%[F_score, TP_pct, FP_pct, FN_pct] = Stat_comparison_OE_Matlab_function(session, filename, start_reccord_sec);
%display([F_score, TP_pct, FP_pct, FN_pct]);