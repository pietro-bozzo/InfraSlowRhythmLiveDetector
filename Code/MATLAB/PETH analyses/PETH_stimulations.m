% =========================================================================
% PETH — Peri-Event Time Histogram around stimulations
%
% Objective:
%   For each stimulation type (A, B, C, D):
%     - PETH 1: Acceleration (baseline-corrected [-2n,-n], individual trials)
%     - PETH 2: LFP ch137 (individual trials)
%     - PETH 3: Mean |LFP| across channels 0-63 (mean + SEM)
%
% By Nathan Mimouni, 2026
% =========================================================================

%% =========================================================================
% PARAMETERS
% =========================================================================

session = "/mnt/hubel-data-149/Lumos_Rat013/2026-06-11_11-21-30/Record Node 131/experiment1/recording1/continuous/Rat013_11062026/Rat013_11062026.xml";

stim_filename = '/mnt/hubel-data-149/Lumos_Rat013/2026-06-11_11-21-30/STIM_and_TIMINGS/stim_20260611_112020.csv';

acc_channels    = [128 129 130];
lfp_channel     = 137;
mua_channels    = 0:63;

n_sec           = 1;     % half-window for display (s)
start_sec_decay = 0;     % temporal offset (adjust to your session)



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

t_first_stim = stim_starts(1);

% Charger ch137 autour de cette stim (fenêtre large)
t_calib_win = [t_first_stim - 0.5,  t_first_stim + 0.5];
lfp_calib   = GetWidebandData(lfp_channel, 'intervals', t_calib_win);
t_calib     = lfp_calib(:, 1);
sig_calib   = lfp_calib(:, 2);

% Détecter le début du pic : premier passage au-dessus de 10% du max
threshold   = 0.1 * max(sig_calib);
idx_peak    = find(sig_calib > threshold, 1, 'first');
t_true_stim = t_calib(idx_peak);

% Décalage = temps réel du pic - temps attendu (t_first_stim)
start_sec_decay = t_true_stim - t_first_stim;
fprintf('Décalage détecté : %.4f s\n', start_sec_decay);

% Appliquer le décalage
stim_starts = stim_starts + start_sec_decay;
stim_ends   = stim_ends   + start_sec_decay;

stim_durations = stim_ends - stim_starts;

block_types = unique(stim_blocks);

%% =========================================================================
% SESSION SETUP
% =========================================================================

SetCurrentSession(session);

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

    % Full window [-2*n_sec, +n_sec] for accelerometer (includes baseline)
    t_win_full_ref = [t_starts(1) - 2*n_sec,  t_starts(1) + n_sec];
    tmp_full       = GetWidebandData(acc_channels(1), 'intervals', t_win_full_ref);
    n_samples_full = size(tmp_full, 1);
    t_rel_full     = linspace(-2*n_sec, n_sec, n_samples_full);

    % Baseline mask: [-2*n_sec, -n_sec]
    idx_baseline_mask = t_rel_full < -n_sec;

    % Analysis window [-n_sec, +n_sec] for LFP and MUA
    t_win_ref  = [t_starts(1) - n_sec,  t_starts(1) + n_sec];
    tmp_ref    = GetWidebandData(acc_channels(1), 'intervals', t_win_ref);
    n_samples  = size(tmp_ref, 1);
    t_rel      = linspace(-n_sec, n_sec, n_samples);

    % Storage
    acc_mat = nan(n_samples, n_events);
    lfp_mat = nan(n_samples, n_events);
    mua_mat = nan(n_samples, n_events);

    % -----------------------------------------------------------------------
    % LOAD DATA AROUND EACH STIM
    % -----------------------------------------------------------------------

    for ev = 1:n_events

        t_win_full = [t_starts(ev) - 2*n_sec,  t_starts(ev) + n_sec];
        t_win      = [t_starts(ev) - n_sec,     t_starts(ev) + n_sec];

        % --- Acceleration (baseline-corrected) ---
        try
            a1 = GetWidebandData(acc_channels(1), 'intervals', t_win_full);
            a2 = GetWidebandData(acc_channels(2), 'intervals', t_win_full);
            a3 = GetWidebandData(acc_channels(3), 'intervals', t_win_full);
            acc_full_raw = sqrt(a1(:,2).^2 + a2(:,2).^2 + a3(:,2).^2) * 0.008;
            smooth_win = round(0.5 * fs);  % 0.5s, ajustable
            acc_full = movmean(acc_full_raw, smooth_win);
            if numel(acc_full) == n_samples_full
                baseline_val  = mean(acc_full(idx_baseline_mask));
                acc_corrected = acc_full(~idx_baseline_mask) - baseline_val;
                acc_mat(:, ev) = acc_corrected(1:n_samples);  % force exact size
            end
        catch e
            warning('Acc load failed for event %d: %s', ev, e.message);
        end

        % --- LFP channel 137 ---
        try
            lfp_tmp = GetWidebandData(lfp_channel, 'intervals', t_win);
            if size(lfp_tmp, 1) == n_samples
                lfp_mat(:, ev) = lfp_tmp(:, 2);
            end
        catch e
            warning('LFP load failed for event %d: %s', ev, e.message);
        end

        % --- MUA: mean |LFP| across channels 0-63 ---
        try
            mua_sum  = zeros(n_samples, 1);
            n_loaded = 0;
            for ch = mua_channels
                tmp_ch = GetWidebandData(ch, 'intervals', t_win);
                if size(tmp_ch, 1) == n_samples
                    mua_sum  = mua_sum + abs(tmp_ch(:, 2));
                    n_loaded = n_loaded + 1;
                end
            end
            if n_loaded > 0
                mua_mat(:, ev) = mua_sum / n_loaded;
            end
        catch e
            warning('MUA load failed for event %d: %s', ev, e.message);
        end

    end  % end event loop

    % -----------------------------------------------------------------------
    % MUA mean + SEM
    % -----------------------------------------------------------------------

    mua_mean = nanmean(mua_mat, 2);
    mua_sem  = nanstd(mua_mat, 0, 2) ./ sqrt(sum(~isnan(mua_mat), 2));

    % -----------------------------------------------------------------------
    % FIGURE — created once, no close/reopen
    % -----------------------------------------------------------------------

    col_mua  = [0.90 0.45 0.20];
    col_stim = [1.00 0.75 0.00];
    col_sem  = 0.3;
    cmap_acc = cool(max(n_events, 1));
    cmap_lfp = summer(max(n_events, 1));

    figure;

    %figure('Name', sprintf('PETH — Block %s', block_label), ...
           %'NumberTitle', 'off', ...
           %'Position', [100 100 900 900]);

    % =====================================================================
    % SUBPLOT 1-2 : Acceleration — baseline-corrected, individual trials
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
    title(ax1, sprintf('Block %s — Acceleration  [baseline = [-%ds, -%ds]]  (n=%d stims)', ...
          block_label, 2*n_sec, n_sec, n_events));
    legend(ax1, 'show', 'Location', 'northwest', 'NumColumns', 2);
    grid(ax1, 'on');
    box(ax1, 'off');
    xticklabels(ax1, {});

    % =====================================================================
    % SUBPLOT 3 : LFP ch137 — individual trials
    % =====================================================================

    ax2 = subplot(4, 1, 3);
    hold(ax2, 'on');

    for ev = 1:n_events
        if any(~isnan(lfp_mat(:, ev)))
            plot(ax2, t_rel, lfp_mat(:, ev), ...
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
    ylabel(ax2, sprintf('LFP ch%d (µV)', lfp_channel));
    title(ax2, sprintf('Block %s — LFP ch%d  (n=%d stims)', ...
          block_label, lfp_channel, n_events));
    legend(ax2, 'show', 'Location', 'northwest', 'NumColumns', 2);
    grid(ax2, 'on');
    box(ax2, 'off');
    xticklabels(ax2, {});

    % =====================================================================
    % SUBPLOT 4 : Mean MUA — mean + SEM
    % =====================================================================

    ax3 = subplot(4, 1, 4);
    hold(ax3, 'on');

    t_fill = [t_rel(:); flipud(t_rel(:))];
y_fill = [mua_mean + mua_sem; flipud(mua_mean - mua_sem)];
fill(ax3, t_fill, y_fill, ...
     col_mua, 'FaceAlpha', col_sem, 'EdgeColor', 'none', 'HandleVisibility', 'off');

    plot(ax3, t_rel, mua_mean, 'Color', col_mua, 'LineWidth', 1.8, ...
         'DisplayName', 'Mean |LFP| ch0–63');

    ylims3 = ylim(ax3);
    patch(ax3, [0, mean_dur, mean_dur, 0], ...
          [ylims3(1), ylims3(1), ylims3(2), ylims3(2)], ...
          col_stim, 'FaceAlpha', 0.20, 'EdgeColor', 'none', 'HandleVisibility', 'off');
    xline(ax3, 0, '--k', 'LineWidth', 1.5, 'HandleVisibility', 'off');

    xlim(ax3, [-n_sec n_sec]);
    xlabel(ax3, 'Time relative to stim onset (s)');
    ylabel(ax3, 'Mean |LFP| (µV)');
    title(ax3, sprintf('Block %s — Mean firing rate proxy  (ch 0–63)', block_label));
    legend(ax3, 'show', 'Location', 'northwest');
    grid(ax3, 'on');
    box(ax3, 'off');

    sgtitle(sprintf('PETH — Block %s  |  window = ±%d s  |  baseline = [-%ds, -%ds]', ...
            block_label, n_sec, 2*n_sec, n_sec), ...
            'FontSize', 14, 'FontWeight', 'bold');

end  % end block loop

