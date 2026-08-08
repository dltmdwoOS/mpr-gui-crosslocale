#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(emmeans)
})

args_all <- commandArgs(trailingOnly = FALSE)
script_file <- sub("^--file=", "", grep("^--file=", args_all, value = TRUE)[1])
script_dir <- dirname(normalizePath(script_file))
source(file.path(script_dir, "glmm_utils.R"))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 3L) {
  stop(
    "Usage: Rscript rel_text_dependency_glmm.R <analysis.csv> <integrated_annotation.csv> ",
    "<output_dir> [outcome] [verbose_level] [manifest.json]\n",
    "Outcome defaults to generation_correct; verbose_level defaults to 1."
  )
}

data_path <- args[[1]]
annotation_path <- args[[2]]
output_dir <- args[[3]]
outcome <- if (length(args) >= 4L) args[[4]] else "generation_correct"
verbose_level <- if (length(args) >= 5L) as.integer(args[[5]]) else 1L
manifest_input <- if (length(args) >= 6L) {
  args[[6]]
} else {
  "annotation/rel_text_dependency/data/pilot_manifest.json"
}
manifest_path <- if (length(args) >= 6L) {
  manifest_input
} else {
  file.path(
    script_dir, "..", "..", "annotation", "rel_text_dependency",
    "data", "pilot_manifest.json"
  )
}

if (is.na(verbose_level) || verbose_level < 0L) {
  stop("verbose_level must be a non-negative integer.")
}

if (outcome != "generation_correct") {
  stop(
    "This frozen REL text-dependency analysis is generation-only. ",
    "Expected outcome='generation_correct', got: ", outcome
  )
}

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

DEPENDENCY_LEVELS <- c("independent", "dependent")
EXPECTED_REL_ITEMS <- 366L
EXPECTED_REL_ROWS <- 366L * 36L
EXPECTED_DEPENDENT_ITEMS <- 302L
EXPECTED_INDEPENDENT_ITEMS <- 64L
EXPECTED_ANNOTATOR_ID <- "team_consensus"
EXPECTED_GUIDELINE <- "pilot-v1+team-adjudication-v1"

if (!file.exists(manifest_path)) {
  stop("Canonical annotation manifest does not exist: ", manifest_path)
}

manifest_path <- normalizePath(manifest_path)
manifest_raw <- readBin(
  manifest_path,
  what = "raw",
  n = file.info(manifest_path)$size
)
manifest_text <- rawToChar(manifest_raw)
manifest_text <- gsub("\r\n", "\n", manifest_text, fixed = TRUE)
manifest_text <- gsub("\r", "\n", manifest_text, fixed = TRUE)
actual_manifest_sha256 <- digest::digest(
  charToRaw(enc2utf8(manifest_text)),
  algo = "sha256",
  serialize = FALSE
)

EXPECTED_ANNOTATION_COLUMNS <- c(
  "parallel_id",
  "annotator_id",
  "display_order",
  "text_dependency",
  "review_flag",
  "note",
  "current_locale",
  "annotation_seconds",
  "guideline_version",
  "manifest_sha256",
  "created_at",
  "updated_at"
)


# -------------------------------------------------------------------------
# 1. Read and validate the frozen model analysis table
# -------------------------------------------------------------------------

progress_message("Reading frozen GLMM table: ", data_path)
full_data <- prepare_glmm_data(data_path, outcome)

data <- full_data %>%
  filter(as.character(dimension) == "rel") %>%
  mutate(parallel_id = as.character(parallel_id))

if (nrow(data) != EXPECTED_REL_ROWS) {
  stop(
    "REL analysis table must contain exactly ", EXPECTED_REL_ROWS,
    " rows (= 366 items x 36 language cells); found ", nrow(data), "."
  )
}

if (dplyr::n_distinct(data$parallel_id) != EXPECTED_REL_ITEMS) {
  stop(
    "REL analysis table must contain exactly 366 semantic items; found ",
    dplyr::n_distinct(data$parallel_id), "."
  )
}

if (any(table(data$parallel_id) != 36L)) {
  stop("Every REL semantic item must contain exactly 36 language cells.")
}


# -------------------------------------------------------------------------
# 2. Read and strictly validate the final adjudicated annotation CSV
#
# Frozen file schema observed for rel_annotations_integrated_366.csv:
#   366 rows x 12 columns
#   text_dependency is the FINAL adjudicated label
#   annotator_id == team_consensus
#   review_flag == 0 for all rows
#   dependent == 302, independent == 64
# -------------------------------------------------------------------------

progress_message("Reading final integrated REL annotation: ", annotation_path)

annotation_raw <- readr::read_csv(
  annotation_path,
  show_col_types = FALSE,
  na = c("", "NA")
)

missing_columns <- setdiff(EXPECTED_ANNOTATION_COLUMNS, names(annotation_raw))
if (length(missing_columns) > 0L) {
  stop(
    "Integrated annotation CSV is missing expected columns: ",
    paste(missing_columns, collapse = ", ")
  )
}

if (nrow(annotation_raw) != EXPECTED_REL_ITEMS) {
  stop(
    "Integrated annotation CSV must contain exactly 366 rows; found ",
    nrow(annotation_raw), "."
  )
}

if (anyDuplicated(annotation_raw$parallel_id)) {
  duplicated_ids <- unique(
    annotation_raw$parallel_id[duplicated(annotation_raw$parallel_id)]
  )
  stop(
    "Duplicate parallel_id values in integrated annotation CSV: ",
    paste(head(duplicated_ids, 20), collapse = ", ")
  )
}

if (anyNA(annotation_raw$parallel_id) || any(trimws(annotation_raw$parallel_id) == "")) {
  stop("Integrated annotation CSV contains missing/empty parallel_id values.")
}

annotation <- annotation_raw %>%
  transmute(
    parallel_id = as.character(parallel_id),
    annotator_id = as.character(annotator_id),
    text_dependency = tolower(trimws(as.character(text_dependency))),
    review_flag = as.integer(review_flag),
    guideline_version = as.character(guideline_version),
    manifest_sha256 = as.character(manifest_sha256)
  )

invalid_labels <- setdiff(unique(annotation$text_dependency), DEPENDENCY_LEVELS)
if (length(invalid_labels) > 0L || anyNA(annotation$text_dependency)) {
  stop(
    "Integrated annotation CSV contains invalid text_dependency labels: ",
    paste(invalid_labels, collapse = ", ")
  )
}

if (!all(annotation$annotator_id == EXPECTED_ANNOTATOR_ID)) {
  stop(
    "Expected every annotator_id to equal '", EXPECTED_ANNOTATOR_ID,
    "' in the final integrated CSV."
  )
}

if (!all(annotation$review_flag == 0L)) {
  stop(
    "Expected every review_flag to be 0 after team adjudication; found ",
    sum(annotation$review_flag != 0L), " unresolved rows."
  )
}

if (!all(annotation$guideline_version == EXPECTED_GUIDELINE)) {
  stop(
    "Unexpected guideline_version in integrated annotation CSV. Expected: ",
    EXPECTED_GUIDELINE
  )
}

if (!all(annotation$manifest_sha256 == actual_manifest_sha256)) {
  stop(
    "Integrated annotation manifest_sha256 does not match the canonical ",
    "manifest after newline normalization. Canonical manifest SHA-256: ",
    actual_manifest_sha256,
    "; CSV values: ",
    paste(unique(annotation$manifest_sha256), collapse = ", ")
  )
}

annotation_counts <- table(annotation$text_dependency)

if (
  unname(annotation_counts[["dependent"]]) != EXPECTED_DEPENDENT_ITEMS ||
  unname(annotation_counts[["independent"]]) != EXPECTED_INDEPENDENT_ITEMS
) {
  stop(
    "Final annotation label counts do not match the adjudicated freeze. Expected ",
    "dependent=302, independent=64; found dependent=",
    unname(annotation_counts[["dependent"]]),
    ", independent=", unname(annotation_counts[["independent"]]), "."
  )
}


# -------------------------------------------------------------------------
# 3. Validate exact REL item universe and join annotations
# -------------------------------------------------------------------------

missing_in_annotation <- setdiff(data$parallel_id, annotation$parallel_id)
extra_in_annotation <- setdiff(annotation$parallel_id, data$parallel_id)

if (length(missing_in_annotation) > 0L || length(extra_in_annotation) > 0L) {
  stop(
    "REL model item IDs and integrated annotation IDs do not match exactly. ",
    "Missing in annotation=", length(missing_in_annotation),
    "; extra in annotation=", length(extra_in_annotation), "."
  )
}

data <- data %>%
  left_join(
    annotation %>% dplyr::select(parallel_id, text_dependency),
    by = "parallel_id"
  ) %>%
  mutate(
    parallel_id = factor(parallel_id),
    text_dependency = factor(text_dependency, levels = DEPENDENCY_LEVELS)
  )

if (anyNA(data$text_dependency)) {
  stop("Annotation join produced missing text_dependency values.")
}

if (any(table(data$parallel_id) != 36L)) {
  stop("Annotation join corrupted the 36-cell repeated-measures structure.")
}

progress_message(
  "Validated REL input: rows=", nrow(data),
  ", items=", nlevels(data$parallel_id),
  ", independent=", EXPECTED_INDEPENDENT_ITEMS,
  ", dependent=", EXPECTED_DEPENDENT_ITEMS
)


# -------------------------------------------------------------------------
# 4. Freeze provenance and descriptive summaries
# -------------------------------------------------------------------------

input_audit <- tibble::tibble(
  analysis_input = data_path,
  annotation_input = annotation_path,
  manifest_input = manifest_input,
  outcome = outcome,
  rel_rows = nrow(data),
  rel_items = nlevels(data$parallel_id),
  independent_items = EXPECTED_INDEPENDENT_ITEMS,
  dependent_items = EXPECTED_DEPENDENT_ITEMS,
  annotator_id = EXPECTED_ANNOTATOR_ID,
  guideline_version = EXPECTED_GUIDELINE,
  manifest_sha256 = actual_manifest_sha256
)

readr::write_csv(
  input_audit,
  file.path(output_dir, "rel_textdep_input_audit.csv")
)

item_counts <- data %>%
  distinct(parallel_id, text_dependency) %>%
  count(text_dependency, name = "n_items") %>%
  mutate(proportion = n_items / sum(n_items))

readr::write_csv(
  item_counts,
  file.path(output_dir, "rel_textdep_item_counts.csv")
)

raw_summary <- data %>%
  group_by(text_dependency, matched_num) %>%
  summarise(
    n_rows = n(),
    n_items = n_distinct(parallel_id),
    correct = sum(y),
    accuracy = mean(y),
    .groups = "drop"
  ) %>%
  mutate(
    condition = ifelse(matched_num == 1L, "matched", "mismatch")
  )

readr::write_csv(
  raw_summary,
  file.path(output_dir, "rel_textdep_raw_summary_generation_correct.csv")
)

raw_gap <- raw_summary %>%
  dplyr::select(text_dependency, condition, accuracy) %>%
  tidyr::pivot_wider(names_from = condition, values_from = accuracy) %>%
  mutate(raw_gap = matched - mismatch)

readr::write_csv(
  raw_gap,
  file.path(output_dir, "rel_textdep_raw_gap_generation_correct.csv")
)


# -------------------------------------------------------------------------
# 5. Primary GLMM model ladder
#
# M0: dependency-specific query/GUI difficulty, no concordance term.
#
# M1: adds one common matched/concordance association.
#
# M2: PRIMARY MODEL. Allows matched association to differ by dependency.
#
# Primary hypothesis test:
#   H0: no matched x text_dependency moderation
#   compare M1 vs M2 by 1-df likelihood-ratio test.
# -------------------------------------------------------------------------

optimizer_print_every <- if (verbose_level == 0L) {
  0L
} else if (verbose_level == 1L) {
  500L
} else {
  100L
}

control <- glmm_control(
  fast = FALSE,
  optimizer_print_every = optimizer_print_every
)

formula_m0 <- y ~
  question_language * text_dependency +
  gui_language * text_dependency +
  (1 | parallel_id)

formula_m1 <- y ~
  question_language * text_dependency +
  gui_language * text_dependency +
  matched_num +
  (1 | parallel_id)

formula_m2 <- y ~
  question_language * text_dependency +
  gui_language * text_dependency +
  matched_num * text_dependency +
  (1 | parallel_id)

fit_or_load <- function(path, label, formula) {
  if (file.exists(path)) {
    progress_message("CHECKPOINT: loading ", label, ": ", path)
    return(readRDS(path))
  }

  model <- timed_fit(
    label,
    lme4::glmer(
      formula,
      data = data,
      family = binomial("logit"),
      control = control,
      nAGQ = 1,
      verbose = 0L
    )
  )

  saveRDS(model, path)
  progress_message("CHECKPOINT SAVED: ", path)
  model
}

m0_path <- file.path(output_dir, "rel_textdep_m0_no_matched_generation_correct.rds")
m1_path <- file.path(output_dir, "rel_textdep_m1_common_matched_generation_correct.rds")
m2_path <- file.path(output_dir, "rel_textdep_m2_matched_interaction_generation_correct.rds")

model_m0 <- fit_or_load(m0_path, "M0: no concordance", formula_m0)
model_m1 <- fit_or_load(m1_path, "M1: common concordance", formula_m1)
model_m2 <- fit_or_load(m2_path, "M2: matched x text_dependency", formula_m2)


# -------------------------------------------------------------------------
# 6. Formal model tests, fixed effects, diagnostics
# -------------------------------------------------------------------------

lrt_results <- dplyr::bind_rows(
  lrt_table(model_m0, model_m1, "common_matched_association"),
  lrt_table(model_m1, model_m2, "matched_by_text_dependency_PRIMARY")
)

readr::write_csv(
  lrt_results,
  file.path(output_dir, "rel_textdep_lrt_generation_correct.csv")
)

readr::write_csv(
  fixed_effect_table(model_m2),
  file.path(output_dir, "rel_textdep_fixed_effects_generation_correct.csv")
)

readr::write_csv(
  dplyr::bind_rows(
    model_diagnostics(model_m0, "rel_textdep_m0_no_matched"),
    model_diagnostics(model_m1, "rel_textdep_m1_common_matched"),
    model_diagnostics(model_m2, "rel_textdep_m2_matched_interaction")
  ),
  file.path(output_dir, "rel_textdep_diagnostics_generation_correct.csv")
)


# -------------------------------------------------------------------------
# 7. Link-scale matched trends and interaction OR
#
# This avoids reading the sum-coded interaction coefficient directly.
# emtrends gives the matched slope separately for each dependency class.
# Their difference gives a directly interpretable interaction log-OR and OR.
# -------------------------------------------------------------------------

matched_trends_grid <- emmeans::emtrends(
  model_m2,
  specs = ~ text_dependency,
  var = "matched_num"
)

matched_trends <- as.data.frame(
  summary(matched_trends_grid, infer = c(TRUE, TRUE))
) %>%
  mutate(
    matched_odds_ratio = exp(matched_num.trend),
    matched_or_low = exp(asymp.LCL),
    matched_or_high = exp(asymp.UCL)
  )

readr::write_csv(
  matched_trends,
  file.path(output_dir, "rel_textdep_matched_trends_generation_correct.csv")
)

interaction_contrast <- emmeans::contrast(
  matched_trends_grid,
  method = list(
    dependent_minus_independent = c(-1, 1)
  )
)

interaction_or <- as.data.frame(
  summary(interaction_contrast, infer = c(TRUE, TRUE))
) %>%
  mutate(
    interaction_odds_ratio = exp(estimate),
    interaction_or_low = exp(asymp.LCL),
    interaction_or_high = exp(asymp.UCL)
  )

readr::write_csv(
  interaction_or,
  file.path(output_dir, "rel_textdep_interaction_or_generation_correct.csv")
)


# -------------------------------------------------------------------------
# 8. Item-marginal adjusted concordance bonus within each dependency class
#
# Estimand follows the existing RQ1/RQ2 pipeline:
# - six diagonal language cells receive equal weight;
# - compare matched=1 with the same diagonal cells counterfactually set to 0;
# - integrate over the fitted item-random-intercept distribution;
# - propagate fixed-effect covariance with 2,000 MVN coefficient draws;
# - treat fitted random-intercept SD as a plug-in value.
# -------------------------------------------------------------------------

make_diagonal_grid <- function(dependency, matched_value) {
  tibble::tibble(
    question_language = factor(
      LANGUAGES,
      levels = levels(data$question_language)
    ),
    gui_language = factor(
      LANGUAGES,
      levels = levels(data$gui_language)
    ),
    text_dependency = factor(
      rep(dependency, length(LANGUAGES)),
      levels = levels(data$text_dependency)
    ),
    matched_num = rep(as.integer(matched_value), length(LANGUAGES))
  )
}

nsim <- 2000L
seed <- 42L

set.seed(seed)
coef_draws <- MASS::mvrnorm(
  n = nsim,
  mu = lme4::fixef(model_m2),
  Sigma = as.matrix(stats::vcov(model_m2))
)

random_sd <- item_intercept_sd(model_m2)

estimate_dependency <- function(dependency) {
  grid_matched <- make_diagonal_grid(dependency, 1L)
  grid_counterfactual <- make_diagonal_grid(dependency, 0L)

  x_matched <- fixed_model_matrix(model_m2, grid_matched)
  x_counter <- fixed_model_matrix(model_m2, grid_counterfactual)

  p_matched <- marginal_probability_from_eta(
    as.numeric(x_matched %*% lme4::fixef(model_m2)),
    random_sd
  )

  p_counter <- marginal_probability_from_eta(
    as.numeric(x_counter %*% lme4::fixef(model_m2)),
    random_sd
  )

  eta_matched_draw <- x_matched %*% t(coef_draws)
  eta_counter_draw <- x_counter %*% t(coef_draws)

  p_matched_draw <- marginal_probability_from_eta(
    eta_matched_draw,
    random_sd
  )

  p_counter_draw <- marginal_probability_from_eta(
    eta_counter_draw,
    random_sd
  )

  matched_draw <- colMeans(p_matched_draw)
  counter_draw <- colMeans(p_counter_draw)
  bonus_draw <- matched_draw - counter_draw

  summary_row <- tibble::tibble(
    text_dependency = dependency,
    adjusted_matched_probability = mean(p_matched),
    adjusted_counterfactual_mismatch_probability = mean(p_counter),
    adjusted_concordance_bonus = mean(p_matched - p_counter),
    bonus_conf_low = unname(stats::quantile(bonus_draw, 0.025)),
    bonus_conf_high = unname(stats::quantile(bonus_draw, 0.975)),
    nsim = nsim,
    estimand = paste(
      "equal-language item-marginal diagonal matched-vs-matched-off",
      "counterfactual probability difference"
    )
  )

  list(
    summary = summary_row,
    bonus_draw = bonus_draw
  )
}

independent_est <- estimate_dependency("independent")
dependent_est <- estimate_dependency("dependent")

bonus_table <- dplyr::bind_rows(
  independent_est$summary,
  dependent_est$summary
)

readr::write_csv(
  bonus_table,
  file.path(output_dir, "rel_textdep_adjusted_bonuses_generation_correct.csv")
)


# -------------------------------------------------------------------------
# 9. Probability-scale moderation:
#    dependent adjusted bonus - independent adjusted bonus
# -------------------------------------------------------------------------

did_draw <- dependent_est$bonus_draw - independent_est$bonus_draw

probability_did <- tibble::tibble(
  contrast = "dependent_bonus_minus_independent_bonus",
  estimate = (
    dependent_est$summary$adjusted_concordance_bonus -
      independent_est$summary$adjusted_concordance_bonus
  ),
  conf.low = unname(stats::quantile(did_draw, 0.025)),
  conf.high = unname(stats::quantile(did_draw, 0.975)),
  nsim = nsim,
  estimand = paste(
    "difference in item-marginal standardized concordance bonuses;",
    "fixed-effect covariance propagated; random-intercept SD plug-in"
  )
)

readr::write_csv(
  probability_did,
  file.path(output_dir, "rel_textdep_probability_did_generation_correct.csv")
)


# -------------------------------------------------------------------------
# 10. Reproducibility record
# -------------------------------------------------------------------------

model_spec <- c(
  "Outcome: generation_correct",
  "Scope: REL only; 366 semantic items x 36 language cells = 13,176 rows",
  paste0(
    "Final annotation: dependent=", EXPECTED_DEPENDENT_ITEMS,
    ", independent=", EXPECTED_INDEPENDENT_ITEMS
  ),
  paste0("Annotator ID: ", EXPECTED_ANNOTATOR_ID),
  paste0("Guideline: ", EXPECTED_GUIDELINE),
  paste0("Manifest file: ", manifest_input),
  paste0("Manifest SHA-256: ", actual_manifest_sha256),
  "",
  "M0:",
  paste(deparse(formula_m0), collapse = " "),
  "",
  "M1:",
  paste(deparse(formula_m1), collapse = " "),
  "",
  "M2 PRIMARY:",
  paste(deparse(formula_m2), collapse = " "),
  "",
  "Primary hypothesis test: likelihood-ratio test M1 vs M2",
  "Primary moderation term: matched_num x text_dependency",
  "Probability estimand: equal-language item-marginal standardized concordance bonus",
  "Probability CI: 2,000 MVN fixed-effect draws; random-intercept SD plug-in"
)

writeLines(
  model_spec,
  con = file.path(output_dir, "rel_textdep_model_spec.txt")
)

capture.output(
  sessionInfo(),
  file = file.path(output_dir, "rel_textdep_session_info.txt")
)

progress_message("REL text-dependency GLMM completed: ", output_dir)
progress_message(
  "PRIMARY TEST -> rel_textdep_lrt_generation_correct.csv ",
  "(matched_by_text_dependency_PRIMARY)"
)
progress_message(
  "SUBSET EFFECTS -> rel_textdep_adjusted_bonuses_generation_correct.csv"
)
progress_message(
  "PROBABILITY DID -> rel_textdep_probability_did_generation_correct.csv"
)
progress_message(
  "INTERACTION OR -> rel_textdep_interaction_or_generation_correct.csv"
)
