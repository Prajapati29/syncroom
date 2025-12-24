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
</style>
""", unsafe_allow_html=True)

# --- 2. TRUE SINGLETON MEMORY ---
# We define the class normally, then use a specific function to cache the INSTANCE.
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
            # RESET start time to now so everyone syncs
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
        room['chat'].insert(0, (user, text))
        if len(room['chat']) > 50: room['chat'].pop()

# This decorator ensures we only create ONE manager for the whole server
@st.cache_resource
def get_manager():
    return RoomManager()

manager = get_manager()

# --- 3. UI SETUP ---

with st.sidebar:
    st.header("Login")
    username = st.text_input("Nickname", value="Guest")
    # Using a fixed room name for simplicity, or let users type
    room_name = st.text_input("Room Name", value="party")

if not room_name:
    st.stop()

st.title(f"🎵 SyncRoom: {room_name}")

col1, col2 = st.columns([2, 1])

# --- 4. MAIN THREAD (Video Player) ---
# This part handles the video. It only reloads when the song changes.
room_data = manager.get_room(room_name)
current = room_data['current_video']

with col1:
    if current:
        # Calculate how many seconds have passed since the song started on the server
        elapsed = int(time.time() - current['start_time'])
        
        # Guard against negative time (if clocks are slightly off)
        if elapsed < 0: elapsed = 0
        
        st.info(f"▶ Now Playing: {current['title']}")
        
        # Autoplay=1 is crucial here. 
        # mute=0 might be blocked by browsers, but we try.
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
            st.success("Added! syncing...")
            time.sleep(0.5) # Give the server a moment to update
            st.rerun()
        else:
            st.error("Invalid Link")

# --- 5. BACKGROUND SYNC (Chat & Updates) ---
# This runs every 2 seconds to check if the other user changed the song.

@st.fragment(run_every=2)
def live_updates_fragment():
    # A. SYNC CHECK
    # We fetch the latest server state
    server_current = manager.get_room(room_name)['current_video']
    
    # We compare it to what is currently on the screen (captured from main thread)
    server_id = server_current['id'] if server_current else None
    display_id = current['id'] if current else None
    
    # If they don't match, someone changed the song! Force a reload.
    if server_id != display_id:
        st.rerun()

    # B. CHAT & QUEUE TABS
    tab_chat, tab_queue = st.tabs(["💬 Chat", "📜 Queue"])
    
    with tab_chat:
        # Chat Input
        # We use a static key. Note: Streamlit resets input on interaction in fragments,
        # so this is basic. For full chat apps, we'd use session state, but this works for basic syncing.
        new_msg = st.chat_input("Say something...")
        if new_msg:
            manager.add_msg(room_name, username, new_msg)
        
        # Show Messages
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

# CALL THE FRAGMENT
with col2:
    live_updates_fragment()