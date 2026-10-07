#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
input <- if (length(args) >= 1L) args[[1L]] else
  "followup_rel_4lang/results/analysis_ready/glmm_rows.csv"

needed <- c("lme4", "emmeans", "readr", "dplyr")
missing <- needed[!vapply(needed, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing)) stop("Missing R packages: ", paste(missing, collapse = ", "))

data <- read.csv(input, fileEncoding = "UTF-8", stringsAsFactors = FALSE)
required <- c(
  "model", "parallel_id", "pair_id", "query_language", "gui_language",
  "text_dependency", "condition", "reference_alignment",
  "context_localization", "generation_correct"
)
if (!all(required %in% names(data))) stop("GLMM input columns are incomplete")
if (nrow(data) != 34336L) stop("Expected 34,336 eligible model rows")
if (!setequal(data$model, c("internvl", "qwen"))) stop("Expected both completed models")
if (anyNA(data[required])) stop("Required GLMM input fields contain NA")
if (!all(data$generation_correct %in% 0:1)) stop("Outcome is not binary")
if (any(data$query_language == data$gui_language)) stop("Matched-language rows entered the primary table")

key <- paste(data$model, data$pair_id, sep = "|")
groups <- split(data$condition, key)
if (length(groups) != 8584L || !all(vapply(groups, function(x) identical(sort(x), c("C", "F", "O", "R")), logical(1)))) {
  stop("Incomplete or duplicated O/R/C/F quartets")
}

counts <- table(data$model, data$text_dependency)
if (any(counts[, "dependent"] != 14304L) ||
    any(counts[, "independent"] != 2864L)) {
  stop("Dependency-specific row counts differ from the published summaries")
}

fixed <- model.matrix(
  ~ reference_alignment * context_localization * text_dependency +
    query_language + gui_language,
  data = data
)
if (qr(fixed)$rank != ncol(fixed)) stop("Proposed fixed-effect design is rank deficient")

cat("R version:", R.version.string, "\n")
cat("R packages:", paste(needed, collapse = ", "), "available\n")
cat("GLMM input:", nrow(data), "rows;", length(groups), "complete model quartets\n")
print(counts)
cat("Fixed-effect design:", ncol(fixed), "columns, full rank\n")
