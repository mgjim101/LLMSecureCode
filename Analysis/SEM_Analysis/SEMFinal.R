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
base_path <- "~/Desktop/work/Fard Lab/Analysis/SEM_Analysis"

df_raw <- read_csv(file.path(base_path, "participant_profiles_schema.csv"))

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

# FIX 1: Safe correlation helper — returns NA if either variable has zero variance
safe_cor <- function(x, y) {
  if (sd(x, na.rm = TRUE) == 0 || sd(y, na.rm = TRUE) == 0) return(NA_real_)
  cor(x, y, use = "pairwise.complete.obs")
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

# FIX A: Compute TotalNewVulns by parsing issue change kind columns
df <- df %>%
  mutate(
    TotalNewVulns = str_count(tolower(replace_na(`Task 1 issue change kind [fixed, common, new]`, "")), "new") +
      str_count(tolower(replace_na(`Task 2 issue change kind [fixed, common, new]`, "")), "new") +
      str_count(tolower(replace_na(`Task 3 issue change kind [fixed, common, new]`, "")), "new")
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

# FIX 1 APPLIED: Use safe_cor() to avoid warning when a variable has zero variance
codechange_bandit_assoc <- tibble(
  metric = c("TotalHighSeverityDiff", "TotalMedSeverityDiff", "TotalLowSeverityDiff"),
  cor_with_CodeChangesWithTool = c(
    safe_cor(df$CodeChangesWithTool, df$TotalHighSeverityDiff),
    safe_cor(df$CodeChangesWithTool, df$TotalMedSeverityDiff),
    safe_cor(df$CodeChangesWithTool, df$TotalLowSeverityDiff)
  )
)

print(codechange_bandit_assoc)

# ---------------------------
# 5b. CWE / Bandit Issue Analysis (NEW)
# ---------------------------

cat("\n=== CWE / Bandit Issue Analysis ===\n")

# Bandit ID to CWE lookup table
bandit_cwe_map <- tribble(
  ~bandit_id, ~bandit_name,                                ~cwe,                                              ~severity,  ~task,
  "B701",     "jinja2_autoescape_false",                   "CWE-80 (XSS via template injection)",             "HIGH",     1L,
  "B311",     "blacklist (random)",                        "CWE-330 (Insufficient Randomness)",               "LOW",      2L,
  "B404",     "blacklist (subprocess import)",             "CWE-78 (OS Command Injection - import)",          "LOW",      3L,
  "B602",     "subprocess_popen_with_shell_equals_true",   "CWE-78 (OS Command Injection)",                   "HIGH",     3L,
  "B603",     "subprocess_without_shell_equals_true",      "CWE-78 (OS Command Injection - no shell)",        "LOW",      3L,
  "B607",     "start_process_with_partial_path",           "CWE-426 (Untrusted Search Path)",                 "LOW",      3L,
  "B105",     "hardcoded_password_string",                 "CWE-259 (Use of Hard-coded Password)",            "LOW",      3L
)

# Parse per-participant per-task issues into long format
parse_bandit_issues <- function(df_in) {
  result <- list()
  for (task_num in 1:3) {
    id_col     <- paste0("Task ", task_num, " issue type ID")
    change_col <- paste0("Task ", task_num, " issue change kind [fixed, common, new]")
    
    for (i in seq_len(nrow(df_in))) {
      ids_raw     <- df_in[[id_col]][i]
      change_raw  <- df_in[[change_col]][i]
      nudge_val   <- df_in[["Nudge"]][i]
      
      if (is.na(ids_raw)) next
      
      ids     <- str_trim(str_split(ids_raw,     ",")[[1]])
      changes <- str_trim(str_split(replace_na(change_raw, ""), ",")[[1]])
      
      for (j in seq_along(ids)) {
        result[[length(result) + 1]] <- tibble(
          nudge      = nudge_val,
          task       = task_num,
          bandit_id  = ids[j],
          change_kind = ifelse(j <= length(changes) && changes[j] != "", changes[j], NA_character_)
        )
      }
    }
  }
  bind_rows(result)
}

issue_long <- parse_bandit_issues(df)

# Join with CWE map
issue_long <- issue_long %>%
  left_join(bandit_cwe_map, by = c("bandit_id", "task"))

cat("\nBandit ID overall frequencies:\n")
bandit_freq_overall <- issue_long %>%
  count(bandit_id, bandit_name, cwe, severity, name = "total_occurrences") %>%
  arrange(desc(total_occurrences))
print(bandit_freq_overall)

cat("\nBandit ID frequencies by Nudge group:\n")
bandit_freq_by_nudge <- issue_long %>%
  count(bandit_id, cwe, nudge) %>%
  pivot_wider(names_from = nudge, values_from = n, values_fill = 0, names_prefix = "Nudge_") %>%
  arrange(desc(Nudge_A + Nudge_B))
print(bandit_freq_by_nudge)

cat("\nChange kind (fixed / common / new) by Nudge group:\n")
change_by_nudge <- issue_long %>%
  filter(!is.na(change_kind)) %>%
  count(change_kind, nudge) %>%
  pivot_wider(names_from = nudge, values_from = n, values_fill = 0, names_prefix = "Nudge_")
print(change_by_nudge)

cat("\nBandit ID x Change kind cross-tabulation:\n")
bandit_change_cross <- issue_long %>%
  filter(!is.na(change_kind)) %>%
  count(bandit_id, change_kind) %>%
  pivot_wider(names_from = change_kind, values_from = n, values_fill = 0)
print(bandit_change_cross)

cat("\nBandit ID x Change kind by Nudge group:\n")
bandit_change_nudge <- issue_long %>%
  filter(!is.na(change_kind)) %>%
  count(bandit_id, change_kind, nudge) %>%
  pivot_wider(names_from = nudge, values_from = n, values_fill = 0, names_prefix = "Nudge_")
print(bandit_change_nudge)

# Per-participant counts for correlation analysis
df <- df %>%
  mutate(
    n_issues_fixed = str_count(
      tolower(paste(
        replace_na(`Task 1 issue change kind [fixed, common, new]`, ""),
        replace_na(`Task 2 issue change kind [fixed, common, new]`, ""),
        replace_na(`Task 3 issue change kind [fixed, common, new]`, "")
      )), "fixed"),
    n_issues_common = str_count(
      tolower(paste(
        replace_na(`Task 1 issue change kind [fixed, common, new]`, ""),
        replace_na(`Task 2 issue change kind [fixed, common, new]`, ""),
        replace_na(`Task 3 issue change kind [fixed, common, new]`, "")
      )), "common"),
    n_issues_new = TotalNewVulns
  )

cat("\nCorrelations: CodeChangesWithTool vs issue outcomes\n")
cwe_cor_table <- tibble(
  metric = c("n_issues_fixed", "n_issues_common", "n_issues_new",
             "TotalHighSeverityDiff", "TotalLowSeverityDiff"),
  cor_with_CodeChangesWithTool = c(
    safe_cor(df$CodeChangesWithTool, df$n_issues_fixed),
    safe_cor(df$CodeChangesWithTool, df$n_issues_common),
    safe_cor(df$CodeChangesWithTool, df$n_issues_new),
    safe_cor(df$CodeChangesWithTool, df$TotalHighSeverityDiff),
    safe_cor(df$CodeChangesWithTool, df$TotalLowSeverityDiff)
  )
)
print(cwe_cor_table)

cat("\nDescriptives: issues fixed/common/new by Nudge group\n")
issue_desc_by_nudge <- df %>%
  group_by(NudgeType) %>%
  summarise(
    n = n(),
    fixed_M  = mean(n_issues_fixed,  na.rm = TRUE),
    fixed_SD = sd(n_issues_fixed,    na.rm = TRUE),
    common_M = mean(n_issues_common, na.rm = TRUE),
    new_M    = mean(n_issues_new,    na.rm = TRUE),
    new_SD   = sd(n_issues_new,      na.rm = TRUE),
    .groups = "drop"
  )
print(issue_desc_by_nudge)

# ---------------------------
# 6. Baseline motivation
# ---------------------------

mot1_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I explore GenAI technology even if it's not critical to my job.]"
mot2_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I use GenAI tools because it's a way for me to look good with peers.]"
mot3_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [Its fun to try new GenAI technology that is not yet available to everyone such as being a participant in beta testing programs.]"

# Safety check: verify columns exist after name cleaning
missing_mot <- c(mot1_col, mot2_col, mot3_col)[!c(mot1_col, mot2_col, mot3_col) %in% names(df)]
if (length(missing_mot) > 0) {
  mot_candidates <- names(df)[grepl(
    "explore GenAI technology even if|look good with peers|fun to try new GenAI technology",
    names(df), ignore.case = TRUE
  )]
  cat("\nMotivation columns detected by fallback:\n")
  print(mot_candidates)
  if (length(mot_candidates) != 3) stop(paste0("Expected 3 Motivation columns, found ", length(mot_candidates)))
  mot1_col <- mot_candidates[grepl("explore GenAI technology", mot_candidates, ignore.case = TRUE)][1]
  mot2_col <- mot_candidates[grepl("look good with peers",     mot_candidates, ignore.case = TRUE)][1]
  mot3_col <- mot_candidates[grepl("fun to try new GenAI",     mot_candidates, ignore.case = TRUE)][1]
}

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
# 8. Identify Risk columns
# ---------------------------

risk_pre_1_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I avoid advanced GenAI features or options.]"
risk_pre_2_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I avoid activities when using GenAI tools that are dangerous or risky.]"
risk_pre_3_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [Despite the risks I use GenAI features that haven\u2019t been proven to work.]"

risk_post_1_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I avoid advanced GenAI features or options.]__dup_1"
risk_post_2_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I avoid activities when using GenAI tools that are dangerous or risky.]__dup_1"
risk_post_3_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [Despite the risks I use GenAI features that haven\u2019t been proven to work.]__dup_1"

missing_risk <- c(risk_pre_1_col, risk_pre_2_col, risk_pre_3_col,
                  risk_post_1_col, risk_post_2_col, risk_post_3_col)
missing_risk <- missing_risk[!missing_risk %in% names(df)]
if (length(missing_risk) > 0) {
  cat("\nMissing risk columns:\n")
  print(missing_risk)
  stop("One or more risk columns not found. Check __dup_ suffix numbering.")
}

cat("\nRisk columns verified OK\n")

# ---------------------------
# 9. Recode PRE and POST constructs
# ---------------------------

se_pre_1_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I am able to use GenAI tools when I have just the built-in help for assistance.]"
se_pre_2_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I don\u2019t feel confident to use and learn GenAI tools, as I have other strengths.]"
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
se_post_2_col <- "Please assess the following statements based on your own thoughts and experiences working with GenAI-based coding tools. [I don\u2019t feel confident to use and learn GenAI tools, as I have other strengths.]__2"
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
# 13. PRE-POST TESTS BY NUDGE GROUP — SEPARATELY (CAVEAT FIX)
# ---------------------------

run_paired_tests <- function(data, pre, post, label) {
  
  data <- data %>% filter(!is.na(.data[[pre]]), !is.na(.data[[post]]))
  
  if (nrow(data) < 5) return(NULL)
  
  tt <- t.test(data[[post]], data[[pre]], paired = TRUE)
  wil <- suppressWarnings(
    wilcox.test(data[[post]], data[[pre]], paired = TRUE, exact = FALSE)
  )
  d <- suppressWarnings(
    effectsize::cohens_d(data[[post]], data[[pre]], paired = TRUE)
  )
  
  tibble(
    construct   = label,
    n           = nrow(data),
    mean_pre    = mean(data[[pre]],  na.rm = TRUE),
    mean_post   = mean(data[[post]], na.rm = TRUE),
    t           = tt$statistic,
    df          = tt$parameter,
    p_t         = tt$p.value,
    wilcox_V    = wil$statistic,
    p_wilcox    = wil$p.value,
    cohens_d    = d$Cohens_d
  )
}

# Split groups
df_A <- df %>% filter(NudgeType == 0)
df_B <- df %>% filter(NudgeType == 1)

paired_results_A <- bind_rows(
  run_paired_tests(df_A, "PreRiskTolerance",       "PostRiskTolerance",       "RiskTolerance"),
  run_paired_tests(df_A, "PreSelfEfficacy",        "PostSelfEfficacy",        "SelfEfficacy"),
  run_paired_tests(df_A, "PreTrust",               "PostTrust",               "Trust"),
  run_paired_tests(df_A, "PreBehavioralIntention", "PostBehavioralIntention", "BehavioralIntention")
) %>% mutate(Group = "Nudge A")

paired_results_B <- bind_rows(
  run_paired_tests(df_B, "PreRiskTolerance",       "PostRiskTolerance",       "RiskTolerance"),
  run_paired_tests(df_B, "PreSelfEfficacy",        "PostSelfEfficacy",        "SelfEfficacy"),
  run_paired_tests(df_B, "PreTrust",               "PostTrust",               "Trust"),
  run_paired_tests(df_B, "PreBehavioralIntention", "PostBehavioralIntention", "BehavioralIntention")
) %>% mutate(Group = "Nudge B")

# CAVEAT FIX: bind both groups and keep Group column — this is the correct export
paired_results <- bind_rows(paired_results_A, paired_results_B) %>%
  select(Group, construct, n, mean_pre, mean_post, t, df, p_t, wilcox_V, p_wilcox, cohens_d)

print(paired_results)

# ---------------------------
# 14. BETWEEN-GROUP TESTS (A vs B)
# ---------------------------

df <- df %>%
  mutate(NudgeType_f = factor(NudgeType, levels = c(0, 1), labels = c("A", "B")))

run_between_tests <- function(var, label) {
  
  df2 <- df %>% filter(!is.na(.data[[var]]))
  
  tt <- t.test(as.formula(paste(var, "~ NudgeType_f")), data = df2)
  mw <- suppressWarnings(
    wilcox.test(as.formula(paste(var, "~ NudgeType_f")), data = df2)
  )
  d <- suppressWarnings(
    effectsize::cohens_d(as.formula(paste(var, "~ NudgeType_f")), data = df2)
  )
  
  tibble(
    variable  = label,
    mean_A    = mean(df2 %>% filter(NudgeType == 0) %>% pull(var), na.rm = TRUE),
    mean_B    = mean(df2 %>% filter(NudgeType == 1) %>% pull(var), na.rm = TRUE),
    t         = tt$statistic,
    df        = tt$parameter,
    p_t       = tt$p.value,
    wilcox_W  = mw$statistic,
    p_wilcox  = mw$p.value,
    cohens_d  = d$Cohens_d
  )
}

# FIX B: All required single-measure variables included
between_results <- bind_rows(
  run_between_tests("FollowCount",           "AvgToolUseCount"),
  run_between_tests("CodeChangesWithTool",   "CodeChangesWithTool"),
  run_between_tests("TotalNewVulns",         "TotalNewVulnerabilities"),
  run_between_tests("Motivation",            "Motivation"),
  run_between_tests("TotalHighSeverityDiff", "HighSeverityDiff"),
  run_between_tests("TotalMedSeverityDiff",  "MedSeverityDiff"),
  run_between_tests("TotalLowSeverityDiff",  "LowSeverityDiff"),
  run_between_tests("n_issues_fixed",        "IssuesFixed"),
  run_between_tests("n_issues_new",          "IssuesNew")
)

print(between_results)

# ---------------------------
# 14. Correlation matrix
# ---------------------------

# FIX 4: Drop zero-variance columns before computing the full correlation matrix
corr_data <- df %>%
  select(
    NudgeType, CodeChangesWithTool, Motivation,
    PreRiskTolerance, PostRiskTolerance,
    PreSelfEfficacy, PostSelfEfficacy,
    PreTrust, PostTrust,
    PreBehavioralIntention, PostBehavioralIntention,
    dRiskTolerance, dSelfEfficacy, dTrust, dBehavioralIntention,
    TotalHighSeverityDiff, TotalMedSeverityDiff, TotalLowSeverityDiff
  ) %>%
  select(where(~ sd(., na.rm = TRUE) > 0))

corr_mat <- cor(corr_data, use = "pairwise.complete.obs")
print(round(corr_mat, 2))

# ---------------------------
# 15. Main path model
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

write_csv(df, file.path(output_dir, "cleaned_sem_data_codechanges.csv"))
write_csv(params_main, file.path(output_dir, "sem_main_parameter_estimates_codechanges.csv"))
write_csv(params_delta, file.path(output_dir, "sem_delta_parameter_estimates_codechanges.csv"))

# CAVEAT FIX: paired_results now has Group column, Cohen's d, both p-values — per group
write_csv(paired_results,         file.path(output_dir, "paired_tests_by_nudge.csv"))
write_csv(between_results,        file.path(output_dir, "between_group_tests.csv"))
write_csv(group_desc,             file.path(output_dir, "group_descriptives_by_nudge_codechanges.csv"))
write_csv(bandit_by_nudge,        file.path(output_dir, "bandit_by_nudge_codechanges.csv"))
write_csv(codechange_bandit_assoc, file.path(output_dir, "codechange_bandit_associations.csv"))

# NEW: CWE / Bandit issue exports
write_csv(bandit_freq_overall,    file.path(output_dir, "cwe_bandit_freq_overall.csv"))
write_csv(bandit_freq_by_nudge,   file.path(output_dir, "cwe_bandit_freq_by_nudge.csv"))
write_csv(change_by_nudge,        file.path(output_dir, "cwe_change_kind_by_nudge.csv"))
write_csv(bandit_change_cross,    file.path(output_dir, "cwe_bandit_change_crosstab.csv"))
write_csv(bandit_change_nudge,    file.path(output_dir, "cwe_bandit_change_by_nudge.csv"))
write_csv(cwe_cor_table,          file.path(output_dir, "cwe_correlations_with_codechanges.csv"))
write_csv(issue_desc_by_nudge,    file.path(output_dir, "cwe_issue_descriptives_by_nudge.csv"))

cat("\nFiles written to:\n")
print(normalizePath(output_dir))
print(list.files(output_dir))