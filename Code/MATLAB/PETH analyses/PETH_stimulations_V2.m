% =========================================================================
% PETH — Peri-Event Time Histogram around stimulations
%
% Objective:
%   For each stimulation type (A, B, C, D):
%     - PETH 1: Acceleration (baseline-corrected [-2n,-n], individual trials)
%     - PETH 2: LFP ch137 (individual trials)
%     - PETH 3: MUA — STD thresholding (Open Ephys method), mean spike rate
%
% By Nathan Mimouni, 2026
% =========================================================================

%% =========================================================================
% PARAMETERS
% =========================================================================

session = "/mnt/hubel-data-149/Lumos_Rat013/2026-06-11_11-21-30/Record Node 131/experiment1/recording1/continuous/Rat013_11062026/Rat013_11062026.xml";

stim_filename = '/mnt/hubel-data-149/Lumos_Rat013/2026-06-11_11-21-30/STIM_and_TIMINGS/stim_20260611_112020.csv';

acc_channels    = [128 129 130];
lfp_channel     = 137;       % channel of the stimulation pattern
mua_channels    = 0:63;      % channels for MUA (32 excluded below)

n_sec           = 1;         % half-window for display (s)
dc_margin       = 2;         % extra margin each side for robust DC estimation (s)
butter_fc       = 15;        % Butterworth lowpass cutoff (Hz) for acceleration
start_sec_decay = 0;         % temporal offset CSV → session (auto-computed below)

% MUA spike detection parameters
std_factor       = 4;        % threshold = -std_factor * sliding_std
refractory_ms    = 1.0;      % refractory period (ms)
std_win_samples  = 200;      % sliding STD window (samples, at fs_wide)

%% =========================================================================
% SESSION SETUP — read fs from xml
% =========================================================================

SetCurrentSession(session);
s        = GetCurrentSession;
fs_wide  = s.wideband;            % 20000 Hz
fs_lfp   = s.lfp;                 % 1250 Hz
ds_factor = round(fs_wide / fs_lfp);

refractory_samples = round(refractory_ms * 1e-3 * fs_wide);

% Butterworth lowpass filter for acceleration (zero-phase via filtfilt)
[b_but, a_but] = butter(4, butter_fc / (fs_wide/2), 'low');

% Bandpass filter for MUA spike detection 300-6000 Hz
% Computed ONCE here, reused for every channel and every event
[b_mua, a_mua] = butter(4, [300 6000] / (fs_wide/2), 'bandpass');

%% =========================================================================
% LOAD AND PARSE STIMULATION FILE
% =========================================================================

stim_table = readtable(stim_filename);

stim_start_rows = strcmp(stim_table.event, 'STIM_START');
stim_starts_raw = stim_table.t_pc_ms(stim_start_rows) / 1000;
stim_blocks     = stim_table.block(stim_start_rows);

stim_end_rows = strcmp(stim_table.event, 'STIM_END');
stim_ends_raw = stim_table.t_pc_ms(stim_end_rows) / 1000;

n_stim          = min(numel(stim_starts_raw), numel(stim_ends_raw));
stim_starts_raw = stim_starts_raw(1:n_stim);
stim_ends_raw   = stim_ends_raw(1:n_stim);
stim_blocks     = stim_blocks(1:n_stim);

stim_starts    = stim_starts_raw + start_sec_decay;
stim_ends      = stim_ends_raw   + start_sec_decay;

% Auto-detect temporal offset via first peak on lfp_channel
t_first_stim = stim_starts(1);
t_calib_win  = [t_first_stim - 1, t_first_stim + 1];
lfp_calib    = GetWidebandData(lfp_channel, 'intervals', t_calib_win);
t_calib      = lfp_calib(:, 1);
sig_calib    = lfp_calib(:, 2);
threshold    = 0.1 * max(sig_calib);
idx_peak     = find(sig_calib > threshold, 1, 'first');
t_true_stim  = t_calib(idx_peak);
start_sec_decay = t_true_stim - t_first_stim;
fprintf('Décalage détecté : %.4f s\n', start_sec_decay);

stim_starts = stim_starts + start_sec_decay;
stim_ends   = stim_ends   + start_sec_decay;
stim_durations = stim_ends - stim_starts;

block_types = unique(stim_blocks);

%% =========================================================================
% LOOP OVER BLOCK TYPES
% =========================================================================

for b = 1:numel(block_types)

    block_label = block_types{b};
    idx_block   = strcmp(stim_blocks, block_label);

    t_starts    = stim_starts(idx_block);
    t_ends      = stim_ends(idx_block);
    t_durations = stim_durations(idx_block);
    n_events    = numel(t_starts);
    mean_dur    = mean(t_durations);

    fprintf('Block %s : %d stimulations\n', block_label, n_events);

    % -----------------------------------------------------------------------
    % MEASURE SAMPLE COUNTS FROM FIRST STIM
    % -----------------------------------------------------------------------

    % Acc: full window [-2n-dc_margin, +n+dc_margin] at fs_wide
    t_win_acc_ref  = [t_starts(1) - 2*n_sec - dc_margin, ...
                      t_starts(1) + n_sec   + dc_margin];
    margin_samples_lfp = round(dc_margin * fs_lfp);

    n_samples_baseline = round(n_sec   * fs_lfp);   % width of [-2n,-n] = n
    n_samples_display  = round(2*n_sec * fs_lfp);   % width of [-n,+n]  = 2n
    n_samples_full_lfp = n_samples_baseline + n_samples_display;

    t_rel_full = linspace(-2*n_sec, n_sec,  n_samples_full_lfp);
    t_rel      = linspace(-n_sec,   n_sec,  n_samples_display);

    idx_baseline_mask = t_rel_full < -n_sec;

    % LFP/MUA: window [-n, +n] at fs_wide
    t_win_lfp_ref = [t_starts(1) - n_sec, t_starts(1) + n_sec];
    tmp_lfp_ref   = GetWidebandData(lfp_channel, 'intervals', t_win_lfp_ref);
    n_samples_lfp = size(tmp_lfp_ref, 1);   % at fs_wide
    t_rel_lfp     = linspace(-n_sec, n_sec, n_samples_lfp);

    % Storage
    acc_mat = nan(n_samples_display, n_events);
    lfp_mat = nan(n_samples_lfp,     n_events);
    mua_mat = nan(n_samples_lfp,     n_events);  % spike rate per sample (Hz proxy)

    % -----------------------------------------------------------------------
    % LOAD DATA AROUND EACH STIM
    % -----------------------------------------------------------------------

    for ev = 1:n_events

        t_win_acc = [t_starts(ev) - 2*n_sec - dc_margin, ...
                     t_starts(ev) + n_sec   + dc_margin];
        t_win_lfp = [t_starts(ev) - n_sec, t_starts(ev) + n_sec];

        % --- Acceleration ---
        try
            a1 = GetWidebandData(acc_channels(1), 'intervals', t_win_acc);
            a2 = GetWidebandData(acc_channels(2), 'intervals', t_win_acc);
            a3 = GetWidebandData(acc_channels(3), 'intervals', t_win_acc);

            min_len = min([size(a1,1), size(a2,1), size(a3,1)]);
            if min_len < 2, continue; end
            a1 = a1(1:min_len,:);
            a2 = a2(1:min_len,:);
            a3 = a3(1:min_len,:);

            acc_norm_raw = sqrt(a1(:,2).^2 + a2(:,2).^2 + a3(:,2).^2);
            acc_smooth   = filtfilt(b_but, a_but, double(acc_norm_raw));
            acc_ds       = downsample(acc_smooth, ds_factor);
            acc_ds       = acc_ds(margin_samples_lfp+1 : end-margin_samples_lfp);

            if length(acc_ds) < n_samples_full_lfp, continue; end
            acc_ds = acc_ds(1:n_samples_full_lfp);

            baseline_val   = mean(acc_ds(idx_baseline_mask));
            acc_display    = acc_ds(~idx_baseline_mask);
            acc_mat(:, ev) = acc_display(1:n_samples_display) - baseline_val;

        catch e
            warning('Acc load failed for event %d: %s', ev, e.message);
        end

        % --- LFP channel (raw wideband) ---
        try
            lfp_tmp = GetWidebandData(lfp_channel, 'intervals', t_win_lfp);
            if size(lfp_tmp, 1) == n_samples_lfp
                lfp_mat(:, ev) = lfp_tmp(:, 2);
            end
        catch e
            warning('LFP load failed for event %d: %s', ev, e.message);
        end

        % --- MUA: STD thresholding (Open Ephys method) ---
        % For each channel:
        %   1) Bandpass 300-6000 Hz
        %   2) Sliding STD threshold = -std_factor * movstd(signal, 200)
        %   3) Detect negative crossings → spike timestamps
        %   4) Apply refractory period
        %   5) Convert to binary spike train at fs_wide
        % Then average spike trains across channels → mean spike rate proxy
        try
            spike_train_sum = zeros(n_samples_lfp, 1);
            n_loaded = 0;

            valid_mua_channels = mua_channels(mua_channels ~= 32);

            for ch = valid_mua_channels

                tmp_ch = GetWidebandData(ch, 'intervals', t_win_lfp);
                if size(tmp_ch, 1) ~= n_samples_lfp, continue; end

                % 1) Bandpass filter
                sig_bp = filtfilt(b_mua, a_mua, double(tmp_ch(:, 2)));

                % 2) Sliding STD threshold (negative, downward deflection)
                std_sliding = movstd(sig_bp, std_win_samples);
                thresh_vec  = -std_factor * std_sliding;

                % 3) Detect negative crossings: signal drops below local threshold
                below     = sig_bp < thresh_vec;
                crossings = find(diff(below) == 1) + 1;

                % 4) Refractory period: remove spikes within 1ms of previous
                if ~isempty(crossings)
                    valid    = true(size(crossings));
                    last_idx = crossings(1);
                    for i = 2:numel(crossings)
                        if crossings(i) - last_idx < refractory_samples
                            valid(i) = false;
                        else
                            last_idx = crossings(i);
                        end
                    end
                    crossings = crossings(valid);
                end

                % 5) Binary spike train at fs_wide resolution
                spike_train = zeros(n_samples_lfp, 1);
                valid_idx   = crossings(crossings >= 1 & crossings <= n_samples_lfp);
                spike_train(valid_idx) = 1;

                spike_train_sum = spike_train_sum + spike_train;
                n_loaded = n_loaded + 1;

            end  % end channel loop

            if n_loaded > 0
                % Mean spike train across channels (spikes per sample per channel)
                % Multiply by fs_wide to express as instantaneous rate in Hz
                mua_mat(:, ev) = (spike_train_sum / n_loaded) * fs_wide;
            end

        catch e
            warning('MUA load failed for event %d: %s', ev, e.message);
        end

    end  % end event loop

    % -----------------------------------------------------------------------
    % MUA mean + SEM across events
    % -----------------------------------------------------------------------

    mua_mean = nanmean(mua_mat, 2);
    mua_sem  = nanstd(mua_mat, 0, 2) ./ sqrt(sum(~isnan(mua_mat), 2));

    % -----------------------------------------------------------------------
    % FIGURE
    % -----------------------------------------------------------------------

    col_mua  = [0.90 0.45 0.20];
    col_stim = [1.00 0.75 0.00];
    col_sem  = 0.3;
    cmap_acc = cool(max(n_events, 1));
    cmap_lfp = summer(max(n_events, 1));

    figure;

    % =====================================================================
    % SUBPLOT 1-2 : Acceleration
    % =====================================================================

    ax1 = subplot(4, 1, [1 2]);
    hold(ax1, 'on');

    for ev = 1:n_events
        if any(~isnan(acc_mat(:, ev)))
            plot(ax1, t_rel, acc_mat(:, ev), ...
                 'Color', [cmap_acc(ev,:), 0.75], ...
                 'LineWidth', 1.2, ...
                 'DisplayName', sprintf('Stim %d', ev));
        end
    end

    yline(ax1, 0, '-', 'Color', [0.5 0.5 0.5], 'LineWidth', 0.8, ...
          'HandleVisibility', 'off');
    ylims1 = ylim(ax1);
    patch(ax1, [0, mean_dur, mean_dur, 0], ...
          [ylims1(1), ylims1(1), ylims1(2), ylims1(2)], ...
          col_stim, 'FaceAlpha', 0.20, 'EdgeColor', 'none', 'HandleVisibility', 'off');
    xline(ax1, 0, '--k', 'LineWidth', 1.5, 'HandleVisibility', 'off');

    xlim(ax1, [-n_sec n_sec]);
    ylabel(ax1, '\DeltaAcceleration (a.u.)');
    title(ax1, sprintf('Block %s — Acceleration  [baseline=[-%ds,-%ds]]  (n=%d stims)', ...
          block_label, 2*n_sec, n_sec, n_events));
    legend(ax1, 'show', 'Location', 'northwest', 'NumColumns', 2);
    grid(ax1, 'on'); box(ax1, 'off'); xticklabels(ax1, {});

    % =====================================================================
    % SUBPLOT 3 : LFP ch137
    % =====================================================================

    ax2 = subplot(4, 1, 3);
    hold(ax2, 'on');

    for ev = 1:n_events
        if any(~isnan(lfp_mat(:, ev)))
            plot(ax2, t_rel_lfp, lfp_mat(:, ev), ...
                 'Color', [cmap_lfp(ev,:), 0.75], ...
                 'LineWidth', 1.2, ...
                 'DisplayName', sprintf('Stim %d', ev));
        end
    end

    ylims2 = ylim(ax2);
    patch(ax2, [0, mean_dur, mean_dur, 0], ...
          [ylims2(1), ylims2(1), ylims2(2), ylims2(2)], ...
          col_stim, 'FaceAlpha', 0.20, 'EdgeColor', 'none', 'HandleVisibility', 'off');
    xline(ax2, 0, '--k', 'LineWidth', 1.5, 'HandleVisibility', 'off');

    xlim(ax2, [-n_sec n_sec]);
    ylabel(ax2, sprintf('LFP ch%d (a.u.)', lfp_channel));
    title(ax2, sprintf('Block %s — LFP ch%d  (n=%d stims)', ...
          block_label, lfp_channel, n_events));
    legend(ax2, 'show', 'Location', 'northwest', 'NumColumns', 2);
    grid(ax2, 'on'); box(ax2, 'off'); xticklabels(ax2, {});

    % =====================================================================
    % SUBPLOT 4 : MUA — mean spike rate (mean + SEM across events)
    % =====================================================================

    ax3 = subplot(4, 1, 4);
    hold(ax3, 'on');

    t_fill = [t_rel_lfp(:); flipud(t_rel_lfp(:))];
    y_fill = [mua_mean + mua_sem; flipud(mua_mean - mua_sem)];
    fill(ax3, t_fill, y_fill, ...
         col_mua, 'FaceAlpha', col_sem, 'EdgeColor', 'none', 'HandleVisibility', 'off');

    plot(ax3, t_rel_lfp, mua_mean, 'Color', col_mua, 'LineWidth', 1.8, ...
         'DisplayName', 'Mean spike rate ch0–63');

    ylims3 = ylim(ax3);
    patch(ax3, [0, mean_dur, mean_dur, 0], ...
          [ylims3(1), ylims3(1), ylims3(2), ylims3(2)], ...
          col_stim, 'FaceAlpha', 0.20, 'EdgeColor', 'none', 'HandleVisibility', 'off');
    xline(ax3, 0, '--k', 'LineWidth', 1.5, 'HandleVisibility', 'off');

    xlim(ax3, [-n_sec n_sec]);
    xlabel(ax3, 'Time relative to stim onset (s)');
    ylabel(ax3, 'Mean spike rate (Hz)');
    title(ax3, sprintf('Block %s — MUA spike rate  (ch 0–63, excl. 32 | STD×%d | refrac=%.0fms)', ...
          block_label, std_factor, refractory_ms));
    legend(ax3, 'show', 'Location', 'northwest');
    grid(ax3, 'on'); box(ax3, 'off');

    sgtitle(sprintf('PETH — Block %s  |  window = ±%d s  |  baseline = [-%ds, -%ds]', ...
            block_label, n_sec, 2*n_sec, n_sec), ...
            'FontSize', 14, 'FontWeight', 'bold');

end  % end block loop