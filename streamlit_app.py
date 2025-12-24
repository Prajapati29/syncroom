import streamlit as st
import time
import re
import requests
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="SyncRoom (Streamlit)", page_icon="🎵", layout="wide")

# Force dark theme style
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: white; }
    .stButton>button { width: 100%; border-radius: 5px; background: #FF4B4B; color: white; }
    .css-1r6slb0 { background-color: #262730; }
    .chat-message { padding: 10px; border-radius: 10px; margin: 5px 0; }
    .user-message { background-color: #262730; }
    .system-message { background-color: #1a5fb4; font-style: italic; }
    .video-card { padding: 10px; border-radius: 8px; background-color: #1e1e1e; margin: 5px 0; }
</style>
""", unsafe_allow_html=True)

# --- 2. GLOBAL STATE (The "Server" Memory) ---
@st.cache_resource
class RoomManager:
    def __init__(self):
        self.rooms = {}
        self.users = {}  # Track active users by room
        self.room_activity = {}  # Track last activity time for cleanup
    
    def get_room(self, room_name):
        if room_name not in self.rooms:
            self.rooms[room_name] = {
                'current_video': None,  # {'id': '...', 'url': '...', 'title': '...', 'start_time': 12345}
                'queue': [],
                'chat': [],
                'paused': False,
                'pause_time': None,
                'total_pause_duration': 0
            }
            self.users[room_name] = set()
            self.room_activity[room_name] = time.time()
        return self.rooms[room_name]
    
    def add_user(self, room_name, username):
        room = self.get_room(room_name)
        if username in self.users[room_name]:
            return False, "Username already taken"
        self.users[room_name].add(username)
        self.add_msg(room_name, "System", f"{username} joined the room")
        return True, ""
    
    def remove_user(self, room_name, username):
        if room_name in self.users and username in self.users[room_name]:
            self.users[room_name].remove(username)
            self.add_msg(room_name, "System", f"{username} left the room")
    
    def add_video(self, room_name, url, username=""):
        room = self.get_room(room_name)
        
        # Extract and validate video ID
        video_id = self.extract_video_id(url)
        if not video_id:
            return False, "Invalid YouTube URL"
        
        # Get video info
        video_info = get_video_info(video_id)
        
        video_data = {
            'id': video_id,
            'url': url,
            'title': video_info['title'],
            'thumbnail': video_info['thumbnail'],
            'author': video_info['author'],
            'added_by': username,
            'added_at': time.time()
        }
        
        if room['current_video'] is None:
            video_data['start_time'] = time.time()
            room['current_video'] = video_data
            message = "Started playing"
        else:
            room['queue'].append(video_data)
            message = "Added to queue"
        
        self.room_activity[room_name] = time.time()
        if username:
            self.add_msg(room_name, "System", f"{username} {message}: {video_info['title']}")
        
        return True, message
    
    def extract_video_id(self, url):
        """Extract YouTube video ID from various URL formats"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=)([\w-]{11})',
            r'(?:youtu\.be\/)([\w-]{11})',
            r'(?:youtube\.com\/embed\/)([\w-]{11})',
            r'(?:youtube\.com\/v\/)([\w-]{11})',
            r'(?:youtube\.com\/shorts\/)([\w-]{11})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        # Also check if it's just a video ID
        if re.match(r'^[\w-]{11}$', url.strip()):
            return url.strip()
        
        return None
    
    def skip(self, room_name, username=""):
        room = self.get_room(room_name)
        if room['queue']:
            next_vid = room['queue'].pop(0)
            next_vid['start_time'] = time.time() - room.get('total_pause_duration', 0)
            room['current_video'] = next_vid
            room['paused'] = False
            room['pause_time'] = None
            room['total_pause_duration'] = 0
            
            self.room_activity[room_name] = time.time()
            if username:
                self.add_msg(room_name, "System", f"{username} skipped to: {next_vid['title']}")
            return True
        else:
            room['current_video'] = None
            if username:
                self.add_msg(room_name, "System", f"{username} stopped playback")
            return False
    
    def remove_from_queue(self, room_name, index, username=""):
        room = self.get_room(room_name)
        if 0 <= index < len(room['queue']):
            removed = room['queue'].pop(index)
            self.room_activity[room_name] = time.time()
            if username:
                self.add_msg(room_name, "System", f"{username} removed: {removed['title']}")
            return True
        return False
    
    def move_in_queue(self, room_name, from_idx, to_idx, username=""):
        room = self.get_room(room_name)
        if 0 <= from_idx < len(room['queue']) and 0 <= to_idx < len(room['queue']):
            item = room['queue'].pop(from_idx)
            room['queue'].insert(to_idx, item)
            self.room_activity[room_name] = time.time()
            if username:
                self.add_msg(room_name, "System", f"{username} moved song in queue")
            return True
        return False
    
    def clear_queue(self, room_name, username=""):
        room = self.get_room(room_name)
        room['queue'].clear()
        self.room_activity[room_name] = time.time()
        if username:
            self.add_msg(room_name, "System", f"{username} cleared the queue")
    
    def toggle_pause(self, room_name, username=""):
        room = self.get_room(room_name)
        if room['current_video']:
            if not room['paused']:
                room['paused'] = True
                room['pause_time'] = time.time()
                action = "paused"
            else:
                room['paused'] = False
                if room['pause_time']:
                    pause_duration = time.time() - room['pause_time']
                    room['total_pause_duration'] += pause_duration
                room['pause_time'] = None
                action = "resumed"
            
            self.room_activity[room_name] = time.time()
            if username:
                self.add_msg(room_name, "System", f"{username} {action} the video")
            return True
        return False
    
    def add_msg(self, room_name, user, text):
        room = self.get_room(room_name)
        timestamp = datetime.now().strftime("%H:%M")
        room['chat'].append({
            'user': user,
            'text': text,
            'time': timestamp
        })
        if len(room['chat']) > 100:  # Keep chat manageable
            room['chat'].pop(0)
        self.room_activity[room_name] = time.time()
    
    def list_rooms(self):
        return list(self.rooms.keys())
    
    def cleanup_inactive_rooms(self, max_inactive_time=7200):  # 2 hours
        current_time = time.time()
        to_remove = []
        for room_name, last_active in self.room_activity.items():
            if current_time - last_active > max_inactive_time:
                to_remove.append(room_name)
        
        for room_name in to_remove:
            if room_name in self.rooms:
                del self.rooms[room_name]
            if room_name in self.users:
                del self.users[room_name]
            if room_name in self.room_activity:
                del self.room_activity[room_name]
        
        return len(to_remove)

def get_video_info(video_id):
    """Fetch video title and thumbnail using YouTube oEmbed"""
    try:
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            return {
                'title': data.get('title', f'Video {video_id}'),
                'thumbnail': data.get('thumbnail_url', ''),
                'author': data.get('author_name', 'Unknown')
            }
    except:
        pass
    
    # Fallback if API fails
    return {
        'title': f'Video {video_id}',
        'thumbnail': f'https://img.youtube.com/vi/{video_id}/0.jpg',
        'author': 'Unknown'
    }

# --- 3. AUTO-REFRESH ---
manager = RoomManager()

# Clean up inactive rooms periodically
if 'last_cleanup' not in st.session_state or time.time() - st.session_state.last_cleanup > 300:  # Every 5 minutes
    cleaned = manager.cleanup_inactive_rooms()
    if cleaned > 0:
        st.write(f"Cleaned up {cleaned} inactive rooms")
    st.session_state.last_cleanup = time.time()

# Determine refresh interval based on activity
refresh_interval = 1000  # Default: 1 second

# --- 4. APP LOGIC ---

# Sidebar: Login and Room Info
with st.sidebar:
    st.header("🔑 SyncRoom")
    
    # Room selection
    all_rooms = manager.list_rooms()
    selected_room = st.selectbox(
        "Select or create room",
        options=["Create New Room"] + all_rooms,
        index=0 if len(all_rooms) == 0 else 1
    )
    
    if selected_room == "Create New Room":
        room_name = st.text_input("New Room Name", value="party-room")
        if st.button("Create Room"):
            if room_name:
                st.success(f"Created room: {room_name}")
                st.rerun()
            else:
                st.error("Please enter a room name")
        st.stop()
    else:
        room_name = selected_room
    
    # User login
    username = st.text_input("Your Nickname", value="Guest")
    
    # Join room
    if st.button("Join Room"):
        success, message = manager.add_user(room_name, username)
        if success:
            st.success(f"Joined as {username}")
            st.session_state.joined = True
            st.session_state.username = username
            st.rerun()
        else:
            st.error(message)
    
    # Leave room
    if st.button("Leave Room"):
        if 'username' in st.session_state:
            manager.remove_user(room_name, st.session_state.username)
            st.session_state.joined = False
            st.success("Left the room")
            st.rerun()
    
    # Room info
    if room_name in manager.users:
        st.divider()
        st.subheader("👥 Room Info")
        st.write(f"**Room:** {room_name}")
        st.write(f"**Users online:** {len(manager.users[room_name])}")
        if manager.users[room_name]:
            st.write("Active users:")
            for user in sorted(manager.users[room_name]):
                st.write(f"• {user}")

# Check if user has joined
if 'joined' not in st.session_state or not st.session_state.joined:
    st.info("👈 Please join a room from the sidebar")
    st.stop()

username = st.session_state.username
room_data = manager.get_room(room_name)

# Adjust refresh rate based on whether video is playing
if room_data['current_video'] and not room_data['paused']:
    refresh_interval = 1000  # 1 second when playing
else:
    refresh_interval = 3000  # 3 seconds when idle

count = st_autorefresh(interval=refresh_interval, key="autorefresh")

# --- MAIN UI ---
st.title(f"🎵 SyncRoom: {room_name}")
st.caption(f"Logged in as: {username} | Users online: {len(manager.users.get(room_name, []))}")

col1, col2 = st.columns([2, 1])

# LEFT: Video Player
with col1:
    current = room_data['current_video']
    
    if current:
        # Calculate sync time considering pauses
        if room_data['paused'] and room_data['pause_time']:
            current_pause_duration = time.time() - room_data['pause_time']
        else:
            current_pause_duration = 0
        
        total_pause = room_data.get('total_pause_duration', 0) + current_pause_duration
        elapsed = int(time.time() - current['start_time'] - total_pause)
        
        # Video player header
        col_header1, col_header2, col_header3 = st.columns([3, 1, 1])
        with col_header1:
            st.info(f"▶ **Now Playing:** {current['title']}")
        with col_header2:
            status = "⏸ Paused" if room_data['paused'] else "▶ Playing"
            st.write(status)
        with col_header3:
            st.write(f"⏱ {elapsed // 60}:{elapsed % 60:02d}")
        
        # Video player
        video_url = f"https://www.youtube.com/embed/{current['id']}?start={elapsed}&controls=1&modestbranding=1"
        st.components.v1.html(f"""
        <iframe width="100%" height="450" 
            src="{video_url}" 
            frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
            allowfullscreen>
        </iframe>
        """, height=460)
        
        # Playback controls
        col_controls1, col_controls2, col_controls3 = st.columns(3)
        with col_controls1:
            if st.button("⏭ Skip", use_container_width=True):
                manager.skip(room_name, username)
                st.rerun()
        with col_controls2:
            pause_text = "▶ Resume" if room_data['paused'] else "⏸ Pause"
            if st.button(pause_text, use_container_width=True):
                manager.toggle_pause(room_name, username)
                st.rerun()
        with col_controls3:
            if st.button("🔄 Refresh Player", use_container_width=True):
                st.rerun()
        
        # Video info
        with st.expander("Video Details"):
            st.write(f"**Title:** {current['title']}")
            st.write(f"**Added by:** {current.get('added_by', 'Unknown')}")
            if 'added_at' in current:
                added_time = datetime.fromtimestamp(current['added_at']).strftime("%H:%M:%S")
                st.write(f"**Added at:** {added_time}")
            
    else:
        st.container(height=450, border=True).write("🎵 No video playing")
        st.info("Add a song to start the party!")
    
    # Add Song Section
    st.divider()
    st.subheader("➕ Add Music")
    
    tab_add1, tab_add2 = st.tabs(["Direct URL", "Search"])
    
    with tab_add1:
        new_url = st.text_input("Paste YouTube URL or Video ID", key="url_input")
        if st.button("Add to Queue", key="add_url"):
            if new_url:
                success, message = manager.add_video(room_name, new_url, username)
                if success:
                    st.success(f"{message}: {new_url}")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(message)
    
    with tab_add2:
        st.info("Search functionality requires YouTube API key")
        search_query = st.text_input("Search YouTube", disabled=True)
        if st.button("Search", disabled=True):
            st.warning("Search feature coming soon!")

# RIGHT: Chat & Queue
with col2:
    tab1, tab2 = st.tabs(["💬 Chat", "📜 Queue"])
    
    with tab1:
        chat_container = st.container(height=350, border=True)
        
        # Display chat messages
        for msg in room_data['chat'][-20:]:  # Show last 20 messages
            with chat_container:
                if msg['user'] == "System":
                    st.markdown(f"<div class='chat-message system-message'>*[{msg['time']}] {msg['text']}*</div>", 
                              unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='chat-message user-message'><strong>{msg['user']}</strong> [{msg['time']}]: {msg['text']}</div>", 
                              unsafe_allow_html=True)
        
        # Chat input
        msg_text = st.text_input("Type your message...", key="chat_input")
        col_send, col_clear = st.columns([3, 1])
        with col_send:
            if st.button("Send", use_container_width=True):
                if msg_text.strip():
                    manager.add_msg(room_name, username, msg_text.strip())
                    st.rerun()
        with col_clear:
            if st.button("Clear", use_container_width=True):
                if room_data['chat']:
                    room_data['chat'].clear()
                    st.rerun()
    
    with tab2:
        queue_container = st.container(height=350, border=True)
        
        if room_data['queue']:
            queue_container.write(f"**Next up ({len(room_data['queue'])} songs):**")
            
            for i, vid in enumerate(room_data['queue']):
                with queue_container:
                    col_queue1, col_queue2, col_queue3 = st.columns([4, 1, 1])
                    with col_queue1:
                        st.write(f"**{i+1}.** {vid['title']}")
                        if vid.get('added_by'):
                            st.caption(f"Added by: {vid['added_by']}")
                    with col_queue2:
                        if st.button("↑", key=f"up_{i}", help="Move up"):
                            if i > 0:
                                manager.move_in_queue(room_name, i, i-1, username)
                                st.rerun()
                    with col_queue3:
                        if st.button("🗑", key=f"del_{i}", help="Remove"):
                            manager.remove_from_queue(room_name, i, username)
                            st.rerun()
            
            # Queue management buttons
            st.divider()
            col_q1, col_q2 = st.columns(2)
            with col_q1:
                if st.button("Clear Queue", use_container_width=True):
                    if st.checkbox("Are you sure?"):
                        manager.clear_queue(room_name, username)
                        st.rerun()
            with col_q2:
                if st.button("Shuffle Queue", use_container_width=True, disabled=True):
                    st.info("Shuffle coming soon!")
        else:
            queue_container.write("Queue is empty")
            queue_container.info("Add some songs to get started!")

# --- ROOM ADMIN SECTION (Bottom) ---
st.divider()
with st.expander("⚙️ Room Administration"):
    admin_col1, admin_col2, admin_col3 = st.columns(3)
    
    with admin_col1:
        st.write("**Room Status**")
        st.write(f"Active users: {len(manager.users.get(room_name, []))}")
        st.write(f"Chat messages: {len(room_data['chat'])}")
        st.write(f"Queue length: {len(room_data['queue'])}")
        
        last_active = manager.room_activity.get(room_name, 0)
        if last_active:
            last_active_str = datetime.fromtimestamp(last_active).strftime("%H:%M:%S")
            st.write(f"Last activity: {last_active_str}")
    
    with admin_col2:
        st.write("**Quick Actions**")
        if st.button("Skip Current Song", key="admin_skip"):
            manager.skip(room_name, username)
            st.rerun()
        
        if st.button("Clear Chat", key="admin_chat"):
            room_data['chat'].clear()
            st.rerun()
        
        if st.button("Export Playlist", key="admin_export", disabled=True):
            st.info("Export feature coming soon!")
    
    with admin_col3:
        st.write("**Debug Info**")
        if st.checkbox("Show raw room data"):
            st.json(room_data)
        
        if st.button("Force Refresh"):
            st.rerun()

# --- FOOTER ---
st.divider()
st.caption("SyncRoom v1.0 • Made with Streamlit • Auto-refresh every 1-3 seconds")









# import streamlit as st
# import time

# # --- 1. CONFIGURATION ---
# st.set_page_config(page_title="SyncRoom", page_icon="🎵", layout="wide")

# st.markdown("""
# <style>
#     .stApp { background-color: #0e1117; color: white; }
#     header { visibility: hidden; }
#     .chat-msg {
#         padding: 8px;
#         background: #1e1e1e;
#         border-radius: 5px;
#         margin-bottom: 5px;
#         border-left: 3px solid #FF4B4B;
#     }
# </style>
# """, unsafe_allow_html=True)

# # --- 2. TRUE SINGLETON MEMORY ---
# # We define the class normally, then use a specific function to cache the INSTANCE.
# class RoomManager:
#     def __init__(self):
#         self.rooms = {}

#     def get_room(self, room_name):
#         if room_name not in self.rooms:
#             self.rooms[room_name] = {
#                 'current_video': None, 
#                 'queue': [],
#                 'chat': []
#             }
#         return self.rooms[room_name]

#     def add_video(self, room_name, url):
#         room = self.get_room(room_name)
#         vid_id = ""
#         try:
#             if "v=" in url: vid_id = url.split('v=')[1].split('&')[0]
#             elif "youtu.be/" in url: vid_id = url.split('youtu.be/')[1].split('?')[0]
#         except:
#             return False
        
#         if vid_id:
#             # RESET start time to now so everyone syncs
#             video_data = {'id': vid_id, 'title': f"Video {vid_id}", 'start_time': time.time()}
            
#             if room['current_video'] is None:
#                 room['current_video'] = video_data
#             else:
#                 room['queue'].append(video_data)
#             return True
#         return False

#     def skip(self, room_name):
#         room = self.get_room(room_name)
#         if room['queue']:
#             next_vid = room['queue'].pop(0)
#             next_vid['start_time'] = time.time()
#             room['current_video'] = next_vid
#         else:
#             room['current_video'] = None

#     def add_msg(self, room_name, user, text):
#         room = self.get_room(room_name)
#         room['chat'].insert(0, (user, text))
#         if len(room['chat']) > 50: room['chat'].pop()

# # This decorator ensures we only create ONE manager for the whole server
# @st.cache_resource
# def get_manager():
#     return RoomManager()

# manager = get_manager()

# # --- 3. UI SETUP ---

# with st.sidebar:
#     st.header("Login")
#     username = st.text_input("Nickname", value="Guest")
#     # Using a fixed room name for simplicity, or let users type
#     room_name = st.text_input("Room Name", value="party")

# if not room_name:
#     st.stop()

# st.title(f"🎵 SyncRoom: {room_name}")

# col1, col2 = st.columns([2, 1])

# # --- 4. MAIN THREAD (Video Player) ---
# # This part handles the video. It only reloads when the song changes.
# room_data = manager.get_room(room_name)
# current = room_data['current_video']

# with col1:
#     if current:
#         # Calculate how many seconds have passed since the song started on the server
#         elapsed = int(time.time() - current['start_time'])
        
#         # Guard against negative time (if clocks are slightly off)
#         if elapsed < 0: elapsed = 0
        
#         st.info(f"▶ Now Playing: {current['title']}")
        
#         # Autoplay=1 is crucial here. 
#         # mute=0 might be blocked by browsers, but we try.
#         video_html = f"""
#         <iframe width="100%" height="450" 
#             src="https://www.youtube.com/embed/{current['id']}?start={elapsed}&autoplay=1&controls=1" 
#             frameborder="0" allow="autoplay; encrypted-media" allowfullscreen>
#         </iframe>
#         """
#         st.components.v1.html(video_html, height=460)
        
#         if st.button("⏭ Skip Song"):
#             manager.skip(room_name)
#             st.rerun()
#     else:
#         st.container(height=450, border=True).write("Waiting for music...")
        
#     new_url = st.text_input("Paste YouTube URL")
#     if st.button("Add to Queue"):
#         if manager.add_video(room_name, new_url):
#             st.success("Added! syncing...")
#             time.sleep(0.5) # Give the server a moment to update
#             st.rerun()
#         else:
#             st.error("Invalid Link")

# # --- 5. BACKGROUND SYNC (Chat & Updates) ---
# # This runs every 2 seconds to check if the other user changed the song.

# @st.fragment(run_every=2)
# def live_updates_fragment():
#     # A. SYNC CHECK
#     # We fetch the latest server state
#     server_current = manager.get_room(room_name)['current_video']
    
#     # We compare it to what is currently on the screen (captured from main thread)
#     server_id = server_current['id'] if server_current else None
#     display_id = current['id'] if current else None
    
#     # If they don't match, someone changed the song! Force a reload.
#     if server_id != display_id:
#         st.rerun()

#     # B. CHAT & QUEUE TABS
#     tab_chat, tab_queue = st.tabs(["💬 Chat", "📜 Queue"])
    
#     with tab_chat:
#         # Chat Input
#         # We use a static key. Note: Streamlit resets input on interaction in fragments,
#         # so this is basic. For full chat apps, we'd use session state, but this works for basic syncing.
#         new_msg = st.chat_input("Say something...")
#         if new_msg:
#             manager.add_msg(room_name, username, new_msg)
        
#         # Show Messages
#         with st.container(height=400):
#             for user, msg in manager.get_room(room_name)['chat']:
#                 st.markdown(f"<div class='chat-msg'><b>{user}:</b> {msg}</div>", unsafe_allow_html=True)

#     with tab_queue:
#         q = manager.get_room(room_name)['queue']
#         if q:
#             for idx, v in enumerate(q):
#                 st.write(f"{idx+1}. {v['title']}")
#         else:
#             st.write("Queue is empty.")

# # CALL THE FRAGMENT
# with col2:
#     live_updates_fragment()