#!/usr/bin/env Rscript

args_all <- commandArgs(trailingOnly = FALSE)
script_file <- sub("^--file=", "", grep("^--file=", args_all, value = TRUE)[1])
script_dir <- dirname(normalizePath(script_file))
source(file.path(script_dir, "glmm_utils.R"))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop(
    "Usage: Rscript rq1_glmm.R <analysis.csv> <output_dir> ",
    "[outcome] [verbose_level]\n",
    "Outcome defaults to generation_correct; verbose_level defaults to 1."
  )
}
data_path <- args[[1]]
output_dir <- args[[2]]
outcome <- if (length(args) >= 3) args[[3]] else "generation_correct"
verbose_level <- if (length(args) >= 4) as.integer(args[[4]]) else 1L
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
control <- glmm_control(optimizer_print_every = optimizer_print_every)
progress_message(
  "RQ1 configuration: outcome=", outcome,
  ", optimizer_print_every=", optimizer_print_every,
  ", rows=", nrow(data),
  ", items=", nlevels(data$parallel_id)
)
base_path <- file.path(output_dir, paste0("rq1_base_", outcome, ".rds"))
concordance_path <- file.path(
  output_dir, paste0("rq1_concordance_", outcome, ".rds")
)

if (file.exists(base_path)) {
  progress_message("CHECKPOINT: loading RQ1 base model: ", base_path)
  model_base <- readRDS(base_path)
} else {
  model_base <- timed_fit("RQ1 base model", glmer(
    y ~ question_language + gui_language + dimension + (1 | parallel_id),
    data = data, family = binomial("logit"), control = control, nAGQ = 1,
    verbose = 0L
  ))
  saveRDS(model_base, base_path)
  progress_message("CHECKPOINT SAVED: ", base_path)
}
if (file.exists(concordance_path)) {
  progress_message(
    "CHECKPOINT: loading RQ1 concordance model: ", concordance_path
  )
  model_concordance <- readRDS(concordance_path)
} else {
  model_concordance <- timed_fit("RQ1 concordance model", glmer(
    y ~ question_language + gui_language + dimension + matched_num +
      (1 | parallel_id),
    data = data, family = binomial("logit"), control = control, nAGQ = 1,
    verbose = 0L
  ))
  saveRDS(model_concordance, concordance_path)
  progress_message("CHECKPOINT SAVED: ", concordance_path)
}
write_csv(
  lrt_table(model_base, model_concordance, "matched"),
  file.path(output_dir, paste0("rq1_matched_lrt_", outcome, ".csv"))
)
write_csv(
  fixed_effect_table(model_concordance),
  file.path(output_dir, paste0("rq1_fixed_effects_", outcome, ".csv"))
)
write_csv(
  bind_rows(
    model_diagnostics(model_base, "rq1_base"),
    model_diagnostics(model_concordance, "rq1_concordance")
  ),
  file.path(output_dir, paste0("rq1_diagnostics_", outcome, ".csv"))
)

dim_weights <- dimension_weights(data)
diagonal_grid <- expand_grid(
  question_language = LANGUAGES,
  dimension = DIMENSIONS
) %>%
  mutate(gui_language = question_language, matched_num = 1L) %>%
  coerce_prediction_grid(data) %>%
  left_join(dim_weights, by = "dimension") %>%
  mutate(weight = dimension_weight / length(LANGUAGES))
diagonal_counterfactual <- diagonal_grid %>% mutate(matched_num = 0L)

bonus <- simulate_marginal_probability_contrast(
  model_concordance,
  diagonal_grid,
  diagonal_counterfactual,
  diagonal_grid$weight
) %>%
  mutate(
    outcome = outcome,
    interpretation = paste(
      "Average diagonal-cell probability bonus beyond additive query/GUI",
      "effects, integrated over the fitted item-difficulty distribution"
    )
  )
write_csv(
  bonus,
  file.path(
    output_dir, paste0("rq1_adjusted_concordance_bonus_", outcome, ".csv")
  )
)

cell_grid <- expand_grid(
  question_language = LANGUAGES,
  gui_language = LANGUAGES,
  dimension = DIMENSIONS
) %>%
  mutate(matched_num = as.integer(question_language == gui_language)) %>%
  coerce_prediction_grid(data) %>%
  left_join(dim_weights, by = "dimension") %>%
  mutate(
    adjusted_probability = predict_item_marginal_probability(
      model_concordance, .
    )
  )
adjusted_matrix <- cell_grid %>%
  group_by(question_language, gui_language) %>%
  summarise(
    adjusted_probability = weighted.mean(
      adjusted_probability, dimension_weight
    ),
    .groups = "drop"
  )
write_csv(
  adjusted_matrix,
  file.path(output_dir, paste0("rq1_adjusted_6x6_matrix_", outcome, ".csv"))
)
write_csv(
  adjusted_matrix %>%
    group_by(question_language) %>%
    summarise(adjusted_probability = mean(adjusted_probability), .groups = "drop"),
  file.path(output_dir, paste0("rq1_adjusted_query_means_", outcome, ".csv"))
)
write_csv(
  adjusted_matrix %>%
    group_by(gui_language) %>%
    summarise(adjusted_probability = mean(adjusted_probability), .groups = "drop"),
  file.path(output_dir, paste0("rq1_adjusted_gui_means_", outcome, ".csv"))
)
capture.output(sessionInfo(), file = file.path(output_dir, "rq1_session_info.txt"))
progress_message("RQ1 analysis completed: ", output_dir)
