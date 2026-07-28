#!/usr/bin/env Rscript

suppressPackageStartupMessages(library(emmeans))
args_all <- commandArgs(trailingOnly = FALSE)
script_file <- sub("^--file=", "", grep("^--file=", args_all, value = TRUE)[1])
script_dir <- dirname(normalizePath(script_file))
source(file.path(script_dir, "glmm_utils.R"))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop(
    "Usage: Rscript core5_glmm.R <analysis.csv> <output_dir> ",
    "[standard|fast] [verbose_level] [all|rq1]"
  )
}
data_path <- args[[1]]
output_dir <- args[[2]]
fit_mode <- if (length(args) >= 3) args[[3]] else "standard"
verbose_level <- if (length(args) >= 4) as.integer(args[[4]]) else 1L
analysis_scope <- if (length(args) >= 5) args[[5]] else "all"
if (!fit_mode %in% c("standard", "fast")) {
  stop("Fit mode must be either 'standard' or 'fast'.")
}
if (is.na(verbose_level) || verbose_level < 0L) {
  stop("verbose_level must be a non-negative integer.")
}
if (!analysis_scope %in% c("all", "rq1")) {
  stop("Analysis scope must be either 'all' or 'rq1'.")
}
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

CORE_LANGUAGES <- c("en", "zh", "fr", "ru", "ja")
outcome <- "generation_correct"

progress_message("Reading full 6x6 table: ", data_path)
data <- readr::read_csv(data_path, show_col_types = FALSE)
required <- c(
  "parallel_id", "question_language", "gui_language",
  "dimension", "matched", outcome
)
missing <- setdiff(required, names(data))
if (length(missing) > 0L) {
  stop("Missing analysis columns: ", paste(missing, collapse = ", "))
}
data <- data %>%
  filter(
    question_language %in% CORE_LANGUAGES,
    gui_language %in% CORE_LANGUAGES
  ) %>%
  mutate(
    parallel_id = factor(parallel_id),
    question_language = factor(
      question_language, levels = CORE_LANGUAGES
    ),
    gui_language = factor(gui_language, levels = CORE_LANGUAGES),
    dimension = factor(dimension, levels = DIMENSIONS),
    matched_num = to_binary(matched),
    y = to_binary(.data[[outcome]])
  )
expected_matched <- as.integer(
  as.character(data$question_language) == as.character(data$gui_language)
)
if (!all(data$matched_num == expected_matched)) {
  stop("The matched column is inconsistent with the language columns.")
}
if (nrow(data) != 2195L * 25L ||
    any(table(data$parallel_id) != 25L)) {
  stop("Every semantic item must contain exactly the 25 core-language cells.")
}
if (anyDuplicated(data[c(
  "parallel_id", "question_language", "gui_language"
)])) {
  stop("Duplicate core-language cells were found.")
}

optimizer_print_every <- if (verbose_level == 0L) {
  0L
} else if (verbose_level == 1L) {
  500L
} else {
  100L
}
control <- glmm_control(
  fast = fit_mode == "fast",
  optimizer_print_every = optimizer_print_every
)
progress_message(
  "Core-5 configuration: fit_mode=", fit_mode,
  ", analysis_scope=", analysis_scope,
  ", rows=", nrow(data),
  ", items=", nlevels(data$parallel_id),
  ", optimizer_print_every=", optimizer_print_every
)

base_formula <- y ~ question_language + gui_language + dimension +
  (1 | parallel_id)
additive_formula <- update(base_formula, . ~ . + matched_num)
full_formula <- y ~ question_language * dimension +
  gui_language * dimension + matched_num * dimension +
  (1 | parallel_id)

paths <- list(
  base = file.path(output_dir, "core5_rq1_base_generation_correct.rds"),
  additive = file.path(
    output_dir, "core5_rq1_concordance_generation_correct.rds"
  ),
  full = file.path(output_dir, "core5_rq2_full_generation_correct.rds"),
  no_matched_dimension = file.path(
    output_dir, "core5_rq2_no_matched_dimension_generation_correct.rds"
  )
)

fit_or_load <- function(path, label, expression) {
  if (file.exists(path)) {
    progress_message("CHECKPOINT: loading ", label, ": ", path)
    return(readRDS(path))
  }
  model <- timed_fit(label, eval.parent(substitute(expression)))
  saveRDS(model, path)
  progress_message("CHECKPOINT SAVED: ", path)
  model
}

model_base <- fit_or_load(
  paths$base,
  "Core-5 RQ1 base model",
  glmer(
    base_formula, data = data, family = binomial("logit"),
    control = control, nAGQ = 1, verbose = 0L
  )
)
model_additive <- fit_or_load(
  paths$additive,
  "Core-5 RQ1 concordance model",
  glmer(
    additive_formula, data = data, family = binomial("logit"),
    control = control, nAGQ = 1, verbose = 0L
  )
)
progress_message("Post-processing Core-5 RQ1")
readr::write_csv(
  lrt_table(model_base, model_additive, "core5_matched"),
  file.path(output_dir, "core5_rq1_matched_lrt_generation_correct.csv")
)
readr::write_csv(
  fixed_effect_table(model_additive),
  file.path(output_dir, "core5_rq1_fixed_effects_generation_correct.csv")
)

dim_weights <- dimension_weights(data)
diagonal_grid <- tidyr::expand_grid(
  question_language = CORE_LANGUAGES,
  dimension = DIMENSIONS
) %>%
  mutate(gui_language = question_language, matched_num = 1L) %>%
  coerce_prediction_grid(data) %>%
  left_join(dim_weights, by = "dimension") %>%
  mutate(weight = dimension_weight / length(CORE_LANGUAGES))
core5_bonus <- simulate_marginal_probability_contrast(
  model_additive,
  diagonal_grid,
  diagonal_grid %>% mutate(matched_num = 0L),
  diagonal_grid$weight
) %>%
  mutate(
    outcome = outcome,
    contrast = "matched_minus_counterfactual_mismatch"
  )
readr::write_csv(
  core5_bonus,
  file.path(
    output_dir, "core5_rq1_adjusted_concordance_bonus_generation_correct.csv"
  )
)

diagnostics <- bind_rows(
  model_diagnostics(model_base, "core5_rq1_base"),
  model_diagnostics(model_additive, "core5_rq1_concordance")
)

if (analysis_scope == "all") {
  model_full <- fit_or_load(
    paths$full,
    "Core-5 RQ2 full interaction model",
    glmer(
      full_formula, data = data, family = binomial("logit"),
      control = control, nAGQ = 1, verbose = 0L
    )
  )
  model_no_matched_dimension <- fit_or_load(
    paths$no_matched_dimension,
    "Core-5 RQ2 reduced model: no matched x dimension",
    update(
      model_full,
      . ~ . - matched_num:dimension,
      control = control,
      verbose = 0L
    )
  )

  progress_message("Post-processing Core-5 RQ2")
  readr::write_csv(
    lrt_table(
      model_no_matched_dimension,
      model_full,
      "core5_matched_by_dimension"
    ),
    file.path(
      output_dir, "core5_rq2_matched_dimension_lrt_generation_correct.csv"
    )
  )
  dimension_bonuses <- lapply(DIMENSIONS, function(dimension_name) {
    grid <- tibble(
      question_language = CORE_LANGUAGES,
      gui_language = CORE_LANGUAGES,
      dimension = dimension_name,
      matched_num = 1L
    ) %>%
      coerce_prediction_grid(data)
    simulate_marginal_probability_contrast(
      model_full,
      grid,
      grid %>% mutate(matched_num = 0L),
      rep(1 / length(CORE_LANGUAGES), length(CORE_LANGUAGES))
    ) %>%
      mutate(dimension = dimension_name, outcome = outcome)
  }) %>%
    bind_rows() %>%
    dplyr::select(
      dimension, outcome, estimate, conf.low, conf.high, nsim, estimand
    )
  readr::write_csv(
    dimension_bonuses,
    file.path(
      output_dir,
      "core5_rq2_concordance_bonus_by_dimension_generation_correct.csv"
    )
  )
  diagnostics <- bind_rows(
    diagnostics,
    model_diagnostics(model_full, "core5_rq2_full"),
    model_diagnostics(
      model_no_matched_dimension, "core5_rq2_no_matched_dimension"
    )
  )
} else {
  progress_message("Skipping Core-5 RQ2 because analysis_scope=rq1")
}

readr::write_csv(
  diagnostics,
  file.path(output_dir, "core5_diagnostics_generation_correct.csv")
)
capture.output(
  sessionInfo(), file = file.path(output_dir, "core5_session_info.txt")
)
progress_message(
  "Core-5 analysis completed: ", output_dir,
  " (analysis_scope=", analysis_scope, ")"
)
