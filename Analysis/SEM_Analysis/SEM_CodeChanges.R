############################################################
# SEM / Path Analysis for Security Nudge Study
# Variant: CodeChangesWithTool + Wilcoxon + Bandit summaries
# File: sem_analysis_codechanges.R
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
  str_replace_all("\u00a0", " ") |>
  str_replace_all("\\s+", " ") |>
  str_trim()

names(df_raw) <- make.unique(clean_names, sep = "__dup_")

glimpse(df_raw)
dim(df_raw)

dup_names <- names(df_raw)[grepl("__dup_", names(df_raw))]
if (length(dup_names) > 0) {
  cat("\nColumns made unique after cleaning:\n")
  print(dup_names)
}

output_dir <- "sem_outputs_codechanges"
if (!dir.exists(output_dir)) dir.create(output_dir)
cat("Output folder:", normalizePath(output_dir), "\n")

# ---------------------------
# 2. Helper functions
# ---------------------------

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

reverse6 <- function(x) ifelse(is.na(x), NA_real_, 7 - x)
reverse5 <- function(x) ifelse(is.na(x), NA_real_, 6 - x)

norm01 <- function(x, min_val, max_val) {
  ifelse(is.na(x), NA_real_, (x - min_val) / (max_val - min_val))
}

row_mean_safe <- function(...) {
  rowMeans(cbind(...), na.rm = TRUE)
}

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

safe_alpha <- function(dat) {
  dat2 <- dat %>% select(where(~ !all(is.na(.))))
  dat2 <- dat2 %>% select(where(~ dplyr::n_distinct(na.omit(.)) > 1))
  if (ncol(dat2) < 2) return(NULL)
  suppressWarnings(psych::alpha(dat2))
}

fmt_alpha <- function(a) {
  if (is.null(a)) "Not estimable (fewer than 2 varying items)" else round(a$total$raw_alpha, 3)
}

safe_logical_to_num <- function(x) {
  case_when(
    is.na(x) ~ NA_real_,
    x %in% c(TRUE, "TRUE", "True", "true", 1, "1") ~ 1,
    x %in% c(FALSE, "FALSE", "False", "false", 0, "0") ~ 0,
    TRUE ~ NA_real_
  )
}

# ---------------------------
# 3. Participant filtering
# ---------------------------

df <- df_raw %>%
  filter(!is.na(Nudge)) %>%
  filter(!is.na(`Number of tasks tool used`))

debrief_col <- "Initially, participants were informed that the purpose of this study was to assist in testing and debugging a tool under development. However, to minimize potential consciousness bias, the actual objective of the study was not disclosed at the outset. The true aim of the research is to investigate whether providing warnings about security issues in GenAI-generated code can encourage developers to adopt more security-aware behaviors, specifically, to assess whether such warnings prompt developers to review and address security concerns in the generated code. Additionally, the study examines whether different types of warnings lead to variations in developer behavior. This initial omission was intentional, as revealing the true purpose upfront could have led participants to consciously alter their behavior by actively checking for security issues, thereby compromising the validity of their natural coding practices. Do you still give us consent to use your answers for the purpose of this study? Please note that your eligibility to receive the incentive is not contingent upon how you respond to this question. Upon completing the survey, you will receive the compensation for this part of the study."

if (debrief_col %in% names(df)) {
  df <- df %>% filter(is.na(.data[[debrief_col]]) | .data[[debrief_col]] == "YES")
}

cat("Sample size after filtering:", nrow(df), "\n")

# ---------------------------
# 4. Core observed variables
# ---------------------------

df <- df %>%
  mutate(
    NudgeType = ifelse(Nudge == "B", 1, 0),
    FollowCount = as.numeric(`Number of tasks tool used`)
  )

# Build CodeChangesWithTool from task-level tool-use + changed flags
df <- df %>%
  mutate(
    task1_tool = safe_logical_to_num(`Task 1 tool use BOOL`),
    task1_changed = safe_logical_to_num(`Task 1 changed BOOL`),
    task2_tool = safe_logical_to_num(`Task 2 tool use BOOL`),
    task2_changed = safe_logical_to_num(`Task 2 changed BOOL`),
    task3_tool = safe_logical_to_num(`Task 3 tool use BOOL`),
    task3_changed = safe_logical_to_num(`Task 3 changed BOOL`),
    
    Task1_CodeChangesWithTool = ifelse(task1_tool == 1 & task1_changed == 1, 1, 0),
    Task2_CodeChangesWithTool = ifelse(task2_tool == 1 & task2_changed == 1, 1, 0),
    Task3_CodeChangesWithTool = ifelse(task3_tool == 1 & task3_changed == 1, 1, 0),
    
    CodeChangesWithTool = rowSums(cbind(
      Task1_CodeChangesWithTool,
      Task2_CodeChangesWithTool,
      Task3_CodeChangesWithTool
    ), na.rm = TRUE),
    
    AnyCodeChangeWithTool = ifelse(CodeChangesWithTool > 0, 1, 0)
  )

summary(df$CodeChangesWithTool)
table(df$Nudge, useNA = "ifany")

# ---------------------------
# 5. Bandit-related security outcome summaries
# ---------------------------

# Assumes diff columns already reflect post - pre or final - initial change.
# Interpret signs carefully in writeup according to your study convention.
df <- df %>%
  mutate(
    TotalIssueDiff = rowSums(cbind(
      `Task 1 issue count`, `Task 2 issue count`, `Task 3 issue count`
    ), na.rm = TRUE),
    
    TotalHighSeverityDiff = rowSums(cbind(
      `Task 1 high severity diff`, `Task 2 high severity diff`, `Task 3 high severity diff`
    ), na.rm = TRUE),
    
    TotalMedSeverityDiff = rowSums(cbind(
      `Task 1 med severity diff`, `Task 2 med severity diff`, `Task 3 med severity diff`
    ), na.rm = TRUE),
    
    TotalLowSeverityDiff = rowSums(cbind(
      `Task 1 low severity diff`, `Task 2 low severity diff`, `Task 3 low severity diff`
    ), na.rm = TRUE)
  )

bandit_by_nudge <- df %>%
  group_by(NudgeType) %>%
  summarise(
    n = n(),
    CodeChangesWithTool_M = mean(CodeChangesWithTool, na.rm = TRUE),
    CodeChangesWithTool_SD = sd(CodeChangesWithTool, na.rm = TRUE),
    AnyCodeChangeWithTool_Rate = mean(AnyCodeChangeWithTool, na.rm = TRUE),
    HighSeverityDiff_M = mean(TotalHighSeverityDiff, na.rm = TRUE),
    MedSeverityDiff_M = mean(TotalMedSeverityDiff, na.rm = TRUE),
    LowSeverityDiff_M = mean(TotalLowSeverityDiff, na.rm = TRUE),
    .groups = "drop"
  )

print(bandit_by_nudge)

codechange_bandit_assoc <- tibble(
  metric = c("TotalHighSeverityDiff", "TotalMedSeverityDiff", "TotalLowSeverityDiff"),
  cor_with_CodeChangesWithTool = c(
    cor(df$CodeChangesWithTool, df$TotalHighSeverityDiff, use = "pairwise.complete.obs"),
    cor(df$CodeChangesWithTool, df$TotalMedSeverityDiff, use = "pairwise.complete.obs"),
    cor(df$CodeChangesWithTool, df$TotalLowSeverityDiff, use = "pairwise.complete.obs")
  )
)

print(codechange_bandit_assoc)

# ---------------------------
# 6. Baseline motivation
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
# 7. Identify BI columns automatically
# ---------------------------

bi_cols <- names(df)[grepl(
  "intend to use GenAI tools in the future|plan to continue using GenAI tools|always try to use GenAI tools in my work",
  names(df)
)]

cat("\nBehavioral Intention columns detected:\n")
print(bi_cols)

if (length(bi_cols) != 6) {
  stop(paste0(
    "Expected 6 Behavioral Intention columns (3 pre + 3 post), but found ",
    length(bi_cols), "."
  ))
}

bi_pre_1_col <- bi_cols[1]
bi_pre_2_col <- bi_cols[2]
bi_pre_3_col <- bi_cols[3]
bi_post_1_col <- bi_cols[4]
bi_post_2_col <- bi_cols[5]
bi_post_3_col <- bi_cols[6]

# ---------------------------
# 8. Identify Risk columns automatically
# ---------------------------

risk_cols_all <- names(df)[grepl(
  "I avoid advanced GenAI features or options|I avoid activities when using GenAI tools that are dangerous or risky|Despite the risks I use GenAI features that haven’t been proven to work|Despite the risks I use GenAI features that haven't been proven to work",
  names(df)
)]

risk_pre_candidates <- risk_cols_all[sapply(df[risk_cols_all], is_agree6_col)]
risk_post_candidates <- risk_cols_all[sapply(df[risk_cols_all], is_freq5_col)]

if (length(risk_pre_candidates) != 3) {
  stop(paste0("Expected 3 PRE risk columns, found ", length(risk_pre_candidates), "."))
}
if (length(risk_post_candidates) != 3) {
  stop(paste0("Expected 3 POST risk columns, found ", length(risk_post_candidates), "."))
}

risk_pre_1_col <- risk_pre_candidates[grepl("advanced GenAI features or options", risk_pre_candidates)][1]
risk_pre_2_col <- risk_pre_candidates[grepl("dangerous or risky", risk_pre_candidates)][1]
risk_pre_3_col <- risk_pre_candidates[grepl("haven’t been proven to work|haven't been proven to work", risk_pre_candidates)][1]

risk_post_1_col <- risk_post_candidates[grepl("advanced GenAI features or options", risk_post_candidates)][1]
risk_post_2_col <- risk_post_candidates[grepl("dangerous or risky", risk_post_candidates)][1]
risk_post_3_col <- risk_post_candidates[grepl("haven’t been proven to work|haven't been proven to work", risk_post_candidates)][1]

# ---------------------------
# 9. Recode PRE and POST constructs
# ---------------------------

se_pre_1_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I am able to use GenAI tools when I have just the built-in help for assistance.]"
se_pre_2_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I don’t feel confident to use and learn GenAI tools, as I have other strengths.]"
se_pre_3_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I am able to use GenAI tools when someone shows me how to do it first.]"
se_pre_4_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I am able to use GenAI tools even when no one is around to help me if I need it.]"

trust_pre_1_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I am confident in GenAI tools. I feel that it works well.]"
trust_pre_2_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [GenAI tools are reliable. I can count on it to be correct for my use cases.]"
trust_pre_3_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I feel safe that when I rely on GenAI, I will get the right answers.]"
trust_pre_4_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I like using GenAI for decision making.]"

trust_post_1_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I am confident in GenAI tools. I feel that it works well.]__2"
trust_post_2_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [GenAI tools are reliable. I can count on it to be correct for my use cases.]__2"
trust_post_3_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I feel safe that when I rely on GenAI, I will get the right answers.]__2"
trust_post_4_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I like using GenAI for decision making.]__2"

se_post_1_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I am able to use GenAI tools when I have just the built-in help for assistance.]__2"
se_post_2_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I don’t feel confident to use and learn GenAI tools, as I have other strengths.]__2"
se_post_3_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I am able to use GenAI tools when someone shows me how to do it first.]__2"
se_post_4_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I am able to use GenAI tools even when no one is around to help me if I need it.]__2"

df <- df %>%
  mutate(
    risk_pre_1_raw = recode_agree6(.data[[risk_pre_1_col]]),
    risk_pre_2_raw = recode_agree6(.data[[risk_pre_2_col]]),
    risk_pre_3_raw = recode_agree6(.data[[risk_pre_3_col]]),
    
    risk_pre_1 = reverse6(risk_pre_1_raw),
    risk_pre_2 = reverse6(risk_pre_2_raw),
    risk_pre_3 = risk_pre_3_raw,
    
    se_pre_1 = recode_agree6(.data[[se_pre_1_col]]),
    se_pre_2 = reverse6(recode_agree6(.data[[se_pre_2_col]])),
    se_pre_3 = recode_agree6(.data[[se_pre_3_col]]),
    se_pre_4 = recode_agree6(.data[[se_pre_4_col]]),
    
    trust_pre_1 = recode_agree6(.data[[trust_pre_1_col]]),
    trust_pre_2 = recode_agree6(.data[[trust_pre_2_col]]),
    trust_pre_3 = recode_agree6(.data[[trust_pre_3_col]]),
    trust_pre_4 = recode_agree6(.data[[trust_pre_4_col]]),
    
    bi_pre_1 = recode_agree6(.data[[bi_pre_1_col]]),
    bi_pre_2 = recode_agree6(.data[[bi_pre_2_col]]),
    bi_pre_3 = recode_agree6(.data[[bi_pre_3_col]]),
    
    risk_post_1_raw = recode_freq5(.data[[risk_post_1_col]]),
    risk_post_2_raw = recode_freq5(.data[[risk_post_2_col]]),
    risk_post_3_raw = recode_freq5(.data[[risk_post_3_col]]),
    
    risk_post_1 = reverse5(risk_post_1_raw),
    risk_post_2 = reverse5(risk_post_2_raw),
    risk_post_3 = risk_post_3_raw,
    
    trust_post_1 = recode_agree6(.data[[trust_post_1_col]]),
    trust_post_2 = recode_agree6(.data[[trust_post_2_col]]),
    trust_post_3 = recode_agree6(.data[[trust_post_3_col]]),
    trust_post_4 = recode_agree6(.data[[trust_post_4_col]]),
    
    se_post_1 = recode_agree6(.data[[se_post_1_col]]),
    se_post_2 = reverse6(recode_agree6(.data[[se_post_2_col]])),
    se_post_3 = recode_agree6(.data[[se_post_3_col]]),
    se_post_4 = recode_agree6(.data[[se_post_4_col]]),
    
    bi_post_1 = recode_agree6(.data[[bi_post_1_col]]),
    bi_post_2 = recode_agree6(.data[[bi_post_2_col]]),
    bi_post_3 = recode_agree6(.data[[bi_post_3_col]])
  )

# ---------------------------
# 10. Construct composite scores
# ---------------------------

df <- df %>%
  mutate(
    risk_pre_1_n = norm01(risk_pre_1, 1, 6),
    risk_pre_2_n = norm01(risk_pre_2, 1, 6),
    risk_pre_3_n = norm01(risk_pre_3, 1, 6),
    
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
# 11. Descriptives
# ---------------------------

desc_vars <- df %>%
  select(
    NudgeType, CodeChangesWithTool, Motivation,
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
    CodeChangesWithTool_M = mean(CodeChangesWithTool, na.rm = TRUE),
    CodeChangesWithTool_SD = sd(CodeChangesWithTool, na.rm = TRUE),
    Motivation_M = mean(Motivation, na.rm = TRUE),
    dRisk_M = mean(dRiskTolerance, na.rm = TRUE),
    dSE_M = mean(dSelfEfficacy, na.rm = TRUE),
    dTrust_M = mean(dTrust, na.rm = TRUE),
    dBI_M = mean(dBehavioralIntention, na.rm = TRUE),
    HighSeverityDiff_M = mean(TotalHighSeverityDiff, na.rm = TRUE),
    MedSeverityDiff_M = mean(TotalMedSeverityDiff, na.rm = TRUE),
    LowSeverityDiff_M = mean(TotalLowSeverityDiff, na.rm = TRUE),
    .groups = "drop"
  )

print(group_desc)

# ---------------------------
# 12. Reliability analysis
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
# 13. Paired t-tests + Wilcoxon signed-rank tests
# ---------------------------

tt_risk  <- t.test(df$PostRiskTolerance, df$PreRiskTolerance, paired = TRUE)
tt_se    <- t.test(df$PostSelfEfficacy, df$PreSelfEfficacy, paired = TRUE)
tt_trust <- t.test(df$PostTrust, df$PreTrust, paired = TRUE)
tt_bi    <- t.test(df$PostBehavioralIntention, df$PreBehavioralIntention, paired = TRUE)

wil_risk  <- wilcox.test(df$PostRiskTolerance, df$PreRiskTolerance, paired = TRUE, exact = FALSE)
wil_se    <- wilcox.test(df$PostSelfEfficacy, df$PreSelfEfficacy, paired = TRUE, exact = FALSE)
wil_trust <- wilcox.test(df$PostTrust, df$PreTrust, paired = TRUE, exact = FALSE)
wil_bi    <- wilcox.test(df$PostBehavioralIntention, df$PreBehavioralIntention, paired = TRUE, exact = FALSE)

d_risk  <- effectsize::cohens_d(df$PostRiskTolerance, df$PreRiskTolerance, paired = TRUE)
d_se    <- effectsize::cohens_d(df$PostSelfEfficacy, df$PreSelfEfficacy, paired = TRUE)
d_trust <- effectsize::cohens_d(df$PostTrust, df$PreTrust, paired = TRUE)
d_bi    <- effectsize::cohens_d(df$PostBehavioralIntention, df$PreBehavioralIntention, paired = TRUE)

cat("\nPaired t-tests\n")
print(tt_risk);  print(d_risk)
print(tt_se);    print(d_se)
print(tt_trust); print(d_trust)
print(tt_bi);    print(d_bi)

cat("\nWilcoxon signed-rank tests\n")
print(wil_risk)
print(wil_se)
print(wil_trust)
print(wil_bi)

# ---------------------------
# 14. Correlation matrix
# ---------------------------

corr_data <- df %>%
  select(
    NudgeType, CodeChangesWithTool, Motivation,
    PreRiskTolerance, PostRiskTolerance,
    PreSelfEfficacy, PostSelfEfficacy,
    PreTrust, PostTrust,
    PreBehavioralIntention, PostBehavioralIntention,
    dRiskTolerance, dSelfEfficacy, dTrust, dBehavioralIntention,
    TotalHighSeverityDiff, TotalMedSeverityDiff, TotalLowSeverityDiff
  )

corr_mat <- cor(corr_data, use = "pairwise.complete.obs")
print(round(corr_mat, 2))

# ---------------------------
# 15. Main path model
# Replace FollowCount with CodeChangesWithTool
# ---------------------------

model_main <- '
  # H1-style path
  CodeChangesWithTool ~ h1*NudgeType

  # H2 / H3
  PostRiskTolerance ~ h2a*CodeChangesWithTool + h3a*NudgeType + c1*PreRiskTolerance
  PostSelfEfficacy ~ h2b*CodeChangesWithTool + c2*PreSelfEfficacy
  PostTrust ~ h2c*CodeChangesWithTool + h3b*NudgeType + c3*PreTrust

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
print(std_main)

params_main <- parameterEstimates(
  fit_main,
  standardized = TRUE,
  ci = TRUE,
  boot.ci.type = "perc"
)
print(params_main)

# ---------------------------
# 16. Change-score model
# Replace FollowCount with CodeChangesWithTool
# ---------------------------

model_delta <- '
  CodeChangesWithTool ~ h1*NudgeType

  dRiskTolerance ~ h2a*CodeChangesWithTool + h3a*NudgeType + c1*PreRiskTolerance
  dSelfEfficacy ~ h2b*CodeChangesWithTool + c2*PreSelfEfficacy
  dTrust ~ h2c*CodeChangesWithTool + h3b*NudgeType + c3*PreTrust

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
print(params_delta)

# ---------------------------
# 17. Optional direct effect model
# ---------------------------

model_main_plus_direct <- '
  CodeChangesWithTool ~ h1*NudgeType

  PostRiskTolerance ~ h2a*CodeChangesWithTool + h3a*NudgeType + c1*PreRiskTolerance
  PostSelfEfficacy ~ h2b*CodeChangesWithTool + c2*PreSelfEfficacy
  PostTrust ~ h2c*CodeChangesWithTool + h3b*NudgeType + c3*PreTrust

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
# 18. Path diagram
# ---------------------------

png(file.path(output_dir, "sem_main_path_diagram_codechanges.png"), width = 1800, height = 1200, res = 200)
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
# 19. Export outputs
# ---------------------------

tt_summary <- tibble(
  construct = c("RiskTolerance", "SelfEfficacy", "Trust", "BehavioralIntention"),
  t = c(tt_risk$statistic, tt_se$statistic, tt_trust$statistic, tt_bi$statistic),
  df_stat = c(tt_risk$parameter, tt_se$parameter, tt_trust$parameter, tt_bi$parameter),
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

wilcox_summary <- tibble(
  construct = c("RiskTolerance", "SelfEfficacy", "Trust", "BehavioralIntention"),
  V = c(wil_risk$statistic, wil_se$statistic, wil_trust$statistic, wil_bi$statistic),
  p = c(wil_risk$p.value, wil_se$p.value, wil_trust$p.value, wil_bi$p.value)
)

write_csv(df, file.path(output_dir, "cleaned_sem_data_codechanges.csv"))
write_csv(params_main, file.path(output_dir, "sem_main_parameter_estimates_codechanges.csv"))
write_csv(params_delta, file.path(output_dir, "sem_delta_parameter_estimates_codechanges.csv"))
write_csv(tt_summary, file.path(output_dir, "paired_t_tests_summary_codechanges.csv"))
write_csv(wilcox_summary, file.path(output_dir, "wilcoxon_summary_codechanges.csv"))
write_csv(group_desc, file.path(output_dir, "group_descriptives_by_nudge_codechanges.csv"))
write_csv(bandit_by_nudge, file.path(output_dir, "bandit_by_nudge_codechanges.csv"))
write_csv(codechange_bandit_assoc, file.path(output_dir, "codechange_bandit_associations.csv"))

cat("\nFiles written to:\n")
print(normalizePath(output_dir))
print(list.files(output_dir))

cat("\nAnalysis complete.\n")