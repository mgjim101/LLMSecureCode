
# **SecureCode Study**

  

An interactive Streamlit application for conducting a user study on developers’ willingness to run security checks (Bandit) when nudged. Participants complete three code-completion tasks, view LLM-generated suggestions, submit their own code, receive a security nudge, optionally run a vulnerability scan and edit, and then move on. All interactions are logged to a SQLite database and an admin dashboard lets you explore the results.

----------

## Features

-   **Three Code Tasks**
    
    Participants solve three small coding exercises loaded from JSON.
    
-   **LLM-Suggested Snippets**
    
    For each task, three pre-compiled code suggestions are shown in read-only text areas above the editor.
    
-   **Inline Monaco Editor**
    
    A syntax-highlighted, dark-themed Monaco editor for participants to write and refine their code.
    
-   **Security Nudge & Scan**
    
    After first submission, a customizable nudge (A or B) prompts the user to run Bandit.
    
    -   **Run Security Tool**  runs a Bandit scan and shows the JSON report.
        
    -   **Skip Tool**  proceeds immediately to the next task.
        
    
-   **Optional Code Editing**
    
    Post-scan, participants can either:
    
    1.  **Edit Code**  in the same Monaco editor and submit the revised version.
        
    2.  **Submit As-Is**  without further edits.
        
    
-   **Interaction Logging**
    
    Every step is recorded in  interactions.db:
    
    -   Participant & group
        
    -   Raw code before and after edits
        
    -   Timestamps for start, submit, tool decision, scan decision, edit start & end
        
    -   Whether the tool was run
        
    
-   **Admin Dashboard**
    
    A second Streamlit app (admin.py) to browse the database in a table, filter by participant or nudge, compute solve/edit times, and visualize tool usage by nudge.
    

----------

## ** Repository Structure**

```
.
├── app.py                  # Main Streamlit experiment
├── admin.py                # Streamlit dashboard for results
├── interactions.db         # SQLite DB (auto-generated)
├── requirements.txt        # Python dependencies
├── data/
│   ├── tasks/
│   │   ├── task1.json
│   │   ├── task2.json
│   │   └── task3.json
│   ├── nudges/
│   │   ├── nudgeA.json
│   │   └── nudgeB.json
│   └── suggestions/
│       ├── task1.json
│       ├── task2.json
│       └── task3.json
└── README.md
```

  

----------

## ** Getting Started**

1.  **Clone the repo**
    

```
git clone https://github.com/your-org/securecode-study.git
cd securecode-study
```

1.    
    
2.  **Install dependencies**
    

```
pip install -r requirements.txt
```

2.    
    
3.  **Run the experiment app**
    

```
streamlit run app.py
```

3.  -   Enter a  **participant ID**  (1–30).
        
    -   Complete each task in sequence.
        
    
4.  **Explore results**
    

```
streamlit run admin.py
```

4.  -   View raw interactions, solve/edit durations, and a bar chart of tool usage by nudge (A vs. B).
        
    

----------

## ** Data Formats**

-   **Task JSON** (data/tasks/taskX.json):
    

```
{
  "id": 1,
  "title": "Login Function",
  "code": "# TODO: Complete this function\n def login(username, password):\n     pass"
}
```

-     
    
-   **Nudge JSON** (data/nudges/nudgeA.json / nudgeB.json):
    

```
{ "message": "LLM code can contain security issues. Run a security tool?" }
```

-     
    
-   **Suggestions JSON** (data/suggestions/taskX.json):
    

```
[
  "# suggestion 1 ...",
  "# suggestion 2 ...",
  "# suggestion 3 ..."
]
```

  

