import streamlit as st
import json, os, subprocess, tempfile
from streamlit_monaco import st_monaco

# --- Helpers & JSON Loader ---
BASE_DIR = os.path.dirname(__file__)
def load_json(path):
    full = os.path.join(BASE_DIR, path)
    try:
        with open(full, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Failed to load {full}: {e}")
        st.stop()

# --- Load Tasks, Nudges, and Pre-compiled LLM Suggestions ---
tasks = [load_json(f"data/tasks/task{i+1}.json") for i in range(3)]
nudges = {
    'A': load_json("data/nudges/nudgeA.json")["message"],
    'B': load_json("data/nudges/nudgeB.json")["message"]
}
# Each suggestions file is a JSON array of three code strings
suggestions_data = [load_json(f"data/suggestions/task{i+1}.json") for i in range(3)]

# --- Experimental Design Mapping ---
design = {
    1:{'tasks':[1,2,3],'nudges':['A','B','A']},
    2:{'tasks':[1,3,2],'nudges':['B','A','B']},
    3:{'tasks':[2,1,3],'nudges':['A','B','A']},
    4:{'tasks':[2,3,1],'nudges':['B','A','B']},
    5:{'tasks':[3,1,2],'nudges':['A','B','A']},
    6:{'tasks':[3,2,1],'nudges':['B','A','B']}
}

# --- Initialize Session State ---
defaults = {
    'pid': None,
    'group': None,
    'seq': [],
    'nseq': [],
    'idx': 0,
    'show_nudge': False,
    'tool_ran': False,
    'editing': False,
    'logs': []
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# --- Page Setup ---
st.set_page_config(page_title="SecureCode Study", layout="centered")
st.title("🔒 SecureCode Study")
st.markdown(
    """
    **Study Overview**  
    You will complete three coding tasks with three LLM-generated suggestions displayed above your editor.  
    After submission, you'll receive a security nudge, can run a static scan (Bandit), optionally edit based on feedback,
    and then proceed to the next task.
    """
)

# --- Participant Identification ---
if st.session_state.pid is None:
    pid = st.number_input("Enter Participant ID (1–30)", 1, 30)
    if st.button("Start Experiment"):
        st.session_state.pid = pid
        grp = ((pid - 1) // 5) + 1
        st.session_state.group = grp
        st.session_state.seq = design[grp]['tasks']
        st.session_state.nseq = design[grp]['nudges']
    else:
        st.stop()

st.subheader(f"Participant {st.session_state.pid} — Group G{st.session_state.group}")

# --- Experiment Flow ---
idx = st.session_state.idx
if idx >= len(st.session_state.seq):
    st.success("🎉 All tasks completed. Thank you!")
    st.json(st.session_state.logs)
    st.stop()

# Load current task and nudge type
task_id = st.session_state.seq[idx]
t = tasks[task_id - 1]
nudge = st.session_state.nseq[idx]

# --- Display Task & LLM Suggestions ---
st.header(f"Task {t['id']}: {t['title']}")
st.write("Review these LLM-generated suggestions, then modify below and submit.")
for i, suggestion in enumerate(suggestions_data[idx], start=1):
    st.text_area(f"Suggestion {i}", value=suggestion, height=100, disabled=True)

# --- Main Code Editor (always visible) ---
code_key = f"code_{idx}"
if code_key not in st.session_state:
    st.session_state[code_key] = t['code']
code = st_monaco(
    value=st.session_state[code_key],
    language="python",
    theme="vs-dark",
    height=400
)

# --- Callbacks to Log & Advance ---
def advance():
    st.session_state.idx += 1
    for flag in ('show_nudge', 'tool_ran', 'editing'):
        st.session_state[flag] = False

def submit_task():
    st.session_state.logs.append({
        'participant': st.session_state.pid,
        'group':       st.session_state.group,
        'task':        t['id'],
        'nudge':       nudge,
        'code_pre':    st.session_state[code_key]
    })
    st.session_state.show_nudge = True

def run_tool():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.py')
    tmp.write(st.session_state.logs[-1]['code_pre'].encode()); tmp.close()
    res = subprocess.run(['bandit','-r',tmp.name,'-f','json'], capture_output=True, text=True)
    out = res.stdout
    st.session_state.logs[-1].update({'used_tool': True, 'output': out})
    st.session_state.tool_ran = True

def skip_tool():
    st.session_state.logs[-1].update({
        'used_tool': False,
        'code_post': st.session_state.logs[-1]['code_pre']
    })
    advance()

def edit_code():
    st.session_state.editing = True

def submit_as_is():
    st.session_state.logs[-1].update({'code_post': st.session_state.logs[-1]['code_pre']})
    advance()

def submit_edited():
    st.session_state.logs[-1].update({'code_post': st.session_state[code_key]})
    advance()

# --- Stage 1: Submit Task ---
if not st.session_state.show_nudge:
    st.button("Submit Task", on_click=submit_task, key=f"sub_{idx}")

# --- Stage 2: Display Nudge & Run/Skip ---
elif st.session_state.show_nudge and not st.session_state.tool_ran and not st.session_state.editing:
    st.subheader("🔔 Security Nudge")
    st.write(nudges[nudge])
    c1, c2 = st.columns(2)
    c1.button("Run Security Tool", on_click=run_tool, key=f"run_{idx}")
    c2.button("Submit Without Checking", on_click=skip_tool, key=f"skip_{idx}")

# --- Stage 3: Bandit Report + Next Steps ---
if st.session_state.tool_ran and not st.session_state.editing:
    st.subheader("Tool Output (Bandit)")
    try:
        st.json(json.loads(st.session_state.logs[-1]['output']))
    except:
        st.text(st.session_state.logs[-1]['output'])
    st.subheader("Next Steps")
    st.write("Choose to refine your code based on feedback or submit as-is to proceed.")
    e1, e2 = st.columns(2)
    e1.button("Edit Code", on_click=edit_code, key=f"edit_{idx}")
    e2.button("Submit As-Is", on_click=submit_as_is, key=f"asis_{idx}")

# --- Stage 4: Edit Mode & Submit Edited ---
if st.session_state.editing:
    st.info("Edit the code above and click **Submit Edited Code**.")
    st.button("Submit Edited Code", on_click=submit_edited, key=f"edit_sub_{idx}")
