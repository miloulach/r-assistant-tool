# Ensure R installs into your user library
.libPaths("~/R/x86_64-pc-linux-gnu-library/4.2")

packages <- c(
  "ggplot2", "dplyr", "lmtest", "sandwich", "tidyr", "readr", 
  "plm", "AER", "tseries", "vars", "dynlm", "forecast", "quantmod",
  "tsbox", "xts", "car", "MASS", "lme4", "gmm", 
  "VGAM", "tidyverse", "lubridate", "pglm", "lattice", "glmmTMB", 
  "nlme", "broom", "easystats", "performance", "censReg", "aods3", 
  "mclust", "zoo", "timeSeries", "tsibble", "prophet", "fable", 
  "bsts", "rugarch", "urca", "MTS", "stochvol", "vars", 
  "plmtest", "splm", "fixest", "lfe", "bife", "stargazer", 
  "gtsummary", "feols", "tsDyn", "tidyquant", 
  "quantmod", "xtsExtra", "forecastHybrid", "parsnip", "rsample", 
  "caret", "mlr3", "xgboost", "randomForest", "e1071", "keras", 
  "h2o", "ggResidpanel", "visreg", "plotly", "shinystan", "rstanarm", 
  "brms", "bayesplot", "loo"
)


to_install <- packages[!packages %in% installed.packages()[, "Package"]]

if (length(to_install)) {
  install.packages(to_install, repos = "https://cloud.r-project.org", 
                   lib = "~/R/x86_64-pc-linux-gnu-library/4.2")
}

cat("All required packages are installed ✅\n")
