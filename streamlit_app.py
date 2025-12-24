import streamlit as st
import time

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="SyncRoom", page_icon="🎵", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: white; }
    header { visibility: hidden; }
    .chat-msg {
        padding: 8px;
        background: #1e1e1e;
        border-radius: 5px;
        margin-bottom: 5px;
        border-left: 3px solid #FF4B4B;
    }
    div.stButton > button:first-child {
        background-color: #FF4B4B;
        color: white;
        font-size: 20px;
        height: 3em;
        width: 100%;
        border-radius: 10px; 
    }
</style>
""", unsafe_allow_html=True)

# --- 2. SINGLETON MEMORY ---
class RoomManager:
    def __init__(self):
        self.rooms = {}

    def get_room(self, room_name):
        # Create new room if needed
        if room_name not in self.rooms:
            self.rooms[room_name] = {
                'current_video': None, 
                'queue': [],
                'chat': [],
                'is_paused': False,
                'pause_time': 0
            }
        
        # CRASH FIX: Ensure existing rooms have new keys (if updating from old code)
        room = self.rooms[room_name]
        if 'is_paused' not in room: room['is_paused'] = False
        if 'pause_time' not in room: room['pause_time'] = 0
            
        return room

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
            room['is_paused'] = False
            
            if room['current_video'] is None:
                room['current_video'] = video_data
            else:
                room['queue'].append(video_data)
            return True
        return False

    def toggle_play(self, room_name):
        room = self.get_room(room_name)
        current = room['current_video']
        if not current: return

        if room['is_paused']:
            # RESUME
            room['current_video']['start_time'] = time.time() - room['pause_time']
            room['is_paused'] = False
        else:
            # PAUSE
            elapsed = time.time() - current['start_time']
            room['pause_time'] = elapsed
            room['is_paused'] = True

    def skip(self, room_name):
        room = self.get_room(room_name)
        if room['queue']:
            next_vid = room['queue'].pop(0)
            next_vid['start_time'] = time.time()
            room['current_video'] = next_vid
            room['is_paused'] = False 
        else:
            room['current_video'] = None

    def add_msg(self, room_name, user, text):
        room = self.get_room(room_name)
        room['chat'].insert(0, (user, text))
        if len(room['chat']) > 50: room['chat'].pop()

@st.cache_resource
def get_manager():
    return RoomManager()

manager = get_manager()

# --- 3. UI SETUP ---

with st.sidebar:
    st.header("Login")
    username = st.text_input("Nickname", value="Guest")
    room_name = st.text_input("Room Name", value="party")

if not room_name:
    st.stop()

st.title(f"🎵 SyncRoom: {room_name}")

col1, col2 = st.columns([2, 1])

# --- 4. MAIN THREAD ---
room_data = manager.get_room(room_name)
current = room_data['current_video']

with col1:
    if current:
        is_paused = room_data['is_paused']
        
        if is_paused:
            seek_time = int(room_data['pause_time'])
            autoplay_val = 0
            status_text = "⏸ PAUSED"
        else:
            seek_time = int(time.time() - current['start_time'])
            if seek_time < 0: seek_time = 0
            autoplay_val = 1
            status_text = f"▶ PLAYING: {current['title']}"

        st.info(status_text)
        
        video_html = f"""
        <iframe width="100%" height="450" 
            src="https://www.youtube.com/embed/{current['id']}?start={seek_time}&autoplay={autoplay_val}&controls=0" 
            frameborder="0" allow="autoplay; encrypted-media" allowfullscreen>
        </iframe>
        """
        st.components.v1.html(video_html, height=460)
        
        c1, c2 = st.columns(2)
        with c1:
            btn_label = "▶ RESUME" if is_paused else "⏸ PAUSE"
            if st.button(btn_label):
                manager.toggle_play(room_name)
                st.rerun()
        with c2:
            if st.button("⏭ SKIP"):
                manager.skip(room_name)
                st.rerun()

    else:
        st.container(height=450, border=True).write("Waiting for music...")
        
    new_url = st.text_input("Paste YouTube URL")
    if st.button("Add to Queue"):
        if manager.add_video(room_name, new_url):
            st.success("Added! syncing...")
            time.sleep(0.5)
            st.rerun()
        else:
            st.error("Invalid Link")

# --- 5. BACKGROUND SYNC ---

@st.fragment(run_every=2)
def live_updates_fragment():
    server_room = manager.get_room(room_name)
    server_current = server_room['current_video']
    
    server_id = server_current['id'] if server_current else None
    display_id = current['id'] if current else None
    
    if server_id != display_id:
        st.rerun()

    tab_chat, tab_queue = st.tabs(["💬 Chat", "📜 Queue"])
    
    with tab_chat:
        new_msg = st.chat_input("Say something...")
        if new_msg:
            manager.add_msg(room_name, username, new_msg)
        
        with st.container(height=400):
            for user, msg in manager.get_room(room_name)['chat']:
                st.markdown(f"<div class='chat-msg'><b>{user}:</b> {msg}</div>", unsafe_allow_html=True)

    with tab_queue:
        q = manager.get_room(room_name)['queue']
        if q:
            for idx, v in enumerate(q):
                st.write(f"{idx+1}. {v['title']}")
        else:
            st.write("Queue is empty.")

with col2:
    live_updates_fragment()