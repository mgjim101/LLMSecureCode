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

# --- Load tasks & nudges ---
tasks = [load_json(f"data/tasks/task{i+1}.json") for i in range(3)]
nudges = {
    'A': load_json("data/nudges/nudgeA.json")["message"],
    'B': load_json("data/nudges/nudgeB.json")["message"]
}
design = {i: {'tasks': seq, 'nudges': nds} for i,(seq,nds) in enumerate([
    ([1,2,3],['A','B','A']),
    ([1,3,2],['B','A','B']),
    ([2,1,3],['A','B','A']),
    ([2,3,1],['B','A','B']),
    ([3,1,2],['A','B','A']),
    ([3,2,1],['B','A','B'])
], start=1)}

# --- Initialize session state ---
defaults = {
    'pid': None, 'group': None,
    'seq': [], 'nseq': [], 'idx': 0,
    'show_nudge': False, 'tool_ran': False, 'editing': False,
    'logs': [], 'bandit_output': None
}
for k,v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# --- Page Setup ---
st.set_page_config(page_title="SecureCode Study", layout="centered")
st.title("🔒 SecureCode Study")
st.markdown("**Overview:** Complete tasks → optional security scan → optional edit → auto-advance.")

# --- Participant ID Input ---
if st.session_state.pid is None:
    pid = st.number_input("Enter Participant ID (1–30)", 1, 30)
    if st.button("Start Experiment", key="start_button"):
        st.session_state.pid = pid
        grp = ((pid - 1) // 5) + 1
        st.session_state.group = grp
        st.session_state.seq = design[grp]['tasks']
        st.session_state.nseq = design[grp]['nudges']
    else:
        st.stop()

# --- Experiment Flow ---
idx = st.session_state.idx
if idx >= len(st.session_state.seq):
    st.success("🎉 All tasks completed. Thank you!")
    st.json(st.session_state.logs)
    st.stop()

# Load current task & nudge
task_id = st.session_state.seq[idx]
t = tasks[task_id - 1]
nudge = st.session_state.nseq[idx]

st.header(f"Task {t['id']}: {t['title']}")
st.write("Modify code below and click Submit Task.")

# Editor always visible, stored in session_state.code_{idx}
code_key = f"code_{idx}"
if code_key not in st.session_state:
    st.session_state[code_key] = t['code']
code = st_monaco(
    value=st.session_state[code_key],
    language="python",
    theme="vs-dark",
    height=400)

# Callback functions
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
    res = subprocess.run(
        ['bandit','-r',tmp.name,'-f','json'], capture_output=True, text=True
    )
    st.session_state.bandit_output = res.stdout
    st.session_state.logs[-1].update({'used_tool': True, 'output': res.stdout})
    st.session_state.tool_ran = True


def skip_tool():
    st.session_state.logs[-1].update({
        'used_tool': False,
        'code_post': st.session_state.logs[-1]['code_pre']
    })
    advance_task()


def next_steps_edit():
    st.session_state.editing = True


def next_steps_submit():
    st.session_state.logs[-1].update({'code_post': st.session_state.logs[-1]['code_pre']})
    advance_task()


def submit_edited():
    st.session_state.logs[-1].update({'code_post': st.session_state[code_key]})
    advance_task()


def advance_task():
    st.session_state.idx += 1
    for flag in ['show_nudge', 'tool_ran', 'editing']:
        st.session_state[flag] = False

# Stage 1: Submit Task
eg1 = not st.session_state.show_nudge and not st.session_state.tool_ran and not st.session_state.editing
if eg1:
    st.button("Submit Task", on_click=submit_task)

# Stage 2: Nudge + Run/Skip
eg2 = st.session_state.show_nudge and not st.session_state.tool_ran and not st.session_state.editing
if eg2:
    st.subheader("🔔 Security Nudge")
    st.write(nudges[nudge])
    cols = st.columns(2)
    cols[0].button("Run Security Tool", on_click=run_tool)
    cols[1].button("Submit Without Checking", on_click=skip_tool)

# Stage 3: After Tool: report + next steps
eg3 = st.session_state.tool_ran and not st.session_state.editing
if eg3:
    st.subheader("Tool Output (Bandit)")
    try:
        st.json(json.loads(st.session_state.bandit_output))
    except:
        st.text(st.session_state.bandit_output)
    st.subheader("Next Steps")
    c3 = st.columns(2)
    c3[0].button("Edit Code", on_click=next_steps_edit)
    c3[1].button("Submit As-Is", on_click=next_steps_submit)

# Stage 4: Edit Mode
eg4 = st.session_state.editing
if eg4:
    st.info("Edit your code above and click 'Submit Edited Code'.")
    st.button("Submit Edited Code", on_click=submit_edited)
