#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(tibble)
  library(tidyr)
})

args_all <- commandArgs(trailingOnly = FALSE)
script_file <- sub("^--file=", "", grep("^--file=", args_all, value = TRUE)[1])
script_dir <- dirname(normalizePath(script_file))
source(file.path(script_dir, "glmm_utils.R"))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 3L) {
  stop(
    "Usage: Rscript rel_nllb_oracle_analysis.R <glmm.csv> ",
    "<integrated_annotation.csv> <output_dir> [bootstrap_reps] [seed]"
  )
}

data_path <- args[[1]]
annotation_path <- args[[2]]
output_dir <- args[[3]]
bootstrap_reps <- if (length(args) >= 4L) as.integer(args[[4]]) else 2000L
seed <- if (length(args) >= 5L) as.integer(args[[5]]) else 42L

if (is.na(bootstrap_reps) || bootstrap_reps < 100L) {
  stop("bootstrap_reps must be an integer >= 100.")
}
if (is.na(seed)) stop("seed must be an integer.")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

EXPECTED_ITEMS <- 366L
EXPECTED_ROWS <- EXPECTED_ITEMS * 36L
EXPECTED_TARGET_UNITS <- EXPECTED_ITEMS * 6L
DEPENDENCY_LEVELS <- c("independent", "dependent")

progress_message("Reading frozen result table: ", data_path)
data <- prepare_glmm_data(data_path, "generation_correct") %>%
  filter(as.character(dimension) == "rel") %>%
  mutate(
    parallel_id = as.character(parallel_id),
    source_question_language = as.character(question_language),
    gui_language = as.character(gui_language)
  )

if (nrow(data) != EXPECTED_ROWS || n_distinct(data$parallel_id) != EXPECTED_ITEMS) {
  stop("Oracle analysis requires 366 REL items x 36 language cells.")
}

annotation <- read_csv(annotation_path, show_col_types = FALSE) %>%
  transmute(
    parallel_id = as.character(parallel_id),
    text_dependency = tolower(trimws(as.character(text_dependency)))
  )
if (
  nrow(annotation) != EXPECTED_ITEMS ||
  anyDuplicated(annotation$parallel_id) ||
  !setequal(unique(annotation$text_dependency), DEPENDENCY_LEVELS)
) {
  stop("Final REL annotation is not the frozen 366-item adjudicated table.")
}
annotation_counts <- table(annotation$text_dependency)
if (
  unname(annotation_counts[["dependent"]]) != 302L ||
  unname(annotation_counts[["independent"]]) != 64L
) {
  stop("Final REL annotation counts must be dependent=302 and independent=64.")
}
if (!setequal(data$parallel_id, annotation$parallel_id)) {
  stop("REL result and annotation item universes differ.")
}

data <- data %>%
  left_join(annotation, by = "parallel_id")

# One target-anchored unit averages the five original source-language
# mismatches and compares them with the target human-parallel matched endpoint.
target_units <- data %>%
  group_by(parallel_id, gui_language, text_dependency) %>%
  summarise(
    original_mismatch_accuracy = mean(y[source_question_language != gui_language]),
    original_source_count = sum(source_question_language != gui_language),
    target_human_parallel_accuracy = y[source_question_language == gui_language][[1]],
    target_human_parallel_count = sum(source_question_language == gui_language),
    .groups = "drop"
  ) %>%
  mutate(
    oracle_recoverable_gap = (
      target_human_parallel_accuracy - original_mismatch_accuracy
    ),
    target_human_parallel_endpoint_id = paste0(
      parallel_id, "::", gui_language
    )
  )

if (nrow(target_units) != EXPECTED_TARGET_UNITS) {
  stop("Target-anchored oracle table must contain exactly 2,196 units.")
}
if (
  any(target_units$original_source_count != 5L) ||
  any(target_units$target_human_parallel_count != 1L)
) {
  stop("Each target unit must contain five mismatches and one target endpoint.")
}

write_csv(
  target_units,
  file.path(output_dir, "rq4_target_human_parallel_units.csv")
)

item_means <- target_units %>%
  group_by(parallel_id, text_dependency) %>%
  summarise(
    original_mismatch_accuracy = mean(original_mismatch_accuracy),
    target_human_parallel_accuracy = mean(target_human_parallel_accuracy),
    oracle_recoverable_gap = mean(oracle_recoverable_gap),
    .groups = "drop"
  )

set.seed(seed)
bootstrap_by_dependency <- lapply(DEPENDENCY_LEVELS, function(dependency) {
  values <- item_means %>%
    filter(text_dependency == dependency) %>%
    pull(oracle_recoverable_gap)
  replicate(bootstrap_reps, mean(sample(values, length(values), replace = TRUE)))
})
names(bootstrap_by_dependency) <- DEPENDENCY_LEVELS

summary_rows <- lapply(DEPENDENCY_LEVELS, function(dependency) {
  subset <- target_units %>% filter(text_dependency == dependency)
  draws <- bootstrap_by_dependency[[dependency]]
  tibble(
    text_dependency = dependency,
    n_items = n_distinct(subset$parallel_id),
    n_target_units = nrow(subset),
    original_mismatch_accuracy = mean(subset$original_mismatch_accuracy),
    target_human_parallel_accuracy = mean(subset$target_human_parallel_accuracy),
    oracle_recoverable_gap = mean(subset$oracle_recoverable_gap),
    gap_conf_low = unname(quantile(draws, 0.025)),
    gap_conf_high = unname(quantile(draws, 0.975)),
    bootstrap_reps = bootstrap_reps,
    bootstrap_cluster = "parallel_id",
    estimand = paste(
      "equal-target-language mean of target human-parallel matched endpoint",
      "minus the five-source original mismatch mean"
    )
  )
})
oracle_summary <- bind_rows(summary_rows)
write_csv(
  oracle_summary,
  file.path(output_dir, "rq4_target_human_parallel_summary.csv")
)

did_draws <- (
  bootstrap_by_dependency[["dependent"]] -
    bootstrap_by_dependency[["independent"]]
)
oracle_did <- tibble(
  contrast = "dependent_gap_minus_independent_gap",
  estimate = (
    oracle_summary$oracle_recoverable_gap[
      oracle_summary$text_dependency == "dependent"
    ] -
      oracle_summary$oracle_recoverable_gap[
        oracle_summary$text_dependency == "independent"
      ]
  ),
  conf.low = unname(quantile(did_draws, 0.025)),
  conf.high = unname(quantile(did_draws, 0.975)),
  bootstrap_reps = bootstrap_reps,
  bootstrap_cluster = "parallel_id",
  role = "headroom_sanity_check_not_primary_intervention_test"
)
write_csv(
  oracle_did,
  file.path(output_dir, "rq4_target_human_parallel_did.csv")
)

writeLines(
  c(
    "RQ4 human-parallel endpoint terminology:",
    "- source matched endpoint: (Q_A, G_A)",
    "- target human-parallel matched endpoint: (Q_B, G_B)",
    "- original mismatch: (Q_A, G_B)",
    "- NLLB intervention: (Q_MT[A->B], G_B)",
    "",
    "This analysis uses the target human-parallel matched endpoint only as a",
    "descriptive recoverable-headroom reference. It is not a causal language-only",
    "counterfactual and is not the RQ4 primary intervention test.",
    paste0("Input: ", data_path),
    paste0("Annotation: ", annotation_path),
    paste0("Bootstrap reps: ", bootstrap_reps),
    paste0("Seed: ", seed)
  ),
  file.path(output_dir, "rq4_target_human_parallel_spec.txt")
)
capture.output(sessionInfo(), file = file.path(output_dir, "rq4_oracle_session_info.txt"))

progress_message("RQ4 target human-parallel endpoint analysis completed: ", output_dir)
