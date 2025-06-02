import streamlit as st
import sqlite3, os, json, subprocess, tempfile
from datetime import datetime
from streamlit_ace import st_ace

# ─── Database setup ───
BASE_DIR = os.path.dirname(__file__)
DB_PATH  = os.path.join(BASE_DIR, "interactions.db")
conn     = sqlite3.connect(DB_PATH, check_same_thread=False)
c        = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS interactions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
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
for k,v in {
    'pid':None, 'prolific_id':None, 'group':None,
    'seq':[], 'nseq':[], 'idx':0,
    'show_nudge':False, 'tool_ran':False, 'editing':False,
    'ts_start':None, 'ts_edit_start':None, 'current_id':None
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

# ─── Participant ID Input & Validation ───
if st.session_state.pid is None:
    pid_str = st.text_input("Enter your Participant ID (1–200)")
    prolific_str = st.text_input("Enter your Prolific ID")

    if st.button("Start Experiment"):
        try:
            pid = int(pid_str)
        except:
            st.error("❗ Please enter a valid integer ID.")
            st.stop()
        if pid < 1 or pid > 200:
            st.error("❗ Invalid ID — please enter a number between 1 and 200.")
            st.stop()
        if not prolific_str.strip():
            st.error("❗ Please enter your Prolific ID.")
            st.stop()

        st.session_state.pid = pid
        st.session_state.prolific_id = prolific_str.strip()

        group = ((pid - 1) % 12) + 1
        st.session_state.group = group
        st.session_state.seq   = design[group]['tasks']
        st.session_state.nseq  = design[group]['nudges']
    else:
        st.stop()

st.subheader(f"Participant {st.session_state.pid} — Group G{st.session_state.group}")

# ─── Main Experiment Flow ───
idx = st.session_state.idx
if idx >= len(st.session_state.seq):
    st.success("🎉 Experiment complete. Thank you!")
    st.stop()

task_id = st.session_state.seq[idx]
nudge   = st.session_state.nseq[idx]

if st.session_state.ts_start is None:
    st.session_state.ts_start = datetime.utcnow().isoformat()

# ─── Load dummy code and LLM code ───
dummy_code_path = f"data/task/task{task_id}.json"
llm_code_path   = f"data/LLMCode/task{task_id}.json"

dummy_json = load_json(dummy_code_path)
llm_json = load_json(llm_code_path)

dummy_code = dummy_json.get("code", "# Error loading dummy code")
llm_code   = llm_json.get("code", "# Error loading LLM code")

st.header(f"Task {task_id}")

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
    for flag in ('show_nudge','tool_ran','editing','ts_start','ts_edit_start','current_id'):
        st.session_state[flag] = None if flag.endswith('_start') or flag=='current_id' else False

def submit_task():
    now = datetime.utcnow().isoformat()
    c.execute("""
      INSERT INTO interactions
        (participant, prolific_id, group_num, task, nudge, timestamp_start, code_pre, timestamp_submit)
      VALUES (?,?,?,?,?,?,?,?)
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
    conn.commit()
    st.session_state.current_id = c.lastrowid
    st.session_state.show_nudge = True

def run_tool():
    now = datetime.utcnow().isoformat()
    lastid = st.session_state.current_id
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".py")
    tmp.write(st.session_state[code_key].encode()); tmp.close()
    res = subprocess.run(['bandit','-r',tmp.name,'-f','json'], capture_output=True, text=True)
    c.execute("""
      UPDATE interactions SET
        used_tool=1,
        timestamp_tool_decision=?,
        timestamp_bandit_decision=?,
        code_post=code_pre
      WHERE id=?
    """, (now, now, lastid))
    conn.commit()
    st.session_state.bandit_output = res.stdout
    st.session_state.tool_ran = True

def skip_tool():
    now = datetime.utcnow().isoformat()
    lastid = st.session_state.current_id
    c.execute("""
      UPDATE interactions SET
        used_tool=0,
        timestamp_tool_decision=?,
        timestamp_bandit_decision=?,
        code_post=code_pre
      WHERE id=?
    """, (now, now, lastid))
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
        code_post=?,
        timestamp_edit_complete=?,
        editing_time_sec=0
      WHERE id=?
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
        code_post=?, timestamp_edit_complete=?, editing_time_sec=?
      WHERE id=?
    """, (st.session_state[code_key], now, delta, lastid))
    conn.commit()
    advance()

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
        st.json(json.loads(st.session_state.bandit_output))
    except:
        st.text(st.session_state.bandit_output)
    st.subheader("Next Steps")
    st.write("After reviewing the Bandit report, choose to refine your code or submit as-is to proceed.")
    e1, e2 = st.columns(2)
    e1.button("Edit Code", on_click=edit_mode, key=f"edit_{idx}")
    e2.button("Submit As-Is", on_click=submit_as_is, key=f"asis_{idx}")
if st.session_state.editing:
    st.info("Edit your code above, then click **Submit Edited Code**.")
    st.button("Submit Edited Code", on_click=submit_edited, key=f"edited_{idx}")