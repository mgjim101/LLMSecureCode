import streamlit as st
import json
import os
import subprocess
import tempfile
from streamlit_monaco import st_monaco

# --- Project Paths & JSON Loader ---
BASE_DIR = os.path.dirname(__file__)

def load_json(rel_path):
    """
    Load a JSON file from the data directory with error handling.
    """
    full_path = os.path.join(BASE_DIR, rel_path)
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        st.error(f"File not found: {full_path}")
        st.stop()
    except json.JSONDecodeError as e:
        st.error(f"JSON decode error in {full_path}: {e}")
        st.stop()

# --- Load All Tasks & Nudges Data ---
tasks_data = [load_json(f"data/tasks/task{i+1}.json") for i in range(3)]
nudges_data = {
    'A': load_json("data/nudges/nudgeA.json")["message"],
    'B': load_json("data/nudges/nudgeB.json")["message"]
}

# --- Group Assignment Mapping ---
group_design = {
    1: {'tasks': [1, 2, 3], 'nudges': ['A', 'B', 'A']},
    2: {'tasks': [1, 3, 2], 'nudges': ['B', 'A', 'B']},
    3: {'tasks': [2, 1, 3], 'nudges': ['A', 'B', 'A']},
    4: {'tasks': [2, 3, 1], 'nudges': ['B', 'A', 'B']},
    5: {'tasks': [3, 1, 2], 'nudges': ['A', 'B', 'A']},
    6: {'tasks': [3, 2, 1], 'nudges': ['B', 'A', 'B']},
}

# --- Streamlit UI Setup ---
st.set_page_config(page_title="SecureCode Study", layout="centered")
st.title("🔒 SecureCode Study")
st.markdown(
    """
    **Study Overview:**  
    You will complete three code tasks and decide whether to run a security tool after each.  
    Enter your participant ID (1–30) to begin.
    """
)

# --- Participant Identification ---
if 'participant_id' not in st.session_state:
    pid = st.number_input("Enter your Participant ID", min_value=1, max_value=30, step=1)
    if st.button("Start Experiment"):
        st.session_state.participant_id = int(pid)
        # assign to group: 5 participants per group
        group_num = ((st.session_state.participant_id - 1) // 5) + 1
        st.session_state.group = group_num
        # load group-specific sequences
        design = group_design[group_num]
        st.session_state.task_sequence = design['tasks']
        st.session_state.nudge_sequence = design['nudges']
                # init progress state
        st.session_state.task_index = 0
        st.session_state.show_nudge = False
        st.session_state.task_done = False
        st.session_state.logs = []
        # Streamlit automatically reruns after widget interaction; explicit rerun removed
    else:
        st.stop()

# --- Display Assigned Group ---
st.subheader(f"Participant ID: {st.session_state.participant_id} — Group G{st.session_state.group}")

# --- Session State Defaults ---
if 'task_index' not in st.session_state:
    st.session_state.task_index = 0
if 'show_nudge' not in st.session_state:
    st.session_state.show_nudge = False
if 'task_done' not in st.session_state:
    st.session_state.task_done = False
if 'logs' not in st.session_state:
    st.session_state.logs = []

# --- Experiment Flow ---
idx = st.session_state.task_index
# end of experiment
if idx >= len(st.session_state.task_sequence):
    st.success("🎉 Experiment complete. Thank you!")
    st.write("Your responses:")
    st.json(st.session_state.logs)
    st.stop()

# load current task
task_id = st.session_state.task_sequence[idx]
task = tasks_data[task_id - 1]
nudge_type = st.session_state.nudge_sequence[idx]
nudge_msg = nudges_data[nudge_type]

# --- Display Code Task ---
st.header(f"Task {task['id']}: {task['title']}")
st.write("Review and modify the code below. Click **Submit** when ready.")

code = st_monaco(
    task['code'],
    language="python",
    theme="vs-dark",
    height=500
)

# --- Submit and Nudge ---
if not st.session_state.show_nudge and not st.session_state.task_done:
    if st.button("Submit Task"):
        st.session_state.show_nudge = True

if st.session_state.show_nudge and not st.session_state.task_done:
    st.subheader("Security Nudge")
    st.write(nudge_msg)
    col1, col2 = st.columns(2)
    if col1.button("Run Security Tool"):
        # run Bandit
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.py')
        tmp.write(code.encode())
        tmp.close()
        result = subprocess.run(
            ['bandit', '-r', tmp.name, '-f', 'json'],
            capture_output=True, text=True
        )
        st.subheader("Tool Output (Bandit)")
        try:
            st.json(json.loads(result.stdout))
        except json.JSONDecodeError:
            st.text(result.stdout)
        st.session_state.logs.append({
            'participant': st.session_state.participant_id,
            'group': st.session_state.group,
            'task': task['id'],
            'nudge': nudge_type,
            'used_tool': True,
            'output': result.stdout
        })
        st.session_state.task_done = True
    if col2.button("Skip Tool"):
        st.info("Tool skipped.")
        st.session_state.logs.append({
            'participant': st.session_state.participant_id,
            'group': st.session_state.group,
            'task': task['id'],
            'nudge': nudge_type,
            'used_tool': False
        })
        st.session_state.task_done = True

# --- Next Task Navigation ---
if st.session_state.task_done:
    def go_next():
        st.session_state.task_index += 1
        st.session_state.show_nudge = False
        st.session_state.task_done = False
    st.button("Next Task", on_click=go_next)
