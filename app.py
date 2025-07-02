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
    'show_nudge': False, 'tool_ran': False, 'editing': False,
    'ts_start': None, 'ts_edit_start': None, 'current_id': None
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

# ─── Load Task Data ───
dummy_json = load_json(f"data/task/task{task_id}.json")
llm_json = load_json(f"data/LLMCode/task{task_id}.json")
dummy_code = dummy_json.get("code", "# Error loading dummy code")
llm_code = llm_json.get("code", "# Error loading LLM code")

st.header(f"Task {task_id}")
st.markdown("### Task Description")
st.write(dummy_json.get("prompt", "No task description available."))

st.markdown("#### Coding Problem (Read Only)")
st.text_area(label="", value=dummy_code, height=600, disabled=True, key="dummy_box")

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
    height=650,
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
    INSERT INTO interactions (participant, prolific_id, group_num, task, nudge, timestamp_start, code_pre, timestamp_submit)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
    """, (
        st.session_state.pid, st.session_state.prolific_id, st.session_state.group,
        task_id, nudge, st.session_state.ts_start, st.session_state[code_key], now
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
        UPDATE interactions SET used_tool=%s, timestamp_tool_decision=%s,
        timestamp_bandit_decision=%s, code_post=code_pre WHERE id=%s
    """, (True, now, now, lastid))
    conn.commit()
    st.session_state.bandit_output = res.stdout
    st.session_state.tool_ran = True

def skip_tool():
    now = datetime.utcnow().isoformat()
    lastid = st.session_state.current_id
    c.execute("""
        UPDATE interactions SET used_tool=%s, timestamp_tool_decision=%s,
        timestamp_bandit_decision=%s, code_post=code_pre WHERE id=%s
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
        UPDATE interactions SET code_post=%s, timestamp_edit_complete=%s,
        editing_time_sec=0 WHERE id=%s
    """, (st.session_state[code_key], now, lastid))
    conn.commit()
    advance()

def submit_edited():
    now = datetime.utcnow().isoformat()
    start = datetime.fromisoformat(st.session_state.ts_edit_start)
    delta = (datetime.utcnow() - start).total_seconds()
    lastid = st.session_state.current_id
    c.execute("""
        UPDATE interactions SET code_post=%s, timestamp_edit_complete=%s,
        editing_time_sec=%s WHERE id=%s
    """, (st.session_state[code_key], now, delta, lastid))
    conn.commit()
    advance()

def color_tag(severity):
    return {
        "HIGH": "🟥 High",
        "MEDIUM": "🟧 Medium",
        "LOW": "🟨 Low"
    }.get(severity.upper(), severity)

# ─── Interaction UI ───
if not st.session_state.show_nudge:
    st.button("Submit Task", on_click=submit_task, key=f"submit_{idx}")
elif not st.session_state.tool_ran and not st.session_state.editing:
    st.warning(nudges[nudge], icon="⚠️")
    c1, c2 = st.columns(2)
    c1.button("Run Security Tool", on_click=run_tool, key=f"run_{idx}")
    c2.button("Submit Without Checking", on_click=skip_tool, key=f"skip_{idx}")
elif st.session_state.tool_ran and not st.session_state.editing:
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

    st.subheader("Next Steps")
    e1, e2 = st.columns(2)
    e1.button("Edit Code", on_click=edit_mode, key=f"edit_{idx}")
    e2.button("Submit As-Is", on_click=submit_as_is, key=f"asis_{idx}")
elif st.session_state.editing:
    st.info("Edit your code above, then click **Submit Edited Code**.")
    st.button("Submit Edited Code", on_click=submit_edited, key=f"edited_{idx}")