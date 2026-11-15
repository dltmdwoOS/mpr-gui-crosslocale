# Robustness GLMM for Experiment A (pre-registered). Usage: Rscript glmm_expA.R <glmm_rows.csv> <out_dir>
suppressPackageStartupMessages({library(lme4)})
args <- commandArgs(TRUE); d <- read.csv(args[1]); out <- args[2]; dir.create(out, showWarnings = FALSE, recursive = TRUE)
d$condition <- factor(d$condition, levels = c("O", "T", "R"))
for (v in c("item", "pair", "query_language", "gui_language")) d[[v]] <- factor(d[[v]])
ctrl <- glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5))
fit_ok <- function(m) !isSingular(m) && is.null(m@optinfo$conv$lme4$messages)
m <- tryCatch(glmer(correct ~ condition + query_language + gui_language + (1 + condition | item) + (1 | pair),
                    data = d, family = binomial, control = ctrl), error = function(e) NULL)
spec <- "slope"
if (is.null(m) || !fit_ok(m)) {
  spec <- "intercepts"
  m <- glmer(correct ~ condition + query_language + gui_language + (1 | item) + (1 | pair), data = d, family = binomial, control = ctrl)
  if (isSingular(m)) { spec <- "intercepts_item_only"
    m <- glmer(correct ~ condition + query_language + gui_language + (1 | item), data = d, family = binomial, control = ctrl) }
}
b <- fixef(m); V <- as.matrix(vcov(m))
row <- function(name, L) { est <- sum(L * b); se <- sqrt(as.numeric(t(L) %*% V %*% L))
  data.frame(term = name, log_or = est, se = se, or = exp(est), lo = exp(est - 1.96 * se), hi = exp(est + 1.96 * se), p = 2 * pnorm(-abs(est / se))) }
L <- function(nm) { v <- setNames(rep(0, length(b)), names(b)); v[nm] <- 1; v }
res <- rbind(row("T_vs_O", L("conditionT")), row("R_vs_O", L("conditionR")), row("R_vs_T", L("conditionR") - L("conditionT")))
res$spec <- spec; res$singular <- isSingular(m); res$n <- nrow(d)
write.csv(res, file.path(out, "glmm_contrasts.csv"), row.names = FALSE); print(res)
