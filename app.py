import streamlit as st
import sqlite3, os, json, subprocess, tempfile
from datetime import datetime
from streamlit_ace import st_ace
import psycopg2
from dotenv import load_dotenv
load_dotenv()

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
c.execute("""
CREATE TABLE IF NOT EXISTS interactions (
 id SERIAL PRIMARY KEY,
 participant INTEGER,
 prolific_id TEXT,
 group_num INTEGER,
 task INTEGER,
 nudge TEXT,
 timestamp_start TEXT,
 code_pre TEXT,
 timestamp_submit TEXT,
 used_tool BOOLEAN,
 timestamp_tool_decision TEXT,
 timestamp_bandit_decision TEXT,
 editing_time_sec REAL,
 code_post TEXT,
 timestamp_edit_complete TEXT
)
""")
conn.commit()

# ─── JSON loaders ───
BASE_DIR = os.path.dirname(__file__)

def load_json(path):
    with open(os.path.join(BASE_DIR, path), encoding="utf-8") as f:
        return json.load(f)

nudges = {
    'A': load_json("data/nudges/nudgeA.json")["message"],
    'B': load_json("data/nudges/nudgeB.json")["message"]
}

# ─── New Design with 2 main groups and 6 permutations each ───
permutations = [
    [1, 2, 3], [1, 3, 2], [2, 1, 3],
    [2, 3, 1], [3, 1, 2], [3, 2, 1]
]
design = {}
for i, perm in enumerate(permutations):
    design[i + 1] = {'tasks': perm, 'nudges': ['A'] * 3}
    design[i + 7] = {'tasks': perm, 'nudges': ['B'] * 3}

# ─── Session defaults ───
for k, v in {
    'pid': None, 'prolific_id': None, 'group': None,
    'seq': [], 'nseq': [], 'idx': 0,
    'show_nudge': False, 'tool_ran': False, 'editing': False,
    'ts_start': None, 'ts_edit_start': None, 'current_id': None
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─── Page & Project Description ───
st.set_page_config(page_title="SecureCode Study", layout="wide")
st.title("What is this study?")
st.markdown(
    """ 
UBC is developing a tool to support programming education using large language models (LLMs). The tool
provides AI-generated code suggestions to help students complete coding tasks while learning best practices.
Designed for use in instructional settings, it aims to enhance learning without promoting over-reliance on 
automation. The project also includes user studies to evaluate how students interact with the tool and how it 
influences their coding behavior.

TO-DO:
1. Check the code in the text box (read only) for the coding task.
2. The code editor has the solution from an LLM. You can edit this code.
"""
)

# ─── Retrieve Prolific ID from URL ───
params = st.query_params
prolific_param = params.get("PROLIFIC_PID", None)

# ─── Participant ID Input & Validation ───
if st.session_state.pid is None:
    pid_str = st.text_input("Enter your Participant ID (1–200)")

    if st.button("Start Experiment"):
        # Validate participant ID
        try:
            pid = int(pid_str)
        except ValueError:
            st.error("❗ Please enter a valid integer ID.")
            st.stop()
        if pid < 1 or pid > 200:
            st.error("❗ Invalid ID — please enter a number between 1 and 200.")
            st.stop()

        # Validate Prolific ID from URL
        if prolific_param is None or not prolific_param.strip():
            st.error("❗ Prolific ID not found in the URL. Please access the study through the Prolific link provided.")
            st.stop()

        st.session_state.pid = pid
        st.session_state.prolific_id = prolific_param.strip()

        group = ((pid - 1) % 12) + 1
        st.session_state.group = group
        st.session_state.seq = design[group]['tasks']
        st.session_state.nseq = design[group]['nudges']
    else:
        st.stop()

st.subheader(f"Participant {st.session_state.pid} — Group G{st.session_state.group}")

# ─── Main Experiment Flow ───
idx = st.session_state.idx
if idx >= len(st.session_state.seq):
    st.success("🎉 Experiment complete. Thank you!")

    st.markdown("""
    ### ✅ Final Step: Submit This Code on Prolific
    Please copy and paste the following completion code back into the Prolific study page to confirm your participation:
    """)
    st.code("761528", language="text")

    st.stop()

task_id = st.session_state.seq[idx]
nudge = st.session_state.nseq[idx]

if st.session_state.ts_start is None:
    st.session_state.ts_start = datetime.utcnow().isoformat()

# ─── Load dummy code and LLM code ───
dummy_code_path = f"data/task/task{task_id}.json"
llm_code_path = f"data/LLMCode/task{task_id}.json"

dummy_json = load_json(dummy_code_path)
llm_json = load_json(llm_code_path)

dummy_code = dummy_json.get("code", "# Error loading dummy code")
llm_code = llm_json.get("code", "# Error loading LLM code")

st.header(f"Task {task_id}")

c0 = st.container()
with c0:
    st.markdown("### Task Description")
    st.write(dummy_json.get("prompt", "No task description available."))

c1, c2 = st.columns(2)
with c1:
    st.markdown("#### Coding Problem (Read Only)")
    st.text_area(label="", value=dummy_code, height=600, disabled=True, key="dummy_box")

with c2:
    st.markdown("#### LLM Suggested Solution (Editable)")
    code_key = f"code_{idx}"
    widget_key = f"ace_widget_{idx}"
    if code_key not in st.session_state:
        st.session_state[code_key] = llm_code

    code_input = st_ace(
        value=st.session_state[code_key],
        language="python",
        theme="monokai",
        key=widget_key,
        height=600,
        tab_size=4,
        font_size=14,
        wrap=True,
        auto_update=True
    )
    if code_input is not None:
        st.session_state[code_key] = code_input

# ─── Callbacks ───

def advance():
    st.session_state.idx += 1
    for flag in ('show_nudge', 'tool_ran', 'editing', 'ts_start', 'ts_edit_start', 'current_id'):
        st.session_state[flag] = None if flag.endswith('_start') or flag == 'current_id' else False


def submit_task():
    now = datetime.utcnow().isoformat()
    c.execute("""
    INSERT INTO interactions
        (participant, prolific_id, group_num, task, nudge, timestamp_start, code_pre, timestamp_submit)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    RETURNING id
    """, (
        st.session_state.pid,
        st.session_state.prolific_id,
        st.session_state.group,
        task_id,
        nudge,
        st.session_state.ts_start,
        st.session_state[code_key],
        now
    ))
    last_id = c.fetchone()[0]
    conn.commit()
    st.session_state.current_id = last_id
    st.session_state.show_nudge = True


def run_tool():
    now = datetime.utcnow().isoformat()
    lastid = st.session_state.current_id
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".py")
    tmp.write(st.session_state[code_key].encode())
    tmp.close()
    res = subprocess.run(['bandit', '-r', tmp.name, '-f', 'json'], capture_output=True, text=True)
    c.execute("""
        UPDATE interactions SET
            used_tool=%s,
            timestamp_tool_decision=%s,
            timestamp_bandit_decision=%s,
            code_post=code_pre
        WHERE id=%s
        """, (True, now, now, lastid))
    conn.commit()
    st.session_state.bandit_output = res.stdout
    st.session_state.tool_ran = True


def skip_tool():
    now = datetime.utcnow().isoformat()
    lastid = st.session_state.current_id
    c.execute("""
      UPDATE interactions SET
        used_tool=%s,
        timestamp_tool_decision=%s,
        timestamp_bandit_decision=%s,
        code_post=code_pre
      WHERE id=%s
    """, (False, now, now, lastid))
    conn.commit()
    advance()


def edit_mode():
    st.session_state.editing = True
    st.session_state.ts_edit_start = datetime.utcnow().isoformat()


def submit_as_is():
    now = datetime.utcnow().isoformat()
    lastid = st.session_state.current_id
    c.execute("""
      UPDATE interactions SET
        code_post=%s,
        timestamp_edit_complete=%s,
        editing_time_sec=0
      WHERE id=%s
    """, (st.session_state[code_key], now, lastid))
    conn.commit()
    advance()


def submit_edited():
    now = datetime.utcnow().isoformat()
    start = datetime.fromisoformat(st.session_state.ts_edit_start)
    delta = (datetime.utcnow() - start).total_seconds()
    lastid = st.session_state.current_id
    c.execute("""
      UPDATE interactions SET
        code_post=%s, timestamp_edit_complete=%s, editing_time_sec=%s
      WHERE id=%s
    """, (st.session_state[code_key], now, delta, lastid))
    conn.commit()
    advance()


def color_tag(severity):
    return {
        "HIGH": "🟥 High",
        "MEDIUM": "🟧 Medium",
        "LOW": "🟨 Low"
    }.get(severity.upper(), severity)


# ─── UI Stages ───
if not st.session_state.show_nudge:
    st.button("Submit Task", on_click=submit_task, key=f"submit_{idx}")
elif not st.session_state.tool_ran and not st.session_state.editing:
    st.warning(nudges[nudge], icon="⚠️")
    c1, c2 = st.columns(2)
    c1.button("Run Security Tool", on_click=run_tool, key=f"run_{idx}")
    c2.button("Submit Without Checking", on_click=skip_tool, key=f"skip_{idx}")
if st.session_state.tool_ran and not st.session_state.editing:
    st.subheader("Tool Output (Bandit)")
    try:
        bandit_data = json.loads(st.session_state.bandit_output)
        results = bandit_data.get("results", [])
        if not results:
            st.success("There is no issues found by Bandit!")
        else:
            for i, issue in enumerate(results, 1):
                with st.expander(f"Issue {i}"):
                    st.write(f"**Desctiption**: {issue['issue_text']}")
                    st.write(f"**Line:** {issue['line_number']}")
                    st.write(f"**Severity:** {color_tag(issue['issue_severity'])}")
                    st.write(f"**Confidence:** {color_tag(issue['issue_confidence'])}")
                    st.code(issue["code"], language="python")
                    st.caption(f"Test ID: {issue['test_id']} — {issue['test_name']}")
    except Exception:
                st.text(st.session_state.bandit_output)
    st.subheader("Next Steps")
    st.write("After reviewing the Bandit report, choose to refine your code or submit as-is to proceed.")
    e1, e2 = st.columns(2)
    e1.button("Edit Code", on_click=edit_mode, key=f"edit_{idx}")
    e2.button("Submit", on_click=submit_as_is, key=f"asis_{idx}")
if st.session_state.editing:
    st.info("Edit your code above, then click **Submit Edited Code**.")
    st.button("Submit Edited Code", on_click=submit_edited, key=f"edited_{idx}")