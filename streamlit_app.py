import streamlit as st
import time

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="SyncRoom", page_icon="🎵", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: white; }
    /* Hide the default header */
    header { visibility: hidden; }
    /* Style the chat history box */
    .chat-box {
        border: 1px solid #333;
        border-radius: 5px;
        padding: 10px;
        background-color: #1e1e1e;
        height: 350px;
        overflow-y: auto;
    }
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
        try:
            if "v=" in url: vid_id = url.split('v=')[1].split('&')[0]
            elif "youtu.be/" in url: vid_id = url.split('youtu.be/')[1].split('?')[0]
        except:
            return False
        
        if vid_id:
            video_data = {'id': vid_id, 'title': f"Video {vid_id}", 'start_time': time.time()}
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
        # Add message to the TOP
        room['chat'].insert(0, f"**{user}:** {text}")
        if len(room['chat']) > 50: room['chat'].pop()

manager = RoomManager()

# --- 3. UI SETUP ---

with st.sidebar:
    st.header("Login")
    username = st.text_input("Nickname", value="Guest")
    room_name = st.text_input("Room Name", value="party")

if not room_name:
    st.stop()

st.title(f"🎵 SyncRoom: {room_name}")

col1, col2 = st.columns([2, 1])

# --- 4. VIDEO PLAYER (Left Column - Main Thread) ---
room_data = manager.get_room(room_name)
current = room_data['current_video']

with col1:
    if current:
        elapsed = int(time.time() - current['start_time'])
        st.info(f"▶ Now Playing: {current['title']}")
        
        video_html = f"""
        <iframe width="100%" height="450" 
            src="https://www.youtube.com/embed/{current['id']}?start={elapsed}&autoplay=1&controls=1" 
            frameborder="0" allow="autoplay; encrypted-media" allowfullscreen>
        </iframe>
        """
        st.components.v1.html(video_html, height=460)
        
        if st.button("⏭ Skip Song"):
            manager.skip(room_name)
            st.rerun()
    else:
        st.container(height=450, border=True).write("Waiting for music...")
        
    new_url = st.text_input("Paste YouTube URL")
    if st.button("Add to Queue"):
        if manager.add_video(room_name, new_url):
            st.success("Added!")
            st.rerun()
        else:
            st.error("Invalid Link")

# --- 5. CHAT & QUEUE (Right Column - Fragment) ---
# This runs safely inside col2 because we call it inside col2 below

@st.fragment(run_every=2)
def live_updates_fragment():
    # Sync Check: If song changed on server, force full page reload
    server_current = manager.get_room(room_name)['current_video']
    server_id = server_current['id'] if server_current else None
    display_id = current['id'] if current else None
    
    if server_id != display_id:
        st.rerun()

    # Tabs
    tab_chat, tab_queue = st.tabs(["💬 Chat", "📜 Queue"])
    
    with tab_chat:
        # Chat Input
        # Note: In Streamlit fragments, we can't easily clear the input after sending 
        # without complex session state, so users will have to delete text manually 
        # or press enter.
        new_msg = st.text_input("Say something...", key=f"chat_{int(time.time())}")
        if new_msg:
            manager.add_msg(room_name, username, new_msg)
            # No rerun needed, the loop will update the list below next cycle

        # Chat History
        with st.container(height=400):
            for msg in manager.get_room(room_name)['chat']:
                st.write(msg)

    with tab_queue:
        q = manager.get_room(room_name)['queue']
        if q:
            for idx, v in enumerate(q):
                st.write(f"{idx+1}. {v['title']}")
        else:
            st.write("Queue is empty.")

# --- CALL FRAGMENT INSIDE COLUMN ---
with col2:
    live_updates_fragment()