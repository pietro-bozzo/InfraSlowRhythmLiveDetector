%% PARAMÈTRES (à adapter depuis le .xml)
n_channels   = 142;      % nombre total de canaux dans le fichier
fs           = 1250;     % fréquence d'échantillonnage LFP (Hz)
%% LIRE n_channels DEPUIS LE XML
xml_file = '/mnt/hubel-data-149/Lumos_Rat013/2026-05-07_16-11-23/Record Node 106/experiment1/recording1/continuous/Rat013_07052026/Rat013_07052026.xml';
xml = xmlread(xml_file);
n_channels = str2double(xml.getElementsByTagName('nChannels').item(0).getFirstChild.getData);
fs = str2double(xml.getElementsByTagName('lfpSamplingRate').item(0).getFirstChild.getData);

accel_ch     = [128, 129, 130];  % indices 0-based des canaux accéléromètre

lfp_file = '/mnt/hubel-data-149/Lumos_Rat013/2026-05-07_16-11-23/Record Node 106/experiment1/recording1/continuous/Rat013_07052026/Rat013_07052026.lfp';

%% LECTURE DES CANAUX ACCÉLÉROMÈTRE
fid = fopen(lfp_file, 'r');
raw = fread(fid, 'int16');
fclose(fid);

fprintf('n_channels = %d\n', n_channels);
fprintf('fs = %d Hz\n', fs);

% Reshape : chaque colonne = un canal
raw = reshape(raw, n_channels, []);  % [n_channels x n_samples]

% Extraire les 3 canaux (indices 1-based en MATLAB)
acc_x = double(raw(accel_ch(1)+1, :));
acc_y = double(raw(accel_ch(2)+1, :));
acc_z = double(raw(accel_ch(3)+1, :));


%% NORME DE L'ACCÉLÉRATION
% acc_norm = sqrt(acc_x.^2 + acc_y.^2 + acc_z.^2);
% var_win = round(0.1 * fs);  % fenêtre de 1s, ajustable
% acc_norm = movvar(acc_norm_smooth, var_win);
% % 
acc_norm_raw = sqrt(acc_x.^2 + acc_y.^2 + acc_z.^2);
smooth_win = round(0.1 * fs);  % 0.5s, ajustable
acc_norm = movmean(acc_norm_raw, smooth_win);
% % 3) Variance glissante sur la norme lissée
%var_win = round(0.2 * fs);  % fenêtre de 1s, ajustable
%acc_norm = movvar(acc_norm_smooth, var_win);


%% LOAD STIMULATION TIMES

stim_file = '/mnt/hubel-data-149/Lumos_Rat013/2026-05-07_16-11-23/Record Node 106/experiment1/recording1/continuous/Rat013_07052026/stim_times.txt';
fid = fopen(stim_file, 'r');
raw_lines = textscan(fid, '%s', 'Delimiter', '\n', 'Whitespace', '');
fclose(fid);
raw_lines = raw_lines{1};

% Parse STIM lines
stim_times_s  = [];
stim_durations = [];

for i = 1:length(raw_lines)
    line = strtrim(raw_lines{i});
    if startsWith(line, 'STIM,')
        parts = strsplit(line, ',');
        % Parse time MM:SS.mmm -> seconds
        time_str = parts{2};
        time_parts = strsplit(time_str, ':');
        minutes = str2double(time_parts{1});
        seconds = str2double(time_parts{2});
        t_s = minutes * 60 + seconds;
        % Parse duration (e.g. "0.20s")
        dur_str = parts{4};
        dur_s = str2double(dur_str(1:end-1));  % remove trailing 's'

        stim_times_s(end+1)   = t_s;
        stim_durations(end+1) = dur_s;
    end
end

%% LOAD PRECISE STIM TIMES FROM .opt.evt

evt_file = '/mnt/hubel-data-149/Lumos_Rat013/2026-05-07_16-11-23/Record Node 106/experiment1/recording1/continuous/Rat013_07052026/Rat013_07052026.opt.evt';
fid = fopen(evt_file, 'r');
raw_lines = textscan(fid, '%s', 'Delimiter', '\n', 'Whitespace', '');
fclose(fid);
raw_lines = raw_lines{1};

% Extract only 'beg' timestamps (in samples), convert to seconds
stim_times_s = [];

for i = 1:length(raw_lines)
    line = strtrim(raw_lines{i});
    if endsWith(line, 'beg')
        parts = strsplit(line);
        t_samples = str2double(parts{1});
        stim_times_s(end+1) = t_samples / 1000;  % samples -> secondes
    end
end

fprintf('Found %d beg events\n', length(stim_times_s));

n_stims = length(stim_times_s);
fprintf('Found %d stimulations\n', n_stims);


%% PETH PARAMETERS

win_pre  = 1.0;  % seconds before stim
win_post = 3.0;  % seconds after stim
win_total = win_pre + win_post;

n_samples_pre  = round(win_pre  * fs);
n_samples_post = round(win_post * fs);
n_samples_win  = n_samples_pre + n_samples_post;

t_axis = linspace(-win_pre, win_post, n_samples_win);  % time axis (s)


%% EXTRACT PETH SNIPPETS

% Group stimulations by duration

unique_durations = unique(stim_durations);
%unique_durations = [0.10, 0.20, 0.30, 0.40, 0.50];
n_dur = length(unique_durations);

figure;
%colors = lines(n_dur);
colors = [linspace(0,1,n_dur)', zeros(n_dur,1), linspace(1,0,n_dur)'];
%          canal R               canal G          canal B
% Stim window
%xline(0,          'k--', 'LineWidth', 1.2);

for d = 1:n_dur
    dur = unique_durations(d);
    idx_dur = find(stim_durations == dur);

    snippets = NaN(length(idx_dur), n_samples_win);

    for k = 1:length(idx_dur)
        i_stim = idx_dur(k);
        t_stim = stim_times_s(i_stim);

        % Convert stim time to sample index
        idx_center = round(t_stim * fs);
        idx_start  = idx_center - n_samples_pre + 1;
        idx_end    = idx_center + n_samples_post;

        % Skip if out of bounds
        if idx_start < 1 || idx_end > length(acc_norm)
            warning('Stim %d out of bounds, skipping.', i_stim);
            continue;
        end

        
        %snippets(k, :) = acc_norm(idx_start:idx_end);
        baseline = mean(acc_norm(idx_start:idx_center));
        snippets(k, :) = abs(acc_norm(idx_start:idx_end) - baseline);
    end

    % Average across trials (ignoring NaN)
    mean_acc = nanmean(snippets, 1);
    sem_acc  = nanstd(snippets, 0, 1) / sqrt(sum(~isnan(snippets(:,1))));

    % Plot
    %subplot(n_dur, 1, d);
    hold on;

    % % SEM shading
    % fill([t_axis, fliplr(t_axis)], ...
    %      [mean_acc + sem_acc, fliplr(mean_acc - sem_acc)], ...
    %      colors(d,:), 'FaceAlpha', 0.3, 'EdgeColor', 'none');

    % Mean trace
    plot(t_axis, mean_acc, 'Color', colors(d,:), 'LineWidth', 1.5, ...
    'DisplayName', sprintf('dur=%.2fs (n=%d)', dur, length(idx_dur)));

    

    xlabel('Temps relatif à la stim (s)');
    ylabel('Accélération (u.a.)');
    %title(sprintf('PETH — durée stim = %.2f s  (n=%d)', dur, length(idx_dur)));
    legend('show', 'Location', 'best');
    
    xlim([-win_pre, win_post]);
    grid on;
    hold off;
end

sgtitle('Acceleration norm PETH across stimulation durations');
set(findall(gcf, '-property', 'FontSize'), 'FontSize', 14);
set(findall(gcf, '-property', 'LineWidth'), 'LineWidth', 1.5);

