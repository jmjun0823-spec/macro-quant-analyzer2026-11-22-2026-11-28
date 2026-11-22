suppressPackageStartupMessages({
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
json_path <- if (length(args) >= 1) args[1] else "output/verification_results.json"

if (!file.exists(json_path)) {
  stop(paste("JSON report not found:", json_path))
}

res <- fromJSON(json_path)

tg_vol <- res$`2_Thanksgiving_Calendar_Anomaly`$yearly_series$vol_change_pct
if (!is.null(tg_vol) && length(tg_vol) > 2) {
  r_ttest <- t.test(tg_vol, mu = 0)
  cat(sprintf(
    "[R Cross-Check] Thanksgiving Vol Change Mean: %.2f%% (95%% CI: [%.2f%%, %.2f%%], t = %.2f, p = %.4e)\n",
    mean(tg_vol),
    r_ttest$conf.int[1],
    r_ttest$conf.int[2],
    r_ttest$statistic,
    r_ttest$p.value
  ))
}

ye_spread <- res$`3_YearEnd_BookClosing_and_Dividend_Rotation`$yearly_index_series$spread_pct
if (!is.null(ye_spread) && length(ye_spread) > 2) {
  ye_ttest <- t.test(ye_spread, mu = 0)
  cat(sprintf(
    "[R Cross-Check] Year-End KOSPI-KOSDAQ Spread Mean: %.2f%%p (95%% CI: [%.2f%%p, %.2f%%p], p = %.4f)\n",
    mean(ye_spread),
    ye_ttest$conf.int[1],
    ye_ttest$conf.int[2],
    ye_ttest$p.value
  ))
}
