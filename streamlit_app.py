import streamlit as st
import time

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="SyncRoom", page_icon="🎵", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: white; }
    /* Hide the default header to make it look like an app */
    header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# --- 2. GLOBAL STATE (Server Memory) ---
@st.cache_resource
class RoomManager:
    def __init__(self):
        self.rooms = {}

    def get_room(self, room_name):
        if room_name not in self.rooms:
            self.rooms[room_name] = {
                'current_video': None, 
                'queue': [],
                'chat': []
            }
        return self.rooms[room_name]

    def add_video(self, room_name, url):
        room = self.get_room(room_name)
        vid_id = ""
        # Smart ID extraction
        try:
            if "v=" in url: vid_id = url.split('v=')[1].split('&')[0]
            elif "youtu.be/" in url: vid_id = url.split('youtu.be/')[1].split('?')[0]
        except:
            return False
        
        if vid_id:
            video_data = {'id': vid_id, 'title': f"Video {vid_id}", 'start_time': time.time()}
            # If nothing playing, play now
            if room['current_video'] is None:
                room['current_video'] = video_data
            else:
                room['queue'].append(video_data)
            return True
        return False

    def skip(self, room_name):
        room = self.get_room(room_name)
        if room['queue']:
            next_vid = room['queue'].pop(0)
            next_vid['start_time'] = time.time()
            room['current_video'] = next_vid
        else:
            room['current_video'] = None

    def add_msg(self, room_name, user, text):
        room = self.get_room(room_name)
        room['chat'].append(f"**{user}:** {text}")

manager = RoomManager()

# --- 3. UI SETUP ---

# Login Sidebar
with st.sidebar:
    st.header("Login")
    username = st.text_input("Nickname", value="Guest")
    room_name = st.text_input("Room Name", value="party")

if not room_name:
    st.stop()

st.title(f"🎵 SyncRoom: {room_name}")

col1, col2 = st.columns([2, 1])

# --- 4. VIDEO PLAYER (Main Page - Does NOT Refresh Automatically) ---
# This code runs only once when the page loads or when we force a reload.
room_data = manager.get_room(room_name)
current = room_data['current_video']

with col1:
    if current:
        # Calculate time once when page loads
        elapsed = int(time.time() - current['start_time'])
        st.info(f"▶ Now Playing: {current['title']}")
        
        # We embed the video with the calculated start time
        video_html = f"""
        <iframe width="100%" height="450" 
            src="https://www.youtube.com/embed/{current['id']}?start={elapsed}&autoplay=1&controls=1" 
            frameborder="0" allow="autoplay; encrypted-media" allowfullscreen>
        </iframe>
        """
        st.components.v1.html(video_html, height=460)
        
        # Skip Button (Triggers full reload to change song)
        if st.button("⏭ Skip Song"):
            manager.skip(room_name)
            st.rerun()
    else:
        st.container(height=450, border=True).write("Waiting for music...")
        
    # Add Song Input
    new_url = st.text_input("Paste YouTube URL")
    if st.button("Add to Queue"):
        if manager.add_video(room_name, new_url):
            st.success("Added!")
            st.rerun() # Rerun to start playing immediately if empty
        else:
            st.error("Invalid Link")

# --- 5. CHAT & SYNC (Fragment - Refreshes Independent of Video!) ---
# This is the MAGIC part. It refreshes every 2 seconds BUT leaves the video alone.

@st.fragment(run_every=2)
def live_updates():
    # 1. Check if we need to force a video update
    # If the song in memory is different from the one on screen, we MUST reload the whole page
    server_current = manager.get_room(room_name)['current_video']
    
    # Check if a new song started while we were watching
    # We compare IDs. If they don't match, the song changed.
    server_id = server_current['id'] if server_current else None
    display_id = current['id'] if current else None
    
    if server_id != display_id:
        st.rerun() # Force main page reload to switch video

    # 2. Render Chat & Queue
    with col2:
        tab_chat, tab_queue = st.tabs(["💬 Chat", "📜 Queue"])
        
        with tab_chat:
            # We use a container to keep chat scrollable-ish
            with st.container(height=400):
                for msg in manager.get_room(room_name)['chat']:
                    st.write(msg)
            
            # Chat Input inside fragment
            msg = st.chat_input("Type a message...")
            if msg:
                manager.add_msg(room_name, username, msg)
                # No rerun needed here, the fragment loop will pick it up

        with tab_queue:
            q = manager.get_room(room_name)['queue']
            if q:
                for idx, v in enumerate(q):
                    st.write(f"{idx+1}. {v['title']}")
            else:
                st.write("Queue is empty.")

# Run the live fragment
live_updates()