#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(emmeans)
})

args_all <- commandArgs(trailingOnly = FALSE)
script_file <- sub("^--file=", "", grep("^--file=", args_all, value = TRUE)[1])
script_dir <- dirname(normalizePath(script_file))
source(file.path(script_dir, "glmm_utils.R"))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2L) {
  stop(
    "Usage: Rscript rel_nllb_intervention_glmm.R <combined_21960.csv> ",
    "<output_dir> [verbose_level] [nsim] [seed] ",
    "[translation_issue_policy=include|exclude_failed|exclude_any_issue]"
  )
}

data_path <- args[[1]]
output_dir <- args[[2]]
verbose_level <- if (length(args) >= 3L) as.integer(args[[3]]) else 1L
nsim <- if (length(args) >= 4L) as.integer(args[[4]]) else 2000L
seed <- if (length(args) >= 5L) as.integer(args[[5]]) else 42L
translation_issue_policy <- if (length(args) >= 6L) args[[6]] else "include"
if (is.na(verbose_level) || verbose_level < 0L) stop("Invalid verbose_level.")
if (is.na(nsim) || nsim < 100L) stop("nsim must be >= 100.")
if (is.na(seed)) stop("seed must be an integer.")
if (!translation_issue_policy %in% c("include", "exclude_failed", "exclude_any_issue")) {
  stop("Invalid translation_issue_policy: ", translation_issue_policy)
}
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

EXPECTED_ROWS <- 21960L
EXPECTED_PAIRS <- 10980L
EXPECTED_ITEMS <- 366L
DEPENDENCY_LEVELS <- c("independent", "dependent")

progress_message("Reading validated RQ4 paired table: ", data_path)
raw <- read_csv(data_path, show_col_types = FALSE)
required <- c(
  "pair_id", "parallel_id", "source_question_language", "gui_language",
  "text_dependency", "intervention", "generation_correct", "model_id",
  "model_revision", "translation_status", "translation_analysis_eligible"
)
missing <- setdiff(required, names(raw))
if (length(missing) > 0L) {
  stop("RQ4 combined table is missing columns: ", paste(missing, collapse = ", "))
}
if (nrow(raw) != EXPECTED_ROWS) {
  stop("RQ4 combined table must contain exactly 21,960 rows; found ", nrow(raw), ".")
}
intervention_treatments <- setdiff(unique(raw$intervention), "original")
if (length(intervention_treatments) != 1L) {
  stop("RQ4 table must contain original plus exactly one intervention treatment.")
}
intervention_treatment <- intervention_treatments[[1]]
INTERVENTION_LEVELS <- c("original", intervention_treatment)

issue_pair_count <- raw %>%
  distinct(pair_id, translation_status, translation_analysis_eligible) %>%
  summarise(n = sum(translation_status != "ok")) %>%
  pull(n)
if (translation_issue_policy == "exclude_failed") {
  raw <- raw %>% filter(as.integer(translation_analysis_eligible) == 1L)
} else if (translation_issue_policy == "exclude_any_issue") {
  raw <- raw %>% filter(translation_status == "ok")
}
analysis_pairs <- n_distinct(raw$pair_id)
if (nrow(raw) != analysis_pairs * 2L) {
  stop("Translation-issue filtering did not preserve exact original-intervention pairs.")
}

data <- raw %>%
  mutate(
    pair_id = factor(pair_id),
    parallel_id = factor(parallel_id),
    source_question_language = factor(source_question_language, levels = LANGUAGES),
    gui_language = factor(gui_language, levels = LANGUAGES),
    text_dependency = factor(text_dependency, levels = DEPENDENCY_LEVELS),
    intervention = factor(intervention, levels = INTERVENTION_LEVELS),
    intervention_num = as.integer(intervention == intervention_treatment),
    y = to_binary(generation_correct)
  )

if (anyNA(data$source_question_language) || anyNA(data$gui_language) ||
    anyNA(data$text_dependency) || anyNA(data$intervention)) {
  stop("RQ4 table contains an unexpected language, dependency, or intervention value.")
}
if (nlevels(data$pair_id) != analysis_pairs || nlevels(data$parallel_id) != EXPECTED_ITEMS) {
  stop("RQ4 analysis table has an invalid pair or semantic-item universe.")
}
if (any(table(data$pair_id) != 2L)) stop("Every pair_id must have exactly two rows.")
pair_conditions <- data %>%
  count(pair_id, intervention, name = "n")
if (nrow(pair_conditions) != analysis_pairs * 2L || any(pair_conditions$n != 1L)) {
  stop("Every pair must contain exactly one original and one intervention row.")
}
if (any(as.character(data$source_question_language) == as.character(data$gui_language))) {
  stop("RQ4 combined table contains a source-matched language pair.")
}
if (n_distinct(data$model_id) != 1L || n_distinct(data$model_revision) != 1L) {
  stop("RQ4 GLMM input must contain exactly one frozen VLM identity and revision.")
}
item_dependency <- data %>% distinct(parallel_id, text_dependency)
dependency_counts <- table(item_dependency$text_dependency)
if (
  unname(dependency_counts[["dependent"]]) != 302L ||
  unname(dependency_counts[["independent"]]) != 64L
) {
  stop("RQ4 dependency counts must be dependent=302 and independent=64.")
}

raw_summary <- data %>%
  group_by(text_dependency, intervention) %>%
  summarise(
    n_rows = n(),
    n_items = n_distinct(parallel_id),
    n_pairs = n_distinct(pair_id),
    correct = sum(y),
    accuracy = mean(y),
    .groups = "drop"
  )
write_csv(raw_summary, file.path(output_dir, "rq4_raw_summary_generation_correct.csv"))

raw_gains <- raw_summary %>%
  select(text_dependency, intervention, accuracy) %>%
  pivot_wider(names_from = intervention, values_from = accuracy) %>%
  mutate(raw_intervention_gain = .data[[intervention_treatment]] - original)
write_csv(raw_gains, file.path(output_dir, "rq4_raw_mt_gains_generation_correct.csv"))

optimizer_print_every <- if (verbose_level == 0L) 0L else if (verbose_level == 1L) 500L else 100L
control <- glmm_control(fast = FALSE, optimizer_print_every = optimizer_print_every)

fixed_m0 <- y ~
  source_question_language * text_dependency +
  gui_language * text_dependency
fixed_m1 <- update(fixed_m0, . ~ . + intervention_num)
fixed_m2 <- update(fixed_m0, . ~ . + intervention_num * text_dependency)

nested_random <- ~ (1 | parallel_id) + (1 | pair_id)
item_random <- ~ (1 | parallel_id)

combine_formula <- function(fixed, random) {
  stats::as.formula(paste(
    paste(deparse(fixed), collapse = " "),
    "+",
    sub("^~", "", paste(deparse(random), collapse = " "))
  ))
}

fit_ladder <- function(random_formula, structure_name) {
  formulas <- list(
    m0 = combine_formula(fixed_m0, random_formula),
    m1 = combine_formula(fixed_m1, random_formula),
    m2 = combine_formula(fixed_m2, random_formula)
  )
  paths <- lapply(names(formulas), function(name) {
    file.path(output_dir, paste0("rq4_", structure_name, "_", name, ".rds"))
  })
  names(paths) <- names(formulas)
  models <- list()
  for (name in names(formulas)) {
    if (file.exists(paths[[name]])) {
      progress_message("CHECKPOINT: loading ", structure_name, " ", name)
      models[[name]] <- readRDS(paths[[name]])
    } else {
      models[[name]] <- timed_fit(
        paste0("RQ4 ", structure_name, " ", toupper(name)),
        glmer(
          formulas[[name]], data = data, family = binomial("logit"),
          control = control, nAGQ = 1, verbose = 0L
        )
      )
      saveRDS(models[[name]], paths[[name]])
      progress_message("CHECKPOINT SAVED: ", paths[[name]])
    }
  }
  list(models = models, formulas = formulas)
}

# Frozen fallback rule: attempt the exact item+pair structure first. If fitting
# fails or any member of the ladder is singular, refit the entire ladder with
# the item-only structure so M1 and M2 always share identical random effects.
nested_attempt <- tryCatch(
  fit_ladder(nested_random, "item_pair"),
  error = function(error) {
    progress_message("Nested item+pair ladder failed: ", conditionMessage(error))
    NULL
  }
)
nested_singular <- is.null(nested_attempt) || any(vapply(
  nested_attempt$models,
  function(model) isSingular(model, tol = 1e-4),
  logical(1)
))

if (nested_singular) {
  progress_message("FALLBACK: using item-only random intercept for the full M0-M2 ladder.")
  selected <- fit_ladder(item_random, "item_only")
  selected_structure <- "item_only_fallback_after_nested_failure_or_singularity"
} else {
  selected <- nested_attempt
  selected_structure <- "item_plus_pair_primary"
}
model_m0 <- selected$models$m0
model_m1 <- selected$models$m1
model_m2 <- selected$models$m2

lrt_results <- bind_rows(
  lrt_table(model_m0, model_m1, "common_query_alignment_intervention_gain"),
  lrt_table(model_m1, model_m2, "intervention_by_text_dependency_PRIMARY")
)
write_csv(lrt_results, file.path(output_dir, "rq4_lrt_generation_correct.csv"))
write_csv(fixed_effect_table(model_m2), file.path(output_dir, "rq4_fixed_effects_generation_correct.csv"))
write_csv(
  bind_rows(
    model_diagnostics(model_m0, "rq4_m0"),
    model_diagnostics(model_m1, "rq4_m1"),
    model_diagnostics(model_m2, "rq4_m2_primary")
  ) %>% mutate(selected_random_structure = selected_structure),
  file.path(output_dir, "rq4_diagnostics_generation_correct.csv")
)

intervention_trends_grid <- emtrends(
  model_m2, specs = ~ text_dependency, var = "intervention_num"
)
intervention_trends <- as.data.frame(
  summary(intervention_trends_grid, infer = c(TRUE, TRUE))
) %>%
  mutate(
    intervention_odds_ratio = exp(intervention_num.trend),
    intervention_or_low = exp(asymp.LCL),
    intervention_or_high = exp(asymp.UCL)
  )
write_csv(intervention_trends, file.path(output_dir, "rq4_intervention_trends.csv"))

interaction_or <- as.data.frame(summary(
  contrast(
    intervention_trends_grid,
    method = list(dependent_minus_independent = c(-1, 1))
  ),
  infer = c(TRUE, TRUE)
)) %>%
  mutate(
    interaction_odds_ratio = exp(estimate),
    interaction_or_low = exp(asymp.LCL),
    interaction_or_high = exp(asymp.UCL)
  )
write_csv(interaction_or, file.path(output_dir, "rq4_intervention_interaction_or.csv"))

total_random_sd <- function(model) {
  covariance <- VarCorr(model)
  variances <- vapply(covariance, function(value) unname(attr(value, "stddev")[[1]])^2, numeric(1))
  sqrt(sum(variances))
}

direction_grid <- expand.grid(
  source_question_language = LANGUAGES,
  gui_language = LANGUAGES,
  stringsAsFactors = FALSE
) %>%
  filter(source_question_language != gui_language)

make_grid <- function(dependency, intervention_value) {
  direction_grid %>%
    transmute(
      source_question_language = factor(source_question_language, levels = LANGUAGES),
      gui_language = factor(gui_language, levels = LANGUAGES),
      text_dependency = factor(dependency, levels = DEPENDENCY_LEVELS),
      intervention_num = as.integer(intervention_value)
    )
}

set.seed(seed)
coefficient_draws <- MASS::mvrnorm(
  n = nsim, mu = fixef(model_m2), Sigma = as.matrix(vcov(model_m2))
)
random_sd <- total_random_sd(model_m2)

estimate_gain <- function(dependency) {
  original_grid <- make_grid(dependency, 0L)
  intervention_grid <- make_grid(dependency, 1L)
  x_original <- fixed_model_matrix(model_m2, original_grid)
  x_intervention <- fixed_model_matrix(model_m2, intervention_grid)
  beta <- fixef(model_m2)
  p_original <- marginal_probability_from_eta(as.numeric(x_original %*% beta), random_sd)
  p_intervention <- marginal_probability_from_eta(
    as.numeric(x_intervention %*% beta), random_sd
  )
  original_draws <- marginal_probability_from_eta(x_original %*% t(coefficient_draws), random_sd)
  intervention_draws <- marginal_probability_from_eta(
    x_intervention %*% t(coefficient_draws), random_sd
  )
  gain_draw <- colMeans(intervention_draws - original_draws)
  list(
    summary = tibble(
      text_dependency = dependency,
      adjusted_original_probability = mean(p_original),
      adjusted_intervention_probability = mean(p_intervention),
      adjusted_intervention_gain = mean(p_intervention - p_original),
      gain_conf_low = unname(quantile(gain_draw, 0.025)),
      gain_conf_high = unname(quantile(gain_draw, 0.975)),
      nsim = nsim,
      random_structure = selected_structure,
      estimand = paste0(
        "equal-directed-pair marginal ", intervention_treatment,
        "-minus-original probability difference"
      )
    ),
    draws = gain_draw
  )
}

independent_gain <- estimate_gain("independent")
dependent_gain <- estimate_gain("dependent")
gain_table <- bind_rows(independent_gain$summary, dependent_gain$summary)
write_csv(gain_table, file.path(output_dir, "rq4_adjusted_mt_gains_generation_correct.csv"))

did_draws <- dependent_gain$draws - independent_gain$draws
probability_did <- tibble(
  contrast = "dependent_intervention_gain_minus_independent_intervention_gain",
  estimate = dependent_gain$summary$adjusted_intervention_gain -
    independent_gain$summary$adjusted_intervention_gain,
  conf.low = unname(quantile(did_draws, 0.025)),
  conf.high = unname(quantile(did_draws, 0.975)),
  nsim = nsim,
  random_structure = selected_structure,
  estimand = "difference in equal-directed-pair marginal intervention gains"
)
write_csv(probability_did, file.path(output_dir, "rq4_probability_did_generation_correct.csv"))

model_spec <- c(
  "RQ4 frozen primary outcome: generation_correct",
  paste0(
    "Full validated artifact: 21,960 rows = 10,980 exact pairs x (original, ",
    intervention_treatment, ")"
  ),
  paste0("Intervention treatment label: ", intervention_treatment),
  paste0("Translation issue policy: ", translation_issue_policy),
  paste0("Translation issue pairs in full artifact: ", issue_pair_count),
  paste0("Analyzed rows: ", nrow(data), "; analyzed pairs: ", analysis_pairs),
  "Items: 366 REL; dependent=302; independent=64",
  paste0("Model ID: ", unique(data$model_id)),
  paste0("Model revision: ", unique(data$model_revision)),
  paste0("Selected random structure: ", selected_structure),
  "Primary random-effects attempt: (1|parallel_id) + (1|pair_id)",
  "Frozen fallback: refit all M0-M2 with (1|parallel_id) if nested ladder fails or is singular",
  "M1 and M2 always use the same random-effects structure",
  "",
  paste0("M0: ", paste(deparse(selected$formulas$m0), collapse = " ")),
  paste0("M1: ", paste(deparse(selected$formulas$m1), collapse = " ")),
  paste0("M2 PRIMARY: ", paste(deparse(selected$formulas$m2), collapse = " ")),
  "Primary test: M1 vs M2 1-df likelihood-ratio test",
  "Primary effect: intervention_num x text_dependency",
  "Probability estimand: equal weighting over 30 directed source-GUI pairs",
  paste0("Probability simulations: ", nsim, "; seed=", seed),
  "",
  "GEE sensitivity is intentionally excluded from the current implementation and run plan.",
  "It remains a separately authorized future sensitivity analysis."
)
writeLines(model_spec, file.path(output_dir, "rq4_model_spec.txt"))
capture.output(sessionInfo(), file = file.path(output_dir, "rq4_session_info.txt"))

primary_lrt <- lrt_results %>%
  filter(test_block == "intervention_by_text_dependency_PRIMARY") %>%
  slice_tail(n = 1L)
p_column <- grep("^Pr\\(", names(primary_lrt), value = TRUE)
primary_p <- if (length(p_column) == 1L) primary_lrt[[p_column]] else NA_real_
gain_by_dependency <- setNames(
  gain_table$adjusted_intervention_gain,
  gain_table$text_dependency
)
did_value <- probability_did$estimate[[1]]
result_report <- c(
  "# RQ4 REL query-alignment intervention GLMM 결과 요약",
  "",
  paste0("- Model: `", unique(data$model_id), "`"),
  paste0("- Revision: `", unique(data$model_revision), "`"),
  paste0("- Intervention: `", intervention_treatment, "`"),
  paste0("- Random-effects structure: `", selected_structure, "`"),
  paste0(
    "- Independent adjusted intervention gain: ",
    sprintf("%+.2f%%p", 100 * gain_by_dependency[["independent"]])
  ),
  paste0(
    "- Dependent adjusted intervention gain: ",
    sprintf("%+.2f%%p", 100 * gain_by_dependency[["dependent"]])
  ),
  paste0("- Probability DID: ", sprintf("%+.2f%%p", 100 * did_value)),
  paste0(
    "- Primary M1 vs M2 LRT: chi-square=",
    sprintf("%.3f", primary_lrt$Chisq[[1]]),
    ", df=", primary_lrt$`Chi Df`[[1]],
    ", p=", format(primary_p, scientific = TRUE, digits = 4)
  ),
  "",
  "Primary outcome은 `generation_correct`이며 primary moderation은",
  "`intervention × text_dependency`이다.",
  "",
  "GEE sensitivity는 현재 구현·실행 범위에서 의도적으로 제외했으며,",
  "필요 시 별도 후속 분석으로 수행한다."
)
writeLines(result_report, file.path(output_dir, "RQ4_GLMM_RESULT_SUMMARY_KO.md"))

progress_message("RQ4 GLMM completed: ", output_dir)
progress_message("PRIMARY TEST -> rq4_lrt_generation_correct.csv")
progress_message("SUBSET GAINS -> rq4_adjusted_mt_gains_generation_correct.csv")
progress_message("DID -> rq4_probability_did_generation_correct.csv")
