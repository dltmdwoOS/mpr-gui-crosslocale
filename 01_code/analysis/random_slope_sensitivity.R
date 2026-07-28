#!/usr/bin/env Rscript

args_all <- commandArgs(trailingOnly = FALSE)
script_file <- sub("^--file=", "", grep("^--file=", args_all, value = TRUE)[1])
script_dir <- dirname(normalizePath(script_file))
source(file.path(script_dir, "glmm_utils.R"))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop(
    "Usage: Rscript random_slope_sensitivity.R ",
    "<analysis.csv> <output_dir> [outcome] [standard|fast] [verbose_level]"
  )
}
data_path <- args[[1]]
output_dir <- args[[2]]
outcome <- if (length(args) >= 3) args[[3]] else "generation_correct"
fit_mode <- if (length(args) >= 4) args[[4]] else "standard"
verbose_level <- if (length(args) >= 5) as.integer(args[[5]]) else 1L
if (!fit_mode %in% c("standard", "fast")) {
  stop("Fit mode must be either 'standard' or 'fast'.")
}
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
  fast = fit_mode == "fast",
  optimizer_print_every = optimizer_print_every
)
progress_message(
  "Random-slope configuration: outcome=", outcome,
  ", fit_mode=", fit_mode,
  ", optimizer_print_every=", optimizer_print_every,
  ", rows=", nrow(data),
  ", items=", nlevels(data$parallel_id)
)

# The uncorrelated item-specific matched slope tests whether heterogeneous
# concordance effects materially change the fixed-effect conclusion.
rq1_formula <- y ~ question_language + gui_language + dimension + matched_num +
  (1 + matched_num || parallel_id)
rq2_formula <- y ~ question_language * dimension +
  gui_language * dimension + matched_num * dimension +
  (1 + matched_num || parallel_id)

rq1_path <- file.path(
  output_dir, paste0("rq1_random_slope_", outcome, ".rds")
)
rq2_path <- file.path(
  output_dir, paste0("rq2_random_slope_", outcome, ".rds")
)
rq2_reduced_path <- file.path(
  output_dir,
  paste0("rq2_no_matched_dimension_random_slope_", outcome, ".rds")
)

if (file.exists(rq1_path)) {
  progress_message("CHECKPOINT: loading RQ1 random-slope model")
  rq1 <- readRDS(rq1_path)
} else {
  rq1 <- timed_fit("RQ1 random-slope sensitivity model", glmer(
    rq1_formula, data = data, family = binomial("logit"),
    control = control, nAGQ = 1, verbose = 0L
  ))
  saveRDS(rq1, rq1_path)
  progress_message("CHECKPOINT SAVED: ", rq1_path)
}

if (file.exists(rq2_path)) {
  progress_message("CHECKPOINT: loading RQ2 random-slope model")
  rq2 <- readRDS(rq2_path)
} else {
  rq2 <- timed_fit("RQ2 random-slope sensitivity model", glmer(
    rq2_formula, data = data, family = binomial("logit"),
    control = control, nAGQ = 1, verbose = 0L
  ))
  saveRDS(rq2, rq2_path)
  progress_message("CHECKPOINT SAVED: ", rq2_path)
}

if (file.exists(rq2_reduced_path)) {
  progress_message("CHECKPOINT: loading reduced RQ2 random-slope model")
  rq2_no_matched_dimension <- readRDS(rq2_reduced_path)
} else {
  rq2_no_matched_dimension <- timed_fit(
    "Reduced RQ2 random-slope model: no matched × dimension",
    update(rq2, . ~ . - matched_num:dimension)
  )
  saveRDS(rq2_no_matched_dimension, rq2_reduced_path)
  progress_message("CHECKPOINT SAVED: ", rq2_reduced_path)
}

progress_message("Post-processing random-slope sensitivity results")
write_csv(
  bind_rows(
    fixed_effect_table(rq1) %>% mutate(model = "rq1_random_slope"),
    fixed_effect_table(rq2) %>% mutate(model = "rq2_random_slope")
  ),
  file.path(output_dir, paste0("random_slope_fixed_effects_", outcome, ".csv"))
)
write_csv(
  lrt_table(
    rq2_no_matched_dimension, rq2, "matched_by_dimension_random_slope"
  ),
  file.path(output_dir, paste0("random_slope_matched_lrt_", outcome, ".csv"))
)
write_csv(
  bind_rows(
    model_diagnostics(rq1, "rq1_random_slope"),
    model_diagnostics(rq2, "rq2_random_slope"),
    model_diagnostics(
      rq2_no_matched_dimension, "rq2_no_matched_dimension_random_slope"
    )
  ),
  file.path(output_dir, paste0("random_slope_diagnostics_", outcome, ".csv"))
)
capture.output(
  sessionInfo(), file = file.path(output_dir, "random_slope_session_info.txt")
)
progress_message("Random-slope sensitivity completed: ", output_dir)
