import streamlit as st
import feedparser
import httpx
import re
import json
import os
import asyncio
from datetime import datetime
import time

st.set_page_config(page_title="Service Status Monitor", page_icon="🟢", layout="wide")

class StreamlitRSSMonitor:
    def __init__(self, state_file="seen_ids.json"):
        self.state_file = state_file
        self.seen_entries = self.load_state()
# loading the previous state
    def load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return set(json.load(f))
            except json.JSONDecodeError:
                return set()
        return set()
# save the history of the ids for comparison
    def save_state(self):
        with open(self.state_file, 'w') as f:
            json.dump(list(self.seen_entries), f)
# checking whether the feed encounters a new update
    async def check_feed(self, url):
        new_incidents = []
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10.0)
                response.raise_for_status()
# Handling the .rss content
            feed = feedparser.parse(response.text)
            if not feed.entries: 
                return new_incidents

            current_ids = set()
            for entry in feed.entries:
                try:
                    e_id = entry.get('links')[0].get('href').split('incidents/')[1]
                except (IndexError, KeyError):
                    e_id = entry.get('id', entry.get('link'))
                current_ids.add(e_id)
            if not self.seen_entries:
                # show the most recent update
                latest_entry = feed.entries[0]
                new_incidents.append(self.parse_incident(latest_entry))
                
                # current_id to be added into seen
                self.seen_entries = current_ids
                self.save_state()
                return new_incidents 

            # Detect new entries
            new_ids = current_ids - self.seen_entries
            for entry in feed.entries:
                try:
                    e_id = entry.get('links')[0].get('href').split('incidents/')[1]
                except (IndexError, KeyError):
                    e_id = entry.get('id', entry.get('link'))
                    
                if e_id in new_ids:
                    new_incidents.append(self.parse_incident(entry))
                    self.seen_entries.add(e_id)
            
            if new_ids:
                self.save_state()
                
        except Exception as e:
            st.sidebar.error(f"Error checking {url}: {e}")
            
        return new_incidents

    def parse_incident(self, entry):
        dt = entry.get('published', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        product_details = entry.get('summary', '')
        match = re.search(r'<li>(.*?)</li>', product_details, re.IGNORECASE)
        product = match.group(1).strip() if match else 'Unknown'
        status_msg = entry.get('title', 'Unknown Service Update')
        
        return {"timestamp": dt, "product": f"OpenAI - {product}", "status": status_msg.strip()}


if "monitor" not in st.session_state:
    st.session_state.monitor = StreamlitRSSMonitor()
if "incident_log" not in st.session_state:
    st.session_state.incident_log = []
if "is_running" not in st.session_state:
    st.session_state.is_running = False


st.title("🟢 Active Service Status Monitor")
st.markdown("Real-time event tracking...")


with st.sidebar:
    st.header("⚙️ Settings")
    # user controllable urla and polling interval
    target_url = st.text_input("RSS Feed URL", value="https://status.openai.com/feed.rss")
    poll_interval = st.slider("Polling Interval (seconds)", min_value=10, max_value=60, value=20)
    
    if st.button("Start or Stop Monitoring"):
        st.session_state.is_running = not st.session_state.is_running

    st.write("---")
    st.write(f"**Engine Status:** {'🟢 Polling Active' if st.session_state.is_running else '🔴 Paused'}")
    st.write(f"**Historical DB Size:** {len(st.session_state.monitor.seen_entries)} incidents")



def run_check():
    new_alerts = asyncio.run(st.session_state.monitor.check_feed(target_url))
    if new_alerts:
        st.session_state.incident_log = new_alerts + st.session_state.incident_log

if st.session_state.is_running:
    run_check()

# Render Logs
if not st.session_state.incident_log:
    st.info("No new incidents detected during this session. Waiting for updates...")
else:
    for incident in st.session_state.incident_log:
        with st.container():
            st.error(f"{incident['timestamp']} | Product - **{incident['product']}**")
            st.write(f"Status: {incident['status']}")
            st.write("---")

if st.session_state.is_running:
    time.sleep(poll_interval)
    st.rerun()