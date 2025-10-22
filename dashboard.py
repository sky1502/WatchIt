import requests
import streamlit as st
import pandas as pd

API = "http://127.0.0.1:4849"

st.set_page_config(page_title="WatchIt Dashboard", layout="wide")
st.title("👀 WatchIt Dashboard")

# Sidebar
child_id = st.sidebar.text_input("Child ID", value="child_main")
limit = st.sidebar.slider("Show last N events", 10, 200, 50)

# Fetch events & decisions
events = requests.get(f"{API}/v1/events", params={"child_id": child_id, "limit": limit}).json()
decisions = requests.get(f"{API}/v1/decisions", params={"child_id": child_id, "limit": limit}).json()

# Events
st.subheader("Recent Events")
if events["events"]:
    df_events = pd.DataFrame(events["events"])
    st.dataframe(df_events)
else:
    st.info("No events logged yet.")

# Decisions
st.subheader("Recent Decisions")
if decisions["decisions"]:
    df_decisions = pd.DataFrame(decisions["decisions"])
    st.dataframe(df_decisions)
else:
    st.info("No decisions recorded yet.")
