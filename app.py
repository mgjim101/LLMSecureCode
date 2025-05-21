import streamlit as st
import sqlite3, os, json, subprocess, tempfile
from datetime import datetime


# ─── Database setup ───────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(__file__)
DB_PATH  = os.path.join(BASE_DIR, "interactions.db")
conn     = sqlite3.connect(DB_PATH, check_same_thread=False)
c        = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS interactions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 participant INTEGER,
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


# ─── JSON loaders ────────────────────────────────────────────────────────────
def load_json(path):
   with open(os.path.join(BASE_DIR, path), encoding="utf-8") as f:
       return json.load(f)


tasks       = [load_json(f"data/tasks/task{i+1}.json") for i in range(3)]
nudges      = {
   'A': load_json("data/nudges/nudgeA.json")["message"],
   'B': load_json("data/nudges/nudgeB.json")["message"]
}
suggestions = [load_json(f"data/suggestions/task{i+1}.json") for i in range(3)]


design = {
 1:{'tasks':[1,2,3],'nudges':['A','B','A']},
 2:{'tasks':[1,3,2],'nudges':['B','A','B']},
 3:{'tasks':[2,1,3],'nudges':['A','B','A']},
 4:{'tasks':[2,3,1],'nudges':['B','A','B']},
 5:{'tasks':[3,1,2],'nudges':['A','B','A']},
 6:{'tasks':[3,2,1],'nudges':['B','A','B']}
}


# ─── Session defaults ────────────────────────────────────────────────────────
for k,v in {
   'pid':None, 'group':None,
   'seq':[], 'nseq':[], 'idx':0,
   'show_nudge':False, 'tool_ran':False, 'editing':False,
   'ts_start':None, 'ts_edit_start':None, 'current_id':None
}.items():
   if k not in st.session_state:
       st.session_state[k] = v


# ─── Page & Project Description ──────────────────────────────────────────────
st.set_page_config(page_title="SecureCode Study", layout="centered")
st.title("🔒 SecureCode Study")
st.markdown(
   """
**What is this study?** 
We’re testing whether developers will run a security-checker when prompted after a code suggestion. 


1. Solve three code-completion tasks. 
2. View three LLM-generated code suggestions per task. 
3. Submit initial code → receive a nudge. 
4. Optionally run Bandit and edit, or skip and proceed.
"""
)


# ─── Participant ID Input & Validation ────────────────────────────────────────
if st.session_state.pid is None:
   pid_str = st.text_input("Enter your Participant ID (1–30)")
   if st.button("Start Experiment"):
       try:
           pid = int(pid_str)
       except:
           st.error("❗ Please enter a valid integer ID.")
           st.stop()
       if pid < 1 or pid > 30:
           st.error("❗ Invalid ID — please enter a number between 1 and 30.")
           st.stop()
       st.session_state.pid = pid
       grp = ((pid - 1) // 5) + 1
       st.session_state.group = grp
       st.session_state.seq   = design[grp]['tasks']
       st.session_state.nseq  = design[grp]['nudges']
   else:
       st.stop()


st.subheader(f"Participant {st.session_state.pid} — Group G{st.session_state.group}")


# ─── Main Experiment Flow ────────────────────────────────────────────────────
idx = st.session_state.idx
if idx >= len(st.session_state.seq):
   st.success("🎉 Experiment complete. Thank you!")
   st.stop()


task_id = st.session_state.seq[idx]
t       = tasks[task_id - 1]
nudge   = st.session_state.nseq[idx]


# record start time
if st.session_state.ts_start is None:
   st.session_state.ts_start = datetime.utcnow().isoformat()


# ─── Display Task & LLM Suggestions ──────────────────────────────────────────
st.header(f"Task {t['id']}: {t['title']}")
st.write("Three LLM suggestions (read-only):")
for i, s in enumerate(suggestions[idx], start=1):
   st.text_area(f"Suggestion {i}", s, height=100, disabled=True)


# ─── Code Editor (text_area) ─────────────────────────────────────────────────
st.write("Your code:")
code_key = f"code_{idx}"
if code_key not in st.session_state:
   st.session_state[code_key] = t['code']
# the text_area widget itself writes its value into session_state[code_key]
code = st.text_area(
   "Edit code here",
   value=st.session_state[code_key],
   height=400,
   key=code_key
)


# ─── Callbacks ────────────────────────────────────────────────────────────────


def advance():
   st.session_state.idx += 1
   for flag in ('show_nudge','tool_ran','editing','ts_start','ts_edit_start','current_id'):
       st.session_state[flag] = None if flag.endswith('_start') or flag=='current_id' else False


def submit_task():
   now = datetime.utcnow().isoformat()
   c.execute("""
     INSERT INTO interactions
       (participant,group_num,task,nudge,timestamp_start,code_pre,timestamp_submit)
     VALUES (?,?,?,?,?,?,?)
   """, (
     st.session_state.pid,
     st.session_state.group,
     t['id'],
     nudge,
     st.session_state.ts_start,
     st.session_state[code_key],
     now
   ))
   conn.commit()
   st.session_state.current_id = c.lastrowid
   st.session_state.show_nudge   = True


def run_tool():
   now    = datetime.utcnow().isoformat()
   lastid = st.session_state.current_id
   tmp    = tempfile.NamedTemporaryFile(delete=False, suffix=".py")
   tmp.write(st.session_state[code_key].encode()); tmp.close()
   res    = subprocess.run(['bandit','-r',tmp.name,'-f','json'],
                           capture_output=True, text=True)
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
   st.session_state.tool_ran      = True


def skip_tool():
   now    = datetime.utcnow().isoformat()
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
   st.session_state.editing      = True
   st.session_state.ts_edit_start = datetime.utcnow().isoformat()


def submit_as_is():
   now    = datetime.utcnow().isoformat()
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
   now    = datetime.utcnow().isoformat()
   start  = datetime.fromisoformat(st.session_state.ts_edit_start)
   delta  = (datetime.utcnow() - start).total_seconds()
   lastid = st.session_state.current_id
   c.execute("""
     UPDATE interactions SET
       code_post=?, timestamp_edit_complete=?, editing_time_sec=?
     WHERE id=?
   """, (st.session_state[code_key], now, delta, lastid))
   conn.commit()
   advance()


# ─── UI Stages ────────────────────────────────────────────────────────────────
if not st.session_state.show_nudge:
   st.button("Submit Task", on_click=submit_task, key=f"submit_{idx}")
elif not st.session_state.tool_ran and not st.session_state.editing:
   st.subheader("🔔 Security Nudge")
   st.write(nudges[nudge])
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



