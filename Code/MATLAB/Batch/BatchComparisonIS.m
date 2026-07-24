function stats_list = BatchComparisonIS(sessions, filenames, startrecs)


[lessessions,extra_args] = readBatchFile(sessions);
n_sessions = length(lessessions);
args = {filenames, startrecs};

[F_score, TP_pct, FP_pct, FN_pct] = runBatch(sessions, @CriticalExponents, args);

F_score = reverseCellStruct(F_score);
TP_pct = reverseCellStruct(TP_pct);
FP_pct = reverseCellStruct(FP_pct);
FN_pct = reverseCellStruct(FN_pct);

stats_list = {F_score, TP_pct, FP_pct, FN_pct};