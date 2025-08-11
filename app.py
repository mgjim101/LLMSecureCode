import streamlit as st
import os, json, subprocess, tempfile
from datetime import datetime
from streamlit_ace import st_ace
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# ─── Full-width Styling ───
st.markdown("""
    <style>
    .block-container {
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 100% !important;
    }
    textarea, .ace_editor {
        width: 100% !important;
    }
    </style>
""", unsafe_allow_html=True)

# ─── PostgreSQL Setup ───
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_NAME     = os.getenv("DB_NAME", "your_db_name")
DB_USER     = os.getenv("DB_USER", "your_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "your_password")
DB_PORT     = os.getenv("DB_PORT", "5432")

conn = psycopg2.connect(
    host=DB_HOST,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    port=DB_PORT
)
c = conn.cursor()

# ─── Create Table ───
# — participants —
c.execute("""
CREATE TABLE IF NOT EXISTS participants (
  participant_id   INTEGER PRIMARY KEY,
  prolific_pid     TEXT,
  group_id         INTEGER,
  llm_used_flag    BOOLEAN
);
""")
# — nudge_descriptions —
c.execute("""
CREATE TABLE IF NOT EXISTS nudge_descriptions (
  nudgeID   INTEGER PRIMARY KEY,
  description TEXT
);
INSERT INTO nudge_descriptions(nudgeID,description)
 VALUES
   (1,'Do you want to run a tool for checking security issues?'),
   (2,'LLMs can produce insecure code. Do you want to run a tool for checking security issues?')
 ON CONFLICT(nudgeID) DO NOTHING;
""")
# — event_types —
c.execute("""
CREATE TABLE IF NOT EXISTS event_types (
  eventID    INTEGER PRIMARY KEY,
  description TEXT
);
INSERT INTO event_types(eventID,description)
 VALUES
   (1,'SUB_NO_NUDGE'),
   (2,'RUN_TOOL'),
   (3,'SUB_NO_TOOL'),
   (4,'SUB_TOOL')
 ON CONFLICT(eventID) DO NOTHING;
""")
# — tasks —
c.execute("""
CREATE TABLE IF NOT EXISTS tasks (
  taskID      INTEGER PRIMARY KEY,
  description TEXT,
  code        TEXT
);
""")
# — tool_usage —
c.execute("""
CREATE TABLE IF NOT EXISTS tool_usage (
  interaction_id    SERIAL PRIMARY KEY,
  participant_id    INTEGER REFERENCES participants(participant_id),
  taskID            INTEGER REFERENCES tasks(taskID),
  nudgeID           INTEGER REFERENCES nudge_descriptions(nudgeID),
  eventID           INTEGER REFERENCES event_types(eventID),
  tool_used         BOOLEAN,
  tool_decision_time TEXT
);
""")
# — code_snapshots —
c.execute("""
CREATE TABLE IF NOT EXISTS code_snapshots (
  interaction_id    SERIAL PRIMARY KEY,
  participant_id    INTEGER REFERENCES participants(participant_id),
  taskID            INTEGER REFERENCES tasks(taskID),
  eventID           INTEGER REFERENCES event_types(eventID),
  nudgeID           INTEGER REFERENCES nudge_descriptions(nudgeID),
  code              TEXT,
  timestamp         TEXT
);
""")
conn.commit()

# ─── JSON Loaders ───
BASE_DIR = os.path.dirname(__file__)
def load_json(path):
    with open(os.path.join(BASE_DIR, path), encoding="utf-8") as f:
        return json.load(f)

nudges = {
    'A': load_json("data/nudges/nudgeA.json")["message"],
    'B': load_json("data/nudges/nudgeB.json")["message"]
}

permutations = [
    [1, 2, 3], [1, 3, 2], [2, 1, 3],
    [2, 3, 1], [3, 1, 2], [3, 2, 1]
]
design = {}
for i, perm in enumerate(permutations):
    design[i + 1] = {'tasks': perm, 'nudges': ['A'] * 3}
    design[i + 7] = {'tasks': perm, 'nudges': ['B'] * 3}

# ─── Session Defaults ───
for k, v in {
    'pid': None, 'prolific_id': None, 'group': None,
    'seq': [], 'nseq': [], 'idx': 0,
    'show_nudge': False, 'tool_ran': False,
    'ts_start': None, 'ts_edit_start': None, 'current_id': None,
    'bandit_output': ""
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─── Retrieve from URL ───
params = st.query_params
prolific_param = params.get("PROLIFIC_PID")
group_param = params.get("GROUP_ID")

# ─── Validate and Init Session ───
if st.session_state.pid is None:
    if not prolific_param or not group_param:
        st.error("Missing PROLIFIC_PID or GROUP_ID in URL.")
        st.stop()
    try:
        group_id = int(group_param)
        assert 1 <= group_id <= 200
    except:
        st.error("GROUP_ID must be an integer between 1 and 200.")
        st.stop()

    st.session_state.pid = group_id
    st.session_state.prolific_id = prolific_param.strip()
    group_design = ((group_id - 1) % 12) + 1
    st.session_state.group = group_design
    st.session_state.seq = design[group_design]['tasks']
    st.session_state.nseq = design[group_design]['nudges']

# ─── Main Flow ───
idx = st.session_state.idx
counter = idx + 1

if idx >= len(st.session_state.seq):
    st.success("🎉 Experiment complete. Thank you!")
    st.markdown("""
    ### ✅ Final Step: Submit This Code on Prolific
    Please copy and paste the following completion code back into the Prolific study page to confirm your participation:
    """)
    st.code("761528", language="text")
    st.stop()

if idx < len(st.session_state.seq):

    task_id = st.session_state.seq[idx]
    nudge = st.session_state.nseq[idx]

    if st.session_state.ts_start is None:
        st.session_state.ts_start = datetime.utcnow().isoformat()

    # ─── Load Task Data ───
    dummy_json = load_json(f"data/task/task{task_id}.json")
    llm_json = load_json(f"data/LLMCode/task{task_id}.json")
    dummy_code = dummy_json.get("code", "# Error loading dummy code")
    llm_code = llm_json.get("code", "# Error loading LLM code")

    st.markdown(f"### Task {counter}")
    st.write(dummy_json.get("description", "No task description available."))
    arrow = "===>"
    prompt = dummy_json.get("prompt", "No task prompt available.")
    st.markdown(f"""
        <div style="">
            {arrow}
            <div style="background-color: #fff9c4; border-radius: 8px; display: inline-block; margin-bottom: 10px;">
                {prompt}
            </div>
        </div>
    """, unsafe_allow_html=True)
    st.write(dummy_json.get("explanation", "No task explanation available."))

    st.markdown("#### Starter Code (Read Only)")
    st.text_area(label="", value=dummy_code, height=600, disabled=True, key="dummy_box")

    st.markdown("#### LLM Suggested Solution (Editable)")
    code_key = f"code_{idx}"
    widget_key = f"ace_widget_{idx}"
    if code_key not in st.session_state:
        st.session_state[code_key] = llm_code

    # The editor and action buttons are rendered later inside a form to avoid per-keystroke reruns

# ─── Callbacks ───
def advance():
    st.session_state.idx += 1
    for flag in ('show_nudge', 'tool_ran', 'ts_start', 'ts_edit_start', 'current_id', 'bandit_output'):
        st.session_state[flag] = None

def submit_task():
    # Always use the latest editor contents from session
    latest_code = st.session_state.get(code_key, "")

    now = datetime.utcnow().isoformat()
    # ensure participant row exists
    c.execute("""
      INSERT INTO participants(participant_id, prolific_pid, group_id)
      VALUES (%s,%s,%s)
      ON CONFLICT(participant_id) DO NOTHING;
    """, (
      st.session_state.pid,
      st.session_state.prolific_id,
      st.session_state.group
    ))
    # record SUB_NO_NUDGE snapshot (eventID=1)
    c.execute("""
      INSERT INTO code_snapshots(
        participant_id, taskID, eventID, nudgeID, code, timestamp
      ) VALUES (%s,%s,%s,%s,%s,%s)
    """, (
      st.session_state.pid,
      task_id,
      1,
      (1 if nudge=='A' else 2),
      latest_code,
      now
    ))
    conn.commit()
    st.session_state.show_nudge = True

def run_tool():
    # Always use the latest editor contents from session
    latest_code = st.session_state.get(code_key, "")

    now = datetime.utcnow().isoformat()

    # Record the RUN_TOOL event in tool_usage
    c.execute("""
        INSERT INTO tool_usage (
            participant_id,
            taskID,
            nudgeID,
            eventID,
            tool_used,
            tool_decision_time
        ) VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        st.session_state.pid,
        task_id,
        (1 if nudge == 'A' else 2),
        2,           # eventID for RUN_TOOL
        True,
        now
    ))
    # Also snapshot the code at RUN_TOOL (eventID=2)
    c.execute("""
      INSERT INTO code_snapshots(
        participant_id, taskID, eventID, nudgeID, code, timestamp
      ) VALUES (%s,%s,%s,%s,%s,%s)
    """, (
      st.session_state.pid,
      task_id,
      2,
      (1 if nudge=='A' else 2),
      latest_code,
      now
    ))
    conn.commit()

    # Write the current code to a temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".py")
    tmp.write((latest_code or "").encode())
    tmp.close()

    # Actually run Bandit on that file
    res = subprocess.run(
        ['bandit', '-r', tmp.name, '-f', 'json'],
        capture_output=True,
        text=True
    )

    # Store the output and mark that the tool has run
    st.session_state.bandit_output = res.stdout
    st.session_state.tool_ran      = True
    st.session_state.ts_edit_start = now

def skip_tool():
    # Always use the latest editor contents from session
    latest_code = st.session_state.get(code_key, "")

    now = datetime.utcnow().isoformat()

    # 1) Record the tool‐usage event (SUB_NO_TOOL eventID = 3)
    c.execute("""
        INSERT INTO tool_usage (
            participant_id,
            taskID,
            nudgeID,
            eventID,
            tool_used,
            tool_decision_time
        ) VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        st.session_state.pid,
        task_id,
        (1 if nudge == 'A' else 2),
        3,        # eventID for SUB_NO_TOOL
        False,    # tool_used = False
        now
    ))
    conn.commit()

    # 2) Record the code snapshot for skipping (eventID = 3)
    c.execute("""
        INSERT INTO code_snapshots (
            participant_id,
            taskID,
            eventID,
            nudgeID,
            code,
            timestamp
        ) VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        st.session_state.pid,
        task_id,
        3,  # same SUB_NO_TOOL
        (1 if nudge == 'A' else 2),
        latest_code,
        None  # keep as-is if that's your intended behavior
    ))
    conn.commit()

    # Advance to next task
    advance()

def submit_edited():
    # Always use the latest editor contents from session
    latest_code = st.session_state.get(code_key, "")

    now = datetime.utcnow().isoformat()
    if st.session_state.ts_edit_start:
        start = datetime.fromisoformat(st.session_state.ts_edit_start)
        delta = (datetime.utcnow() - start).total_seconds()
    else:
        delta = 0
    # SUB_TOOL event
    c.execute("""
      INSERT INTO code_snapshots(
        participant_id, taskID, eventID, nudgeID, code, timestamp
      ) VALUES (%s,%s,%s,%s,%s,%s)
    """, (
      st.session_state.pid,
      task_id,
      4,
      (1 if nudge=='A' else 2),
      latest_code,
      now
    ))
    conn.commit()
    advance()

def color_tag(severity):
    return {
        "HIGH": "🟥 High",
        "MEDIUM": "🟧 Medium",
        "LOW": "🟨 Low"
    }.get(severity.upper(), severity)

if idx < len(st.session_state.seq):
    # Flags captured during form submission
    submit_task_clicked = False
    run_tool_clicked = False
    skip_tool_clicked = False
    submit_final_clicked = False

    # Render the form with editor and buttons here to keep function names in scope
    with st.form(key=f"task_form_{idx}", clear_on_submit=False):
        code_input = st_ace(
            value=st.session_state[code_key],
            language="python",
            theme="monokai",
            key=widget_key,
            height=650,
            tab_size=4,
            font_size=14,
            wrap=True,
            auto_update=True
        )
        if code_input is not None:
            st.session_state[code_key] = code_input

        if not st.session_state.show_nudge:
            submit_task_clicked = st.form_submit_button("Submit Task")
        elif not st.session_state.tool_ran:
            st.warning(nudges[nudge], icon="⚠️")
            c1, c2 = st.columns(2)
            with c1:
                run_tool_clicked = st.form_submit_button("Run Security Tool")
            with c2:
                skip_tool_clicked = st.form_submit_button("Submit Without Checking")
        else:
            st.subheader("Tool Output (Bandit)")
            try:
                data = json.loads(st.session_state.bandit_output)
                results = data.get("results", [])
                if not results:
                    st.success("✅ No issues found by Bandit.")
                else:
                    for i, issue in enumerate(results, 1):
                        with st.expander(f"Issue {i}"):
                            st.write(f"**Description**: {issue['issue_text']}")
                            st.write(f"**Line**: {issue['line_number']}")
                            st.write(f"**Severity**: {color_tag(issue['issue_severity'])}")
                            st.write(f"**Confidence**: {color_tag(issue['issue_confidence'])}")
                            st.code(issue["code"], language="python")
                            st.caption(f"Test ID: {issue['test_id']} — {issue['test_name']}")
            except Exception:
                st.text(st.session_state.bandit_output)

            st.markdown("""
            <div style=\"background-color: #e8f0fe; border-left: 6px solid #1a73e8; padding: 1rem; border-radius: 5px; margin-bottom: 1rem; color: #202124;\">
                <strong>Note:</strong> You can edit the code above if you wish. Once you're ready, click <strong>Submit Final Code</strong> below.
            </div>
            """, unsafe_allow_html=True)

            submit_final_clicked = st.form_submit_button("Submit Final Code")

    # Execute actions after the form submission to avoid double-click behavior
    if submit_task_clicked:
        submit_task()
        st.rerun()
    elif run_tool_clicked:
        run_tool()
        st.rerun()
    elif skip_tool_clicked:
        skip_tool()
        st.rerun()
    elif submit_final_clicked:
        submit_edited()
        st.rerun()