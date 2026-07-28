suppressPackageStartupMessages({
  library(broom.mixed)
  library(dplyr)
  library(lme4)
  library(MASS)
  library(readr)
  library(tibble)
  library(tidyr)
})

options(contrasts = c("contr.sum", "contr.poly"))

LANGUAGES <- c("en", "zh", "fr", "ru", "ja", "th")
DIMENSIONS <- c("wf", "wi", "au", "ap", "ael", "rel")


progress_message <- function(...) {
  message(
    sprintf("[%s] ", format(Sys.time(), "%Y-%m-%d %H:%M:%S")),
    paste0(...)
  )
  flush.console()
}


timed_fit <- function(label, expression) {
  started <- Sys.time()
  progress_message("START: ", label)
  result <- eval.parent(substitute(expression))
  elapsed <- as.numeric(difftime(Sys.time(), started, units = "mins"))
  progress_message(
    "DONE: ", label, " (elapsed ", sprintf("%.1f", elapsed), " min)"
  )
  result
}


to_binary <- function(x) {
  if (is.logical(x)) return(as.integer(x))
  if (is.numeric(x) && all(x %in% c(0, 1))) return(as.integer(x))
  text <- tolower(trimws(as.character(x)))
  output <- ifelse(
    text %in% c("true", "1", "yes"), 1L,
    ifelse(text %in% c("false", "0", "no"), 0L, NA_integer_)
  )
  if (anyNA(output)) stop("A binary column contains unrecognized values.")
  output
}


prepare_glmm_data <- function(path, outcome) {
  data <- readr::read_csv(path, show_col_types = FALSE)
  required <- c(
    "parallel_id", "question_language", "gui_language",
    "dimension", "matched", outcome
  )
  missing <- setdiff(required, names(data))
  if (length(missing) > 0) {
    stop("Missing analysis columns: ", paste(missing, collapse = ", "))
  }

  data <- data %>%
    mutate(
      parallel_id = factor(parallel_id),
      question_language = factor(question_language, levels = LANGUAGES),
      gui_language = factor(gui_language, levels = LANGUAGES),
      dimension = factor(dimension, levels = DIMENSIONS),
      matched_num = to_binary(matched),
      y = to_binary(.data[[outcome]])
    )

  if (anyNA(data$question_language) ||
      anyNA(data$gui_language) ||
      anyNA(data$dimension)) {
    stop("Unexpected language or dimension values were found.")
  }
  expected_matched <- as.integer(
    as.character(data$question_language) == as.character(data$gui_language)
  )
  if (!all(data$matched_num == expected_matched)) {
    stop("The matched column is inconsistent with the language columns.")
  }
  if (any(table(data$parallel_id) != 36L)) {
    stop("Every semantic item must contain exactly 36 rows.")
  }
  if (anyDuplicated(data[c(
    "parallel_id", "question_language", "gui_language"
  )])) {
    stop("Duplicate item × query-language × GUI-language cells were found.")
  }
  data
}


glmm_control <- function(fast = FALSE, optimizer_print_every = 0L) {
  opt_control <- list(maxfun = 200000)
  if (optimizer_print_every > 0L) {
    opt_control$iprint <- as.integer(optimizer_print_every)
  }
  if (fast) {
    return(glmerControl(
      optimizer = "bobyqa",
      optCtrl = opt_control,
      calc.derivs = FALSE
    ))
  }
  glmerControl(
    optimizer = "bobyqa",
    optCtrl = opt_control,
    calc.derivs = TRUE
  )
}


fixed_effect_table <- function(model) {
  broom.mixed::tidy(
    model,
    effects = "fixed",
    conf.int = TRUE,
    conf.method = "Wald"
  ) %>%
    mutate(
      odds_ratio = exp(estimate),
      odds_ratio_low = exp(conf.low),
      odds_ratio_high = exp(conf.high)
    )
}


model_diagnostics <- function(model, model_name) {
  gradient <- model@optinfo$derivs$gradient
  hessian <- model@optinfo$derivs$Hessian
  messages <- model@optinfo$conv$lme4$messages
  hessian_min_eigenvalue <- if (is.null(hessian)) {
    NA_real_
  } else {
    min(eigen(hessian, symmetric = TRUE, only.values = TRUE)$values)
  }
  random_sd <- paste(
    round(sqrt(unlist(lapply(VarCorr(model), diag))), 6),
    collapse = " | "
  )
  observation_count <- stats::nobs(model)
  log_likelihood <- as.numeric(logLik(model))
  aic <- AIC(model)
  bic <- BIC(model)
  singular <- isSingular(model, tol = 1e-4)

  tibble(
    model = model_name,
    nobs = observation_count,
    log_likelihood = log_likelihood,
    AIC = aic,
    BIC = bic,
    singular = singular,
    max_absolute_gradient = if (is.null(gradient)) NA_real_ else max(abs(gradient)),
    hessian_min_eigenvalue = hessian_min_eigenvalue,
    random_effect_sd = random_sd,
    convergence_messages = if (is.null(messages)) "" else {
      paste(messages, collapse = " | ")
    }
  )
}


coerce_prediction_grid <- function(grid, data) {
  grid %>%
    mutate(
      question_language = factor(
        question_language, levels = levels(data$question_language)
      ),
      gui_language = factor(
        gui_language, levels = levels(data$gui_language)
      ),
      dimension = factor(dimension, levels = levels(data$dimension)),
      matched_num = as.integer(matched_num)
    )
}


fixed_model_matrix <- function(model, newdata) {
  fixed_terms <- delete.response(terms(lme4::nobars(formula(model))))
  matrix <- model.matrix(fixed_terms, newdata)
  expected_names <- names(fixef(model))
  if (!identical(colnames(matrix), expected_names)) {
    stop(
      "Prediction matrix columns do not match fixed-effect coefficients.\n",
      "Matrix: ", paste(colnames(matrix), collapse = ", "), "\n",
      "Model: ", paste(expected_names, collapse = ", ")
    )
  }
  matrix
}


# Golub-Welsch quadrature for expectations under a standard normal.
normal_quadrature <- function(n = 15L) {
  jacobi <- matrix(0, nrow = n, ncol = n)
  if (n > 1L) {
    off_diagonal <- sqrt(seq_len(n - 1L))
    jacobi[cbind(seq_len(n - 1L), 2:n)] <- off_diagonal
    jacobi[cbind(2:n, seq_len(n - 1L))] <- off_diagonal
  }
  decomposition <- eigen(jacobi, symmetric = TRUE)
  order_index <- order(decomposition$values)
  tibble(
    node = decomposition$values[order_index],
    weight = decomposition$vectors[1, order_index]^2
  )
}


item_intercept_sd <- function(model, group_name = "parallel_id") {
  covariance <- VarCorr(model)
  if (!group_name %in% names(covariance)) {
    stop("Random-intercept grouping factor not found: ", group_name)
  }
  unname(attr(covariance[[group_name]], "stddev")[[1]])
}


marginal_probability_from_eta <- function(
    eta,
    random_intercept_sd,
    quadrature = normal_quadrature()
) {
  output <- eta * 0
  for (index in seq_len(nrow(quadrature))) {
    output <- output + quadrature$weight[[index]] * plogis(
      eta + random_intercept_sd * quadrature$node[[index]]
    )
  }
  output
}


predict_item_marginal_probability <- function(model, newdata) {
  eta <- as.numeric(fixed_model_matrix(model, newdata) %*% fixef(model))
  marginal_probability_from_eta(eta, item_intercept_sd(model))
}


# Standardized probability contrast integrated over the fitted distribution of
# item random intercepts. Intervals propagate fixed-effect covariance while
# treating the estimated random-effect SD as a plug-in value.
simulate_marginal_probability_contrast <- function(
    model,
    newdata_one,
    newdata_zero,
    weights,
    nsim = 2000,
    seed = 42
) {
  if (length(weights) != nrow(newdata_one) ||
      nrow(newdata_one) != nrow(newdata_zero)) {
    stop("Contrast data and weights have incompatible lengths.")
  }
  weights <- weights / sum(weights)
  x_one <- fixed_model_matrix(model, newdata_one)
  x_zero <- fixed_model_matrix(model, newdata_zero)
  random_sd <- item_intercept_sd(model)

  point_one <- marginal_probability_from_eta(
    as.numeric(x_one %*% fixef(model)), random_sd
  )
  point_zero <- marginal_probability_from_eta(
    as.numeric(x_zero %*% fixef(model)), random_sd
  )
  point_estimate <- sum(weights * (point_one - point_zero))

  set.seed(seed)
  coefficient_draws <- MASS::mvrnorm(
    n = nsim, mu = fixef(model), Sigma = as.matrix(vcov(model))
  )
  eta_one <- x_one %*% t(coefficient_draws)
  eta_zero <- x_zero %*% t(coefficient_draws)
  p_one <- marginal_probability_from_eta(eta_one, random_sd)
  p_zero <- marginal_probability_from_eta(eta_zero, random_sd)
  draw_differences <- colSums((p_one - p_zero) * weights)

  tibble(
    estimate = point_estimate,
    conf.low = unname(quantile(draw_differences, 0.025)),
    conf.high = unname(quantile(draw_differences, 0.975)),
    nsim = nsim,
    estimand = "item-marginal standardized probability difference"
  )
}


dimension_weights <- function(data) {
  proportions <- table(data$dimension) / nrow(data)
  tibble(
    dimension = factor(
      names(proportions), levels = levels(data$dimension)
    ),
    dimension_weight = as.numeric(proportions)
  )
}


lrt_table <- function(reduced, full, label) {
  as.data.frame(anova(reduced, full, test = "Chisq")) %>%
    rownames_to_column("model") %>%
    mutate(test_block = label)
}
