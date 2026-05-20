############################################################
# SEM / Path Analysis for Security Nudge Study
# File: sem_analysis.R
############################################################

# ---------------------------
# 0. Load packages
# ---------------------------
library(tidyverse)
library(readr)
library(psych)
library(lavaan)
library(semPlot)
library(effectsize)
library(broom)
library(knitr)
library(stringr)

# ---------------------------
# 1. Load data
# ---------------------------
df_raw <- read_csv("participant_profiles_schema.csv", show_col_types = FALSE)

clean_names <- names(df_raw) |>
  stringr::str_replace_all("\u00a0", " ") |>
  stringr::str_replace_all("\\s+", " ") |>
  stringr::str_trim()

names(df_raw) <- make.unique(clean_names, sep = "__dup_")

glimpse(df_raw)
dim(df_raw)

dup_names <- names(df_raw)[grepl("__dup_", names(df_raw))]
if (length(dup_names) > 0) {
  cat("\nColumns made unique after cleaning:\n")
  print(dup_names)
}

# ---------------------------
# 2. Helper functions
# ---------------------------

# 6-point agreement scale
recode_agree6 <- function(x) {
  case_when(
    x == "COMPLETELY DISAGREE" ~ 1,
    x == "DISAGREE" ~ 2,
    x == "SOMEHOW DISAGREE" ~ 3,
    x == "SOMEHOW AGREE" ~ 4,
    x == "AGREE" ~ 5,
    x == "COMPLETELY AGREE" ~ 6,
    TRUE ~ NA_real_
  )
}

# 5-point frequency scale
recode_freq5 <- function(x) {
  case_when(
    x == "NEVER" ~ 1,
    x == "RARELY" ~ 2,
    x == "SOMETIMES" ~ 3,
    x == "OFTEN" ~ 4,
    x == "ALWAYS" ~ 5,
    TRUE ~ NA_real_
  )
}

# Generic 1-6 likelihood scale if needed
recode_likelihood6 <- function(x) {
  case_when(
    x == "VERY UNLIKELY" ~ 1,
    x == "UNLIKELY" ~ 2,
    x == "SOMEWHAT UNLIKELY" ~ 3,
    x == "SOMEWHAT LIKELY" ~ 4,
    x == "LIKELY" ~ 5,
    x == "VERY LIKELY" ~ 6,
    TRUE ~ NA_real_
  )
}

# Reverse scoring for 6-point scale
reverse6 <- function(x) ifelse(is.na(x), NA_real_, 7 - x)

# Reverse scoring for 5-point scale
reverse5 <- function(x) ifelse(is.na(x), NA_real_, 6 - x)

# Normalize to 0-1 to handle different scale lengths safely
norm01 <- function(x, min_val, max_val) {
  ifelse(is.na(x), NA_real_, (x - min_val) / (max_val - min_val))
}

# Safe row mean
row_mean_safe <- function(...) {
  rowMeans(cbind(...), na.rm = TRUE)
}

# Detect scale type from observed response options
is_freq5_col <- function(x) {
  vals <- unique(na.omit(as.character(x)))
  any(vals %in% c("NEVER", "RARELY", "SOMETIMES", "OFTEN", "ALWAYS"))
}

is_agree6_col <- function(x) {
  vals <- unique(na.omit(as.character(x)))
  any(vals %in% c(
    "COMPLETELY DISAGREE", "DISAGREE", "SOMEHOW DISAGREE",
    "SOMEHOW AGREE", "AGREE", "COMPLETELY AGREE"
  ))
}

# Safe alpha that skips all-NA / no-variance items
safe_alpha <- function(dat) {
  dat2 <- dat %>% select(where(~ !all(is.na(.))))
  dat2 <- dat2 %>% select(where(~ dplyr::n_distinct(na.omit(.)) > 1))
  
  if (ncol(dat2) < 2) {
    return(NULL)
  }
  
  suppressWarnings(psych::alpha(dat2))
}

fmt_alpha <- function(a) {
  if (is.null(a)) "Not estimable (fewer than 2 varying items)" else round(a$total$raw_alpha, 3)
}

# ---------------------------
# 3. Optional participant filtering
# ---------------------------
# Keep only participants who:
# - have a nudge condition
# - have follow count
# - provided consent after debriefing if that item exists

df <- df_raw %>%
  filter(!is.na(Nudge)) %>%
  filter(!is.na(`Number of tasks tool used`))

debrief_col <- "Initially, participants were informed that the purpose of this study was to assist in testing and debugging a tool under development. However, to minimize potential consciousness bias, the actual objective of the study was not disclosed at the outset. The true aim of the research is to investigate whether providing warnings about security issues in GenAI-generated code can encourage developers to adopt more security-aware behaviors, specifically, to assess whether such warnings prompt developers to review and address security concerns in the generated code. Additionally, the study examines whether different types of warnings lead to variations in developer behavior. This initial omission was intentional, as revealing the true purpose upfront could have led participants to consciously alter their behavior by actively checking for security issues, thereby compromising the validity of their natural coding practices. Do you still give us consent to use your answers for the purpose of this study? Please note that your eligibility to receive the incentive is not contingent upon how you respond to this question. Upon completing the survey, you will receive the compensation for this part of the study."

if (debrief_col %in% names(df)) {
  df <- df %>% filter(is.na(.data[[debrief_col]]) | .data[[debrief_col]] == "YES")
}

cat("Sample size after initial filtering:", nrow(df), "\n")

# ---------------------------
# 4. Core observed variables
# ---------------------------

df <- df %>%
  mutate(
    NudgeType = ifelse(Nudge == "B", 1, 0),
    FollowCount = as.numeric(`Number of tasks tool used`)
  )

summary(df$FollowCount)
table(df$Nudge, useNA = "ifany")

# ---------------------------
# 5. Recode baseline motivation
# ---------------------------

mot1_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I explore GenAI technology even if it’s not critical to my job.]"
mot2_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I use GenAI tools because it’s a way for me to look good with peers.]"
mot3_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [Its fun to try new GenAI technology that is not yet available to everyone such as being a participant in beta testing programs.]"

df <- df %>%
  mutate(
    mot1 = recode_agree6(.data[[mot1_col]]),
    mot2 = recode_agree6(.data[[mot2_col]]),
    mot3 = recode_agree6(.data[[mot3_col]]),
    Motivation = row_mean_safe(mot1, mot2, mot3)
  )

# ---------------------------
# 6. Identify BI columns automatically
# ---------------------------

bi_cols <- names(df)[grepl(
  "intend to use GenAI tools in the future|plan to continue using GenAI tools|always try to use GenAI tools in my work",
  names(df)
)]

cat("\nBehavioral Intention columns detected:\n")
print(bi_cols)

if (length(bi_cols) != 6) {
  stop(
    paste0(
      "Expected 6 Behavioral Intention columns (3 pre + 3 post), but found ",
      length(bi_cols),
      ". Inspect `bi_cols` and assign them manually."
    )
  )
}

# Assumes survey export order is pre items first, then post items
bi_pre_1_col <- bi_cols[1]
bi_pre_2_col <- bi_cols[2]
bi_pre_3_col <- bi_cols[3]
bi_post_1_col <- bi_cols[4]
bi_post_2_col <- bi_cols[5]
bi_post_3_col <- bi_cols[6]

# ---------------------------
# 7. Identify Risk columns automatically
# ---------------------------

risk_cols_all <- names(df)[grepl(
  "I avoid advanced GenAI features or options|I avoid activities when using GenAI tools that are dangerous or risky|Despite the risks I use GenAI features that haven’t been proven to work|Despite the risks I use GenAI features that haven't been proven to work",
  names(df)
)]

cat("\nRisk-related columns detected:\n")
print(risk_cols_all)

risk_pre_candidates <- risk_cols_all[sapply(df[risk_cols_all], is_agree6_col)]
risk_post_candidates <- risk_cols_all[sapply(df[risk_cols_all], is_freq5_col)]

cat("\nRisk PRE candidates:\n")
print(risk_pre_candidates)

cat("\nRisk POST candidates:\n")
print(risk_post_candidates)

if (length(risk_pre_candidates) != 3) {
  stop(paste0(
    "Expected 3 PRE risk columns, found ", length(risk_pre_candidates),
    ". Inspect risk_pre_candidates manually."
  ))
}

if (length(risk_post_candidates) != 3) {
  stop(paste0(
    "Expected 3 POST risk columns, found ", length(risk_post_candidates),
    ". Inspect risk_post_candidates manually."
  ))
}

risk_pre_1_col <- risk_pre_candidates[grepl("advanced GenAI features or options", risk_pre_candidates)][1]
risk_pre_2_col <- risk_pre_candidates[grepl("dangerous or risky", risk_pre_candidates)][1]
risk_pre_3_col <- risk_pre_candidates[grepl("haven’t been proven to work|haven't been proven to work", risk_pre_candidates)][1]

risk_post_1_col <- risk_post_candidates[grepl("advanced GenAI features or options", risk_post_candidates)][1]
risk_post_2_col <- risk_post_candidates[grepl("dangerous or risky", risk_post_candidates)][1]
risk_post_3_col <- risk_post_candidates[grepl("haven’t been proven to work|haven't been proven to work", risk_post_candidates)][1]

cat("\nSelected PRE risk columns:\n")
print(c(risk_pre_1_col, risk_pre_2_col, risk_pre_3_col))

cat("\nSelected POST risk columns:\n")
print(c(risk_post_1_col, risk_post_2_col, risk_post_3_col))

# ---------------------------
# 8. Recode PRE and POST constructs
# ---------------------------

# ---- PRE Self-Efficacy (agreement, 6-point) ----
se_pre_1_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I am able to use GenAI tools when I have just the built-in help for assistance.]"
se_pre_2_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I don’t feel confident to use and learn GenAI tools, as I have other strengths.]"
se_pre_3_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I am able to use GenAI tools when someone shows me how to do it first.]"
se_pre_4_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I am able to use GenAI tools even when no one is around to help me if I need it.]"

# ---- PRE Trust (agreement, 6-point) ----
trust_pre_1_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I am confident in GenAI tools. I feel that it works well.]"
trust_pre_2_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [GenAI tools are reliable. I can count on it to be correct for my use cases.]"
trust_pre_3_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I feel safe that when I rely on GenAI, I will get the right answers.]"
trust_pre_4_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I like using GenAI for decision making.]"

# ---- POST Trust (agreement, 6-point) ----
trust_post_1_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I am confident in GenAI tools. I feel that it works well.]__2"
trust_post_2_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [GenAI tools are reliable. I can count on it to be correct for my use cases.]__2"
trust_post_3_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I feel safe that when I rely on GenAI, I will get the right answers.]__2"
trust_post_4_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I like using GenAI for decision making.]__2"

# ---- POST Self-Efficacy (agreement, 6-point) ----
se_post_1_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I am able to use GenAI tools when I have just the built-in help for assistance.]__2"
se_post_2_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I don’t feel confident to use and learn GenAI tools, as I have other strengths.]__2"
se_post_3_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I am able to use GenAI tools when someone shows me how to do it first.]__2"
se_post_4_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I am able to use GenAI tools even when no one is around to help me if I need it.]__2"

df <- df %>%
  mutate(
    # ---------- PRE Risk ----------
    risk_pre_1_raw = recode_agree6(.data[[risk_pre_1_col]]),
    risk_pre_2_raw = recode_agree6(.data[[risk_pre_2_col]]),
    risk_pre_3_raw = recode_agree6(.data[[risk_pre_3_col]]),
    
    # Higher = MORE risk tolerant
    risk_pre_1 = reverse6(risk_pre_1_raw),
    risk_pre_2 = reverse6(risk_pre_2_raw),
    risk_pre_3 = risk_pre_3_raw,
    
    # ---------- PRE Self-Efficacy ----------
    se_pre_1 = recode_agree6(.data[[se_pre_1_col]]),
    se_pre_2 = reverse6(recode_agree6(.data[[se_pre_2_col]])),
    se_pre_3 = recode_agree6(.data[[se_pre_3_col]]),
    se_pre_4 = recode_agree6(.data[[se_pre_4_col]]),
    
    # ---------- PRE Trust ----------
    trust_pre_1 = recode_agree6(.data[[trust_pre_1_col]]),
    trust_pre_2 = recode_agree6(.data[[trust_pre_2_col]]),
    trust_pre_3 = recode_agree6(.data[[trust_pre_3_col]]),
    trust_pre_4 = recode_agree6(.data[[trust_pre_4_col]]),
    
    # ---------- PRE BI ----------
    bi_pre_1 = recode_agree6(.data[[bi_pre_1_col]]),
    bi_pre_2 = recode_agree6(.data[[bi_pre_2_col]]),
    bi_pre_3 = recode_agree6(.data[[bi_pre_3_col]]),
    
    # ---------- POST Risk ----------
    risk_post_1_raw = recode_freq5(.data[[risk_post_1_col]]),
    risk_post_2_raw = recode_freq5(.data[[risk_post_2_col]]),
    risk_post_3_raw = recode_freq5(.data[[risk_post_3_col]]),
    
    # Higher = MORE risk tolerant
    risk_post_1 = reverse5(risk_post_1_raw),
    risk_post_2 = reverse5(risk_post_2_raw),
    risk_post_3 = risk_post_3_raw,
    
    # ---------- POST Trust ----------
    trust_post_1 = recode_agree6(.data[[trust_post_1_col]]),
    trust_post_2 = recode_agree6(.data[[trust_post_2_col]]),
    trust_post_3 = recode_agree6(.data[[trust_post_3_col]]),
    trust_post_4 = recode_agree6(.data[[trust_post_4_col]]),
    
    # ---------- POST Self-Efficacy ----------
    se_post_1 = recode_agree6(.data[[se_post_1_col]]),
    se_post_2 = reverse6(recode_agree6(.data[[se_post_2_col]])),
    se_post_3 = recode_agree6(.data[[se_post_3_col]]),
    se_post_4 = recode_agree6(.data[[se_post_4_col]]),
    
    # ---------- POST BI ----------
    bi_post_1 = recode_agree6(.data[[bi_post_1_col]]),
    bi_post_2 = recode_agree6(.data[[bi_post_2_col]]),
    bi_post_3 = recode_agree6(.data[[bi_post_3_col]])
  )

# Optional diagnostics for post-risk recoding
cat("\nPost-risk raw distributions:\n")
print(table(df[[risk_post_1_col]], useNA = "ifany"))
print(table(df[[risk_post_2_col]], useNA = "ifany"))
print(table(df[[risk_post_3_col]], useNA = "ifany"))

cat("\nRecoded post-risk summaries:\n")
print(summary(df %>% select(
  risk_post_1_raw, risk_post_2_raw, risk_post_3_raw,
  risk_post_1, risk_post_2, risk_post_3,
  risk_post_1_n = risk_post_1,
  risk_post_2_n = risk_post_2,
  risk_post_3_n = risk_post_3
)))

# ---------------------------
# 9. Construct composite scores
# ---------------------------

# PRE Risk uses 6-point agreement; POST Risk uses 5-point frequency.
# Normalize both to 0-1 before computing pre/post composites.

df <- df %>%
  mutate(
    # Normalize PRE risk items (1-6 to 0-1)
    risk_pre_1_n = norm01(risk_pre_1, 1, 6),
    risk_pre_2_n = norm01(risk_pre_2, 1, 6),
    risk_pre_3_n = norm01(risk_pre_3, 1, 6),
    
    # Normalize POST risk items (1-5 to 0-1)
    risk_post_1_n = norm01(risk_post_1, 1, 5),
    risk_post_2_n = norm01(risk_post_2, 1, 5),
    risk_post_3_n = norm01(risk_post_3, 1, 5),
    
    PreRiskTolerance = row_mean_safe(risk_pre_1_n, risk_pre_2_n, risk_pre_3_n),
    PostRiskTolerance = row_mean_safe(risk_post_1_n, risk_post_2_n, risk_post_3_n),
    
    PreSelfEfficacy = row_mean_safe(se_pre_1, se_pre_2, se_pre_3, se_pre_4),
    PostSelfEfficacy = row_mean_safe(se_post_1, se_post_2, se_post_3, se_post_4),
    
    PreTrust = row_mean_safe(trust_pre_1, trust_pre_2, trust_pre_3, trust_pre_4),
    PostTrust = row_mean_safe(trust_post_1, trust_post_2, trust_post_3, trust_post_4),
    
    PreBehavioralIntention = row_mean_safe(bi_pre_1, bi_pre_2, bi_pre_3),
    PostBehavioralIntention = row_mean_safe(bi_post_1, bi_post_2, bi_post_3),
    
    dRiskTolerance = PostRiskTolerance - PreRiskTolerance,
    dSelfEfficacy = PostSelfEfficacy - PreSelfEfficacy,
    dTrust = PostTrust - PreTrust,
    dBehavioralIntention = PostBehavioralIntention - PreBehavioralIntention
  )

# ---------------------------
# 10. Descriptives
# ---------------------------

desc_vars <- df %>%
  select(
    NudgeType, FollowCount, Motivation,
    PreRiskTolerance, PostRiskTolerance, dRiskTolerance,
    PreSelfEfficacy, PostSelfEfficacy, dSelfEfficacy,
    PreTrust, PostTrust, dTrust,
    PreBehavioralIntention, PostBehavioralIntention, dBehavioralIntention
  )

summary(desc_vars)

group_desc <- df %>%
  group_by(NudgeType) %>%
  summarise(
    n = n(),
    FollowCount_M = mean(FollowCount, na.rm = TRUE),
    FollowCount_SD = sd(FollowCount, na.rm = TRUE),
    Motivation_M = mean(Motivation, na.rm = TRUE),
    dRisk_M = mean(dRiskTolerance, na.rm = TRUE),
    dSE_M = mean(dSelfEfficacy, na.rm = TRUE),
    dTrust_M = mean(dTrust, na.rm = TRUE),
    dBI_M = mean(dBehavioralIntention, na.rm = TRUE),
    .groups = "drop"
  )

print(group_desc)

# ---------------------------
# 11. Reliability analysis
# ---------------------------

alpha_pre_risk  <- safe_alpha(df %>% select(risk_pre_1_n, risk_pre_2_n, risk_pre_3_n))
alpha_pre_se    <- safe_alpha(df %>% select(se_pre_1, se_pre_2, se_pre_3, se_pre_4))
alpha_pre_trust <- safe_alpha(df %>% select(trust_pre_1, trust_pre_2, trust_pre_3, trust_pre_4))
alpha_pre_bi    <- safe_alpha(df %>% select(bi_pre_1, bi_pre_2, bi_pre_3))
alpha_mot       <- safe_alpha(df %>% select(mot1, mot2, mot3))

alpha_post_risk  <- safe_alpha(df %>% select(risk_post_1_n, risk_post_2_n, risk_post_3_n))
alpha_post_se    <- safe_alpha(df %>% select(se_post_1, se_post_2, se_post_3, se_post_4))
alpha_post_trust <- safe_alpha(df %>% select(trust_post_1, trust_post_2, trust_post_3, trust_post_4))
alpha_post_bi    <- safe_alpha(df %>% select(bi_post_1, bi_post_2, bi_post_3))

cat("\nReliability (Cronbach's alpha)\n")
cat("Motivation:", fmt_alpha(alpha_mot), "\n")
cat("Pre Risk:", fmt_alpha(alpha_pre_risk), "\n")
cat("Post Risk:", fmt_alpha(alpha_post_risk), "\n")
cat("Pre Self-Efficacy:", fmt_alpha(alpha_pre_se), "\n")
cat("Post Self-Efficacy:", fmt_alpha(alpha_post_se), "\n")
cat("Pre Trust:", fmt_alpha(alpha_pre_trust), "\n")
cat("Post Trust:", fmt_alpha(alpha_post_trust), "\n")
cat("Pre Behavioral Intention:", fmt_alpha(alpha_pre_bi), "\n")
cat("Post Behavioral Intention:", fmt_alpha(alpha_post_bi), "\n")

# ---------------------------
# 12. Paired-sample t-tests
# ---------------------------

tt_risk <- t.test(df$PostRiskTolerance, df$PreRiskTolerance, paired = TRUE)
tt_se <- t.test(df$PostSelfEfficacy, df$PreSelfEfficacy, paired = TRUE)
tt_trust <- t.test(df$PostTrust, df$PreTrust, paired = TRUE)
tt_bi <- t.test(df$PostBehavioralIntention, df$PreBehavioralIntention, paired = TRUE)

d_risk <- effectsize::cohens_d(df$PostRiskTolerance, df$PreRiskTolerance, paired = TRUE)
d_se <- effectsize::cohens_d(df$PostSelfEfficacy, df$PreSelfEfficacy, paired = TRUE)
d_trust <- effectsize::cohens_d(df$PostTrust, df$PreTrust, paired = TRUE)
d_bi <- effectsize::cohens_d(df$PostBehavioralIntention, df$PreBehavioralIntention, paired = TRUE)

cat("\nPaired t-tests\n")
print(tt_risk)
print(d_risk)
print(tt_se)
print(d_se)
print(tt_trust)
print(d_trust)
print(tt_bi)
print(d_bi)

# ---------------------------
# 13. Correlation matrix
# ---------------------------

corr_data <- df %>%
  select(
    NudgeType, FollowCount, Motivation,
    PreRiskTolerance, PostRiskTolerance,
    PreSelfEfficacy, PostSelfEfficacy,
    PreTrust, PostTrust,
    PreBehavioralIntention, PostBehavioralIntention,
    dRiskTolerance, dSelfEfficacy, dTrust, dBehavioralIntention
  )

corr_mat <- cor(corr_data, use = "pairwise.complete.obs")
round(corr_mat, 2)

# ---------------------------
# 14. Main path model
# ---------------------------

model_main <- '
  # H1
  FollowCount ~ h1*NudgeType

  # H2 / H3
  PostRiskTolerance ~ h2a*FollowCount + h3a*NudgeType + c1*PreRiskTolerance
  PostSelfEfficacy ~ h2b*FollowCount + c2*PreSelfEfficacy
  PostTrust ~ h2c*FollowCount + h3b*NudgeType + c3*PreTrust

  # H4 / H5
  PostBehavioralIntention ~ h4a*PostRiskTolerance +
                            h4b*PostSelfEfficacy +
                            h4c*PostTrust +
                            h5*Motivation +
                            c4*PreBehavioralIntention

  ind_risk := h1 * h2a * h4a
  ind_se   := h1 * h2b * h4b
  ind_trust:= h1 * h2c * h4c
  ind_total := ind_risk + ind_se + ind_trust
'

fit_main <- sem(
  model_main,
  data = df,
  missing = "fiml",
  se = "bootstrap",
  bootstrap = 5000,
  fixed.x = FALSE
)

cat("\nMain model summary\n")
summary(fit_main, standardized = TRUE, fit.measures = TRUE, ci = TRUE, rsquare = TRUE)

std_main <- standardizedSolution(fit_main)
std_main %>% print(n = Inf)

params_main <- parameterEstimates(
  fit_main,
  standardized = TRUE,
  ci = TRUE,
  boot.ci.type = "perc"
)

params_main %>% print(n = Inf)

# ---------------------------
# 15. Change-score model (robustness check)
# ---------------------------

model_delta <- '
  # H1
  FollowCount ~ h1*NudgeType

  # H2 / H3
  dRiskTolerance ~ h2a*FollowCount + h3a*NudgeType + c1*PreRiskTolerance
  dSelfEfficacy ~ h2b*FollowCount + c2*PreSelfEfficacy
  dTrust ~ h2c*FollowCount + h3b*NudgeType + c3*PreTrust

  # H4 / H5
  dBehavioralIntention ~ h4a*dRiskTolerance +
                         h4b*dSelfEfficacy +
                         h4c*dTrust +
                         h5*Motivation +
                         c4*PreBehavioralIntention

  ind_risk := h1 * h2a * h4a
  ind_se   := h1 * h2b * h4b
  ind_trust:= h1 * h2c * h4c
  ind_total := ind_risk + ind_se + ind_trust
'

fit_delta <- sem(
  model_delta,
  data = df,
  missing = "fiml",
  se = "bootstrap",
  bootstrap = 5000,
  fixed.x = FALSE
)

cat("\nChange-score model summary\n")
summary(fit_delta, standardized = TRUE, fit.measures = TRUE, ci = TRUE, rsquare = TRUE)

params_delta <- parameterEstimates(
  fit_delta,
  standardized = TRUE,
  ci = TRUE,
  boot.ci.type = "perc"
)

params_delta %>% print(n = Inf)

# ---------------------------
# 16. Optional direct effect on BI
# ---------------------------

model_main_plus_direct <- '
  FollowCount ~ h1*NudgeType

  PostRiskTolerance ~ h2a*FollowCount + h3a*NudgeType + c1*PreRiskTolerance
  PostSelfEfficacy ~ h2b*FollowCount + c2*PreSelfEfficacy
  PostTrust ~ h2c*FollowCount + h3b*NudgeType + c3*PreTrust

  PostBehavioralIntention ~ h4a*PostRiskTolerance +
                            h4b*PostSelfEfficacy +
                            h4c*PostTrust +
                            h5*Motivation +
                            c4*PreBehavioralIntention +
                            direct*NudgeType

  ind_risk := h1 * h2a * h4a
  ind_se   := h1 * h2b * h4b
  ind_trust:= h1 * h2c * h4c
  ind_total := ind_risk + ind_se + ind_trust
  total_effect := direct + ind_total
'

fit_main_plus_direct <- sem(
  model_main_plus_direct,
  data = df,
  missing = "fiml",
  se = "bootstrap",
  bootstrap = 5000,
  fixed.x = FALSE
)

cat("\nMain model + direct effect summary\n")
summary(fit_main_plus_direct, standardized = TRUE, fit.measures = TRUE, ci = TRUE, rsquare = TRUE)

# ---------------------------
# 17. Visualize the model
# ---------------------------

semPaths(
  fit_main,
  what = "std",
  whatLabels = "std",
  layout = "tree",
  edge.label.cex = 0.9,
  sizeMan = 8,
  residuals = FALSE,
  intercepts = FALSE,
  nCharNodes = 0
)

png("sem_main_path_diagram.png", width = 1800, height = 1200, res = 200)
semPaths(
  fit_main,
  what = "std",
  whatLabels = "std",
  layout = "tree",
  edge.label.cex = 0.9,
  sizeMan = 8,
  residuals = FALSE,
  intercepts = FALSE,
  nCharNodes = 0
)
dev.off()

# ---------------------------
# 18. Export cleaned data and results
# ---------------------------

write_csv(df, "cleaned_sem_data.csv")
write_csv(params_main, "sem_main_parameter_estimates.csv")
write_csv(params_delta, "sem_delta_parameter_estimates.csv")

tt_summary <- tibble(
  construct = c("RiskTolerance", "SelfEfficacy", "Trust", "BehavioralIntention"),
  t = c(tt_risk$statistic, tt_se$statistic, tt_trust$statistic, tt_bi$statistic),
  df = c(tt_risk$parameter, tt_se$parameter, tt_trust$parameter, tt_bi$parameter),
  p = c(tt_risk$p.value, tt_se$p.value, tt_trust$p.value, tt_bi$p.value),
  mean_pre = c(
    mean(df$PreRiskTolerance, na.rm = TRUE),
    mean(df$PreSelfEfficacy, na.rm = TRUE),
    mean(df$PreTrust, na.rm = TRUE),
    mean(df$PreBehavioralIntention, na.rm = TRUE)
  ),
  mean_post = c(
    mean(df$PostRiskTolerance, na.rm = TRUE),
    mean(df$PostSelfEfficacy, na.rm = TRUE),
    mean(df$PostTrust, na.rm = TRUE),
    mean(df$PostBehavioralIntention, na.rm = TRUE)
  )
)

write_csv(tt_summary, "paired_t_tests_summary.csv")
write_csv(group_desc, "group_descriptives_by_nudge.csv")

cat("\nAnalysis complete.\n")

