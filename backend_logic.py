import asyncio
import feedparser 
import httpx
import re
import json
import os
from datetime import datetime
# Status monitoring using rss 
class RSSStatusMonitor:
    def __init__(self, feeds, state_file="seen_ids.json"):
        self.feeds = feeds
        self.state_file = state_file
        # Load historical state to survive script restarts
        self.seen_entries = self.load_state() 

    def load_state(self):
        """Loads previously seen incident IDs from a local JSON file."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return set(json.load(f))
            except json.JSONDecodeError:
                return set()
        return set()

    def save_state(self):
        """Saves current seen incident IDs to a the JSON file."""
        with open(self.state_file, 'w') as f:
            json.dump(list(self.seen_entries), f)

    async def check_feed(self, client, url):
        try:
            # timeout and HTTP status validation for robustness
            response = await client.get(url, timeout=10.0)
            response.raise_for_status() 
            
            feed = feedparser.parse(response.text)
            
            if not feed.entries:
                return

            # The latest incident is usually the first entry
            latest = feed.entries[0]
            
            # ID extraction
            try:
                entry_id = latest.get('links')[0].get('href').split('incidents/')[1]
            except (IndexError, KeyError):
                # Fallback just in case a different provider doesn't use "incidents/"
                entry_id = latest.get('id', latest.get('link'))

            if not self.seen_entries:
                print("First run detected. Processing the most recent incident...")
                
                # the latest incident
                self.log_incident(latest)
                
                for entry in feed.entries:
                    try:
                        e_id = entry.get('links')[0].get('href').split('incidents/')[1]
                    except (IndexError, KeyError):
                        e_id = entry.get('id', entry.get('link'))
                    self.seen_entries.add(e_id)
                    
                self.save_state()
                print(f"Initialized state with {len(self.seen_entries)} historical incidents from {url}")
                return
            # New Event Detected!
            if entry_id not in self.seen_entries:
                self.seen_entries.add(entry_id)
                self.save_state() # Persist the new event immediately
                self.log_incident(latest)

        except httpx.HTTPStatusError as e:
            print(f"Rate limited or HTTP Error for {url}: {e.response.status_code}")
        except httpx.RequestError as e:
            print(f"Network timeout/error checking {url}: {e}")
        except Exception as e:
            print(f"Unexpected error checking {url}: {e}")

    def log_incident(self, entry):
        dt = entry.get('published')
        
        product_details = entry.get('summary', None)
        if product_details:
            match = re.search(r'<li>(.*?)</li>', product_details, re.IGNORECASE)
            product = match.group(1).strip() if match else 'Unknown'
        else:
            product = 'Unknown'
            
        status_msg = entry.get('title', 'Unknown Service')
        
        print(f"[{dt}] Product: OpenAI - {product}")
        print(f"Status: {status_msg.strip()}\n")

    async def start(self):
        async with httpx.AsyncClient() as client:
            print("Monitoring started...")
            while True:
                tasks = [self.check_feed(client, url) for url in self.feeds]
                await asyncio.gather(*tasks)
                await asyncio.sleep(20) 

if __name__ == "__main__":
    urls = ["https://status.openai.com/feed.rss"] 
    monitor = RSSStatusMonitor(urls)
    asyncio.run(monitor.start())