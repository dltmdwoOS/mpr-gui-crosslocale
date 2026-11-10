# Robustness GLMM for R_stem / R_opts (see ANALYSIS_PLAN_KO.md).
# Usage: Rscript glmm_rstem.R <glmm_rows.csv> <out_dir> [correct|scoring_correct]
suppressPackageStartupMessages(library(lme4))
args <- commandArgs(trailingOnly = TRUE)
d <- read.csv(args[1])
out <- args[2]
y <- if (length(args) >= 3) args[3] else "correct"
dir.create(out, showWarnings = FALSE, recursive = TRUE)
d$y <- d[[y]]
for (v in c("item", "pair", "query_language", "gui_language")) d[[v]] <- factor(d[[v]])
ctrl <- glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5), calc.derivs = TRUE)

fit <- function(formula) glmer(formula, data = d, family = binomial, control = ctrl)
f_full <- y ~ stem_gui * opts_gui + query_language + gui_language + (1 | item) + (1 | pair)
m_full <- fit(f_full)
re_note <- "item + pair random intercepts"
if (isSingular(m_full)) {
  f_full <- y ~ stem_gui * opts_gui + query_language + gui_language + (1 | item)
  m_full <- fit(f_full)
  re_note <- "pair intercept dropped (singular); item random intercept only"
}
m_add <- update(m_full, . ~ . - stem_gui:opts_gui)
lrt_int <- anova(m_add, m_full)
m_nostem <- update(m_add, . ~ . - stem_gui)
m_noopts <- update(m_add, . ~ . - opts_gui)

co <- summary(m_full)$coefficients
ci <- confint(m_full, parm = c("stem_gui", "opts_gui", "stem_gui:opts_gui"), method = "Wald")
tab <- data.frame(term = rownames(ci), log_or = co[rownames(ci), "Estimate"],
                  or = exp(co[rownames(ci), "Estimate"]), or_lo = exp(ci[, 1]), or_hi = exp(ci[, 2]),
                  wald_p = co[rownames(ci), "Pr(>|z|)"])
write.csv(tab, file.path(out, paste0("glmm_terms_", y, ".csv")), row.names = FALSE)
lrt <- data.frame(
  test = c("interaction", "stem_main_additive", "opts_main_additive"),
  chisq = c(lrt_int$Chisq[2], anova(m_nostem, m_add)$Chisq[2], anova(m_noopts, m_add)$Chisq[2]),
  df = c(lrt_int$Df[2], anova(m_nostem, m_add)$Df[2], anova(m_noopts, m_add)$Df[2]),
  p = c(lrt_int$`Pr(>Chisq)`[2], anova(m_nostem, m_add)$`Pr(>Chisq)`[2], anova(m_noopts, m_add)$`Pr(>Chisq)`[2]))
write.csv(lrt, file.path(out, paste0("glmm_lrt_", y, ".csv")), row.names = FALSE)
diag <- c(paste("outcome:", y), paste("random effects:", re_note),
          paste("singular:", isSingular(m_full)), paste("nobs:", nobs(m_full)),
          paste("convergence messages:", paste(m_full@optinfo$conv$lme4$messages, collapse = "; ")))
writeLines(diag, file.path(out, paste0("glmm_diagnostics_", y, ".txt")))
print(tab); print(lrt); cat(diag, sep = "\n")
