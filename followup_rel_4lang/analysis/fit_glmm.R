#!/usr/bin/env Rscript

# Fit the REL four-language O/R/C/F GLMM separately for each completed model.
# The four rows of a directed item/language pair share a pair random intercept;
# pairs from the same semantic item also share an item random intercept.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2L || length(args) > 4L) {
  stop(paste(
    "Usage: Rscript fit_glmm.R <glmm_rows.csv> <output_dir>",
    "[both|internvl|qwen] [--smoke]"
  ))
}

input <- args[[1L]]
output_dir <- args[[2L]]
model_choice <- if (length(args) >= 3L) args[[3L]] else "both"
smoke <- length(args) == 4L && identical(args[[4L]], "--smoke")
if (!model_choice %in% c("both", "internvl", "qwen")) stop("Unknown model: ", model_choice)
if (length(args) == 4L && !smoke) stop("The fourth argument must be --smoke")

needed <- c("lme4", "digest")
missing <- needed[!vapply(needed, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing)) stop("Missing R packages: ", paste(missing, collapse = ", "))

data <- read.csv(input, fileEncoding = "UTF-8", stringsAsFactors = FALSE)
required <- c(
  "model", "parallel_id", "pair_id", "query_language", "gui_language",
  "text_dependency", "condition", "reference_alignment",
  "context_localization", "generation_correct"
)
if (!all(required %in% names(data))) stop("Input CSV is missing required columns")
if (nrow(data) != 34336L || anyNA(data[required])) {
  stop("Expected the validated 34,336-row primary analysis table without missing fields")
}
if (!all(data$generation_correct %in% 0:1) ||
    !all(data$reference_alignment %in% 0:1) ||
    !all(data$context_localization %in% 0:1)) {
  stop("Outcome and condition factors must be coded 0/1")
}
if (any(data$query_language == data$gui_language)) {
  stop("Matched-language rows entered the primary analysis input")
}

input_sha256 <- digest::digest(file = input, algo = "sha256")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
choices <- if (model_choice == "both") c("internvl", "qwen") else model_choice
languages <- c("en", "zh", "th", "ru")
dependencies <- c("independent", "dependent")
conditions <- c("O", "R", "C", "F")
formula <- stats::as.formula(
  "generation_correct ~ reference_alignment * context_localization * text_dependency + query_language + gui_language + (1 | parallel_id) + (1 | pair_id)"
)
fixed_formula <- stats::as.formula(
  "~ reference_alignment * context_localization * text_dependency + query_language + gui_language"
)

make_grid <- function() {
  grid <- expand.grid(
    condition = conditions,
    text_dependency = dependencies,
    KEEP.OUT.ATTRS = FALSE,
    stringsAsFactors = FALSE
  )
  grid$reference_alignment <- as.integer(grid$condition %in% c("R", "F"))
  grid$context_localization <- as.integer(grid$condition %in% c("C", "F"))
  grid$text_dependency <- factor(grid$text_dependency, levels = dependencies)
  grid$query_language <- factor("en", levels = languages)
  grid$gui_language <- factor("zh", levels = languages)
  grid
}

contrast_results <- function(fit, model_name) {
  grid <- make_grid()
  design <- stats::model.matrix(fixed_formula, data = grid)
  coefficients <- lme4::fixef(fit)
  if (!identical(colnames(design), names(coefficients))) {
    stop("Contrast design columns do not match the fitted model")
  }
  covariance <- as.matrix(stats::vcov(fit))
  at <- function(dependency, condition) {
    which(as.character(grid$text_dependency) == dependency & grid$condition == condition)
  }
  difference <- function(dependency, first, second) {
    as.numeric(design[at(dependency, first), ] - design[at(dependency, second), ])
  }
  rows <- list()
  vectors <- list()
  for (dependency in dependencies) {
    vectors[[dependency]] <- list(
      R_minus_O = difference(dependency, "R", "O"),
      F_minus_C = difference(dependency, "F", "C"),
      C_minus_O = difference(dependency, "C", "O"),
      F_minus_R = difference(dependency, "F", "R")
    )
    vectors[[dependency]]$interaction <-
      vectors[[dependency]]$F_minus_C - vectors[[dependency]]$R_minus_O
  }
  for (dependency in dependencies) {
    for (name in names(vectors[[dependency]])) {
      rows[[length(rows) + 1L]] <- list(
        dependency = dependency, contrast = name,
        weights = vectors[[dependency]][[name]]
      )
    }
  }
  for (name in names(vectors[["independent"]])) {
    rows[[length(rows) + 1L]] <- list(
      dependency = "dependent_minus_independent",
      contrast = name,
      weights = vectors[["dependent"]][[name]] - vectors[["independent"]][[name]]
    )
  }
  result <- lapply(rows, function(row) {
    weights <- row$weights
    estimate <- sum(weights * coefficients)
    se <- sqrt(as.numeric(t(weights) %*% covariance %*% weights))
    z <- estimate / se
    data.frame(
      model = model_name,
      dependency = row$dependency,
      contrast = row$contrast,
      log_odds = estimate,
      std_error = se,
      odds_ratio = exp(estimate),
      or_ci_low = exp(estimate - 1.96 * se),
      or_ci_high = exp(estimate + 1.96 * se),
      z = z,
      p_value_wald = 2 * stats::pnorm(-abs(z)),
      stringsAsFactors = FALSE
    )
  })
  do.call(rbind, result)
}

all_contrasts <- list()
all_diagnostics <- list()
for (model_name in choices) {
  subset <- data[data$model == model_name, , drop = FALSE]
  if (nrow(subset) != 17168L) stop("Incomplete model-specific input: ", model_name)
  if (smoke) {
    item_ids <- unlist(lapply(dependencies, function(dependency) {
      head(unique(subset$parallel_id[subset$text_dependency == dependency]), 12L)
    }), use.names = FALSE)
    subset <- subset[subset$parallel_id %in% item_ids, , drop = FALSE]
  }
  subset$text_dependency <- factor(subset$text_dependency, levels = dependencies)
  subset$query_language <- factor(subset$query_language, levels = languages)
  subset$gui_language <- factor(subset$gui_language, levels = languages)
  subset$parallel_id <- factor(subset$parallel_id)
  subset$pair_id <- factor(subset$pair_id)
  if (any(table(subset$pair_id) != 4L)) stop("A pair is missing an O/R/C/F condition")

  message("Fitting ", model_name, if (smoke) " smoke" else " full",
          ": ", nrow(subset), " rows, ", nlevels(subset$parallel_id),
          " items, ", nlevels(subset$pair_id), " directed pairs")
  started <- Sys.time()
  fit <- lme4::glmer(
    formula,
    data = subset,
    family = stats::binomial(link = "logit"),
    nAGQ = 1L,
    control = lme4::glmerControl(
      optimizer = "bobyqa", optCtrl = list(maxfun = 200000L)
    )
  )
  elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs"))
  prefix <- file.path(output_dir, paste0(model_name, if (smoke) "_smoke" else ""))
  saveRDS(fit, paste0(prefix, "_model.rds"))
  contrasts <- contrast_results(fit, model_name)
  write.csv(contrasts, paste0(prefix, "_contrasts.csv"), row.names = FALSE, na = "")
  convergence <- fit@optinfo$conv$lme4$messages
  diagnostics <- data.frame(
    model = model_name, smoke = smoke,
    input_sha256 = input_sha256,
    n_rows = nrow(subset),
    n_items = nlevels(subset$parallel_id),
    n_pairs = nlevels(subset$pair_id),
    elapsed_seconds = elapsed,
    log_likelihood = as.numeric(stats::logLik(fit)),
    aic = stats::AIC(fit),
    singular = lme4::isSingular(fit),
    convergence_message = if (is.null(convergence)) "" else paste(convergence, collapse = " | "),
    stringsAsFactors = FALSE
  )
  write.csv(diagnostics, paste0(prefix, "_diagnostics.csv"), row.names = FALSE)
  session_lines <- capture.output(sessionInfo())
  writeLines(sub("[[:space:]]+$", "", session_lines), paste0(prefix, "_session_info.txt"))
  all_contrasts[[model_name]] <- contrasts
  all_diagnostics[[model_name]] <- diagnostics
  message("Saved ", prefix, "_* (", round(elapsed, 1), " seconds)")
}

if (length(choices) == 2L) {
  write.csv(do.call(rbind, all_contrasts), file.path(output_dir, "combined_contrasts.csv"), row.names = FALSE)
  write.csv(do.call(rbind, all_diagnostics), file.path(output_dir, "combined_diagnostics.csv"), row.names = FALSE)
}

message("GLMM fitting complete. Inspect diagnostics before interpreting contrasts.")
