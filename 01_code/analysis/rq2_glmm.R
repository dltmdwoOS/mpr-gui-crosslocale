#!/usr/bin/env Rscript

suppressPackageStartupMessages(library(emmeans))
args_all <- commandArgs(trailingOnly = FALSE)
script_file <- sub("^--file=", "", grep("^--file=", args_all, value = TRUE)[1])
script_dir <- dirname(normalizePath(script_file))
source(file.path(script_dir, "glmm_utils.R"))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop(
    "Usage: Rscript rq2_glmm.R <analysis.csv> <output_dir> ",
    "[outcome] [standard|fast] [verbose_level]\n",
    "Outcome defaults to generation_correct; fit mode defaults to standard; ",
    "verbose_level defaults to 1."
  )
}
data_path <- args[[1]]
output_dir <- args[[2]]
outcome <- if (length(args) >= 3) args[[3]] else "generation_correct"
fit_mode <- if (length(args) >= 4) args[[4]] else "standard"
if (!fit_mode %in% c("standard", "fast")) {
  stop("Fit mode must be either 'standard' or 'fast'.")
}
fast_mode <- fit_mode == "fast"
verbose_level <- if (length(args) >= 5) as.integer(args[[5]]) else 1L
if (is.na(verbose_level) || verbose_level < 0L) {
  stop("verbose_level must be a non-negative integer.")
}
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

progress_message("Reading and validating analysis data: ", data_path)
data <- prepare_glmm_data(data_path, outcome)
optimizer_print_every <- if (verbose_level == 0L) {
  0L
} else if (verbose_level == 1L) {
  500L
} else {
  100L
}
control <- glmm_control(
  fast = fast_mode,
  optimizer_print_every = optimizer_print_every
)
progress_message(
  "RQ2 configuration: outcome=", outcome,
  ", fit_mode=", fit_mode,
  ", optimizer_print_every=", optimizer_print_every,
  ", rows=", nrow(data),
  ", items=", nlevels(data$parallel_id)
)
additive_path <- file.path(
  output_dir, paste0("rq2_additive_", outcome, ".rds")
)
full_path <- file.path(output_dir, paste0("rq2_full_", outcome, ".rds"))
no_query_path <- file.path(
  output_dir, paste0("rq2_no_query_dimension_", outcome, ".rds")
)
no_gui_path <- file.path(
  output_dir, paste0("rq2_no_gui_dimension_", outcome, ".rds")
)
no_concordance_path <- file.path(
  output_dir, paste0("rq2_no_concordance_dimension_", outcome, ".rds")
)
additive_formula <- y ~ question_language + gui_language + dimension +
  matched_num + (1 | parallel_id)
full_formula <- y ~ question_language * dimension +
  gui_language * dimension + matched_num * dimension +
  (1 | parallel_id)

if (file.exists(additive_path)) {
  progress_message("CHECKPOINT: loading additive model: ", additive_path)
  model_additive <- readRDS(additive_path)
} else {
  model_additive <- timed_fit("RQ2 additive model", glmer(
    additive_formula, data = data, family = binomial("logit"),
    control = control, nAGQ = 1, verbose = 0L
  ))
  saveRDS(model_additive, additive_path)
  progress_message("CHECKPOINT SAVED: ", additive_path)
}
if (file.exists(full_path)) {
  progress_message("CHECKPOINT: loading full model: ", full_path)
  model_full <- readRDS(full_path)
} else {
  model_full <- timed_fit("RQ2 full interaction model", glmer(
    full_formula, data = data, family = binomial("logit"),
    control = control, nAGQ = 1, verbose = 0L
  ))
  saveRDS(model_full, full_path)
  progress_message("CHECKPOINT SAVED: ", full_path)
}
progress_message("Starting three block-reduced models...")
if (file.exists(no_query_path)) {
  progress_message("CHECKPOINT: loading no-query×dimension model")
  model_no_query_dimension <- readRDS(no_query_path)
} else {
  model_no_query_dimension <- timed_fit(
    "Reduced model: no query-language × dimension",
    update(
      model_full,
      . ~ . - question_language:dimension,
      control = control,
      verbose = 0L
    )
  )
  saveRDS(model_no_query_dimension, no_query_path)
  progress_message("CHECKPOINT SAVED: ", no_query_path)
}
if (file.exists(no_gui_path)) {
  progress_message("CHECKPOINT: loading no-GUI×dimension model")
  model_no_gui_dimension <- readRDS(no_gui_path)
} else {
  model_no_gui_dimension <- timed_fit(
    "Reduced model: no GUI-language × dimension",
    update(
      model_full,
      . ~ . - gui_language:dimension,
      control = control,
      verbose = 0L
    )
  )
  saveRDS(model_no_gui_dimension, no_gui_path)
  progress_message("CHECKPOINT SAVED: ", no_gui_path)
}
if (file.exists(no_concordance_path)) {
  progress_message("CHECKPOINT: loading no-matched×dimension model")
  model_no_concordance_dimension <- readRDS(no_concordance_path)
} else {
  model_no_concordance_dimension <- timed_fit(
    "Reduced model: no matched × dimension",
    update(
      model_full,
      . ~ . - matched_num:dimension,
      control = control,
      verbose = 0L
    )
  )
  saveRDS(model_no_concordance_dimension, no_concordance_path)
  progress_message("CHECKPOINT SAVED: ", no_concordance_path)
}

progress_message("Post-processing: omnibus likelihood-ratio tests")
write_csv(
  bind_rows(
    lrt_table(model_additive, model_full, "all_dimension_interactions"),
    lrt_table(
      model_no_query_dimension, model_full, "question_language_by_dimension"
    ),
    lrt_table(
      model_no_gui_dimension, model_full, "gui_language_by_dimension"
    ),
    lrt_table(
      model_no_concordance_dimension, model_full, "matched_by_dimension"
    )
  ),
  file.path(output_dir, paste0("rq2_omnibus_lrt_", outcome, ".csv"))
)
progress_message("Post-processing: fixed effects and diagnostics")
write_csv(
  fixed_effect_table(model_full),
  file.path(output_dir, paste0("rq2_fixed_effects_", outcome, ".csv"))
)
write_csv(
  bind_rows(
    model_diagnostics(model_additive, "rq2_additive"),
    model_diagnostics(model_full, "rq2_full"),
    model_diagnostics(model_no_query_dimension, "rq2_no_query_dimension"),
    model_diagnostics(model_no_gui_dimension, "rq2_no_gui_dimension"),
    model_diagnostics(
      model_no_concordance_dimension, "rq2_no_concordance_dimension"
    )
  ),
  file.path(output_dir, paste0("rq2_diagnostics_", outcome, ".csv"))
)

matched_trends_grid <- emmeans::emtrends(
  model_full,
  specs = ~ dimension,
  var = "matched_num"
)
matched_trends <- as.data.frame(
  summary(matched_trends_grid, infer = c(TRUE, TRUE))
) %>%
  mutate(
    p_value_holm = p.adjust(p.value, method = "holm"),
    odds_ratio = exp(matched_num.trend),
    odds_ratio_low = exp(asymp.LCL),
    odds_ratio_high = exp(asymp.UCL)
  )
write_csv(
  matched_trends,
  file.path(
    output_dir, paste0("rq2_matched_trends_by_dimension_", outcome, ".csv")
  )
)

dimension_bonuses <- lapply(DIMENSIONS, function(dimension_name) {
  progress_message("Post-processing probability contrast: ", dimension_name)
  matched_grid <- tibble(
    question_language = LANGUAGES,
    gui_language = LANGUAGES,
    dimension = dimension_name,
    matched_num = 1L
  ) %>%
    coerce_prediction_grid(data)
  simulate_marginal_probability_contrast(
    model_full,
    matched_grid,
    matched_grid %>% mutate(matched_num = 0L),
    rep(1 / length(LANGUAGES), length(LANGUAGES))
  ) %>%
    mutate(dimension = dimension_name, outcome = outcome)
}) %>%
  bind_rows() %>%
  dplyr::select(
    dimension, outcome, estimate, conf.low, conf.high, nsim, estimand
  )
write_csv(
  dimension_bonuses,
  file.path(
    output_dir, paste0("rq2_concordance_bonus_by_dimension_", outcome, ".csv")
  )
)

dimension_cell_grid <- expand_grid(
  dimension = DIMENSIONS,
  question_language = LANGUAGES,
  gui_language = LANGUAGES
) %>%
  mutate(matched_num = as.integer(question_language == gui_language)) %>%
  coerce_prediction_grid(data) %>%
  mutate(
    adjusted_probability = predict_item_marginal_probability(model_full, .)
  )
write_csv(
  dimension_cell_grid,
  file.path(
    output_dir, paste0("rq2_adjusted_dimension_matrices_", outcome, ".csv")
  )
)
write_csv(
  dimension_cell_grid %>%
    group_by(dimension, question_language) %>%
    summarise(adjusted_probability = mean(adjusted_probability), .groups = "drop"),
  file.path(
    output_dir, paste0("rq2_adjusted_query_profiles_", outcome, ".csv")
  )
)
write_csv(
  dimension_cell_grid %>%
    group_by(dimension, gui_language) %>%
    summarise(adjusted_probability = mean(adjusted_probability), .groups = "drop"),
  file.path(
    output_dir, paste0("rq2_adjusted_gui_profiles_", outcome, ".csv")
  )
)
capture.output(sessionInfo(), file = file.path(output_dir, "rq2_session_info.txt"))
progress_message("RQ2 analysis completed: ", output_dir)
