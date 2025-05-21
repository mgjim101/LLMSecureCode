import streamlit as st
import pandas as pd
import sqlite3

st.set_page_config(page_title="Dashboard", layout="wide")
st.title("📊 SecureCode Dashboard")

conn = sqlite3.connect("interactions.db", check_same_thread=False)
df   = pd.read_sql("SELECT * FROM interactions", conn)

# compute durations
df['solve_time_s'] = (
  pd.to_datetime(df.timestamp_submit)
  - pd.to_datetime(df.timestamp_start)
).dt.total_seconds()
df['edit_time_s']  = (
  pd.to_datetime(df.timestamp_edit_complete)
  - pd.to_datetime(df.timestamp_tool_decision)
).dt.total_seconds()

# sidebar filters
pid   = st.sidebar.multiselect("Participant", df.participant.unique())
nudge = st.sidebar.multiselect("Nudge",       df.nudge.unique())
if pid:   df = df[df.participant.isin(pid)]
if nudge: df = df[df.nudge.isin(nudge)]

st.markdown("#### Raw interactions")
st.dataframe(df, height=400)

# chart: #tool-uses by nudge A vs B
st.markdown("#### Tool Usage by Nudge (A vs B)")
usage = df.groupby('nudge').used_tool.sum().reset_index().rename(columns={'used_tool':'count_used'})
st.bar_chart(usage.set_index('nudge')['count_used'])