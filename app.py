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

# --- Load Data ---
tasks = [load_json(f"data/tasks/task{i+1}.json") for i in range(3)]
nudges = {
    'A': load_json("data/nudges/nudgeA.json")["message"],
    'B': load_json("data/nudges/nudgeB.json")["message"]
}

# --- Session State Initialization ---
if 'task_index' not in st.session_state:
    st.session_state.task_index = 0
if 'nudge_sequence' not in st.session_state:
    # Define the sequence of nudges for each task per participant
    st.session_state.nudge_sequence = ['A', 'B', 'A']
if 'show_nudge' not in st.session_state:
    st.session_state.show_nudge = False
if 'task_done' not in st.session_state:
    st.session_state.task_done = False
if 'logs' not in st.session_state:
    st.session_state.logs = []

# --- UI Header ---
st.set_page_config(page_title="SecureCode Study", layout="centered")
st.title("🔒 SecureCode Study")
st.write("Complete each coding task and choose whether to run a security tool based on the prompt.")
st.markdown(
    """
    **Study Overview:**  
    In this experiment, you will review and complete coding exercises with potential vulnerabilities.  
    After submission, you'll receive a prompt to run a security analysis tool.  
    We record your choices to study how prompts affect tool usage.
    """
)

# --- Determine Current Task ---
idx = st.session_state.task_index
if idx >= len(tasks):
    st.success("🎉 All tasks completed. Thank you!")
    st.stop()

task = tasks[idx]
nudge_type = st.session_state.nudge_sequence[idx]
nudge_msg = nudges[nudge_type]

# --- Display Task ---
st.header(f"Task {task['id']}: {task['title']}")
st.write("Review the suggested code, edit if needed, then click **Submit**.")

# --- Code Editor ---
code = st_monaco(
    task['code'],
    language="python",
    theme="vs-dark",
    height=500
)

# --- Submission & Nudge Flow ---
if not st.session_state.show_nudge and not st.session_state.task_done:
    if st.button("Submit"):
        st.session_state.show_nudge = True

if st.session_state.show_nudge and not st.session_state.task_done:
    st.subheader("Security Nudge")
    st.write(nudge_msg)
    col1, col2 = st.columns(2)
    if col1.button("Use Tool"):
        # Save code to a temporary file
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.py')
        tmp.write(code.encode())
        tmp.close()
        # Run Bandit static analysis
        result = subprocess.run(
            ['bandit', '-r', tmp.name, '-f', 'json'],
            capture_output=True, text=True
        )
        st.subheader("Tool Output (Bandit)")
        try:
            st.json(json.loads(result.stdout))
        except json.JSONDecodeError:
            st.text(result.stdout)
        # Log interaction
        st.session_state.logs.append({
            'task': task['id'],
            'nudge': nudge_type,
            'used_tool': True,
            'output': result.stdout
        })
        st.session_state.task_done = True
    if col2.button("Skip Tool"):
        st.info("Skipped running the tool.")
        st.session_state.logs.append({
            'task': task['id'],
            'nudge': nudge_type,
            'used_tool': False
        })
        st.session_state.task_done = True

# --- Next Task Navigation ---
if st.session_state.task_done:
    if st.button("Next Task"):
        st.session_state.task_index += 1
        # Reset state for next task
        st.session_state.show_nudge = False
        st.session_state.task_done = False
        # Streamlit automatically reruns on widget interaction; no explicit rerun needed
