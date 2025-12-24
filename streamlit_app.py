import streamlit as st
import time
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="SyncRoom (Streamlit)", page_icon="🎵", layout="wide")

# Force dark theme style
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: white; }
    .stButton>button { width: 100%; border-radius: 5px; background: #FF4B4B; color: white; }
    .css-1r6slb0 { background-color: #262730; } 
</style>
""", unsafe_allow_html=True)

# --- 2. GLOBAL STATE (The "Server" Memory) ---
# We use @st.cache_resource to create a "Shared Memory" that lives across all users
@st.cache_resource
class RoomManager:
    def __init__(self):
        self.rooms = {}

    def get_room(self, room_name):
        if room_name not in self.rooms:
            self.rooms[room_name] = {
                'current_video': None, # {'url': '...', 'title': '...', 'start_time': 12345}
                'queue': [],
                'chat': []
            }
        return self.rooms[room_name]

    def add_video(self, room_name, url):
        room = self.get_room(room_name)
        # Extract ID
        vid_id = ""
        if "v=" in url: vid_id = url.split('v=')[1].split('&')[0]
        elif "youtu.be/" in url: vid_id = url.split('youtu.be/')[1].split('?')[0]
        
        if vid_id:
            video_data = {'id': vid_id, 'url': url, 'title': f"Video {vid_id}"}
            
            if room['current_video'] is None:
                video_data['start_time'] = time.time()
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
        if len(room['chat']) > 50: room['chat'].pop(0) # Keep chat small

manager = RoomManager()

# --- 3. AUTO-REFRESH (The "Socket" Replacement) ---
# Streamlit doesn't push updates, so we force the page to reload every 2 seconds
count = st_autorefresh(interval=2000, key="fizzbuzz")

# --- 4. APP LOGIC ---

# Sidebar: Login
with st.sidebar:
    st.header("🔑 Login")
    username = st.text_input("Nickname", value="Guest")
    room_name = st.text_input("Room Name", value="party")

if not room_name:
    st.warning("Please enter a room name.")
    st.stop()

# Get Room Data
room_data = manager.get_room(room_name)

# --- MAIN UI ---
st.title(f"🎵 SyncRoom: {room_name}")

col1, col2 = st.columns([2, 1])

# LEFT: Video Player
with col1:
    current = room_data['current_video']
    
    if current:
        # Calculate sync time
        elapsed = int(time.time() - current['start_time'])
        
        st.info(f"▶ Now Playing: {current['title']}")
        
        # We use HTML embed because st.video doesn't allow specific start times well
        video_embed_code = f"""
        <iframe width="100%" height="450" 
            src="https://www.youtube.com/embed/{current['id']}?start={elapsed}&autoplay=1&controls=1" 
            frameborder="0" allow="autoplay; encrypted-media" allowfullscreen>
        </iframe>
        """
        st.components.v1.html(video_embed_code, height=460)
        
        if st.button("⏭ Skip Song"):
            manager.skip(room_name)
            st.rerun()
            
    else:
        st.container(height=450, border=True).write("Waiting for music...")
        st.warning("Queue is empty.")

    # Add Song Input
    new_url = st.text_input("Paste YouTube URL")
    if st.button("Add to Queue"):
        if manager.add_video(room_name, new_url):
            st.success("Added!")
            time.sleep(0.5)
            st.rerun()
        else:
            st.error("Invalid Link")

# RIGHT: Chat & Queue
with col2:
    tab1, tab2 = st.tabs(["💬 Chat", "📜 Queue"])
    
    with tab1:
        chat_container = st.container(height=400, border=True)
        for msg in room_data['chat']:
            chat_container.markdown(msg)
            
        msg_text = st.text_input("Message", key="chat_input")
        if st.button("Send"):
            manager.add_msg(room_name, username, msg_text)
            st.rerun()

    with tab2:
        if room_data['queue']:
            for i, vid in enumerate(room_data['queue']):
                st.write(f"{i+1}. {vid['title']}")
        else:
            st.write("No upcoming songs.")