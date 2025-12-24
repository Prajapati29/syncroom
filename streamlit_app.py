import streamlit as st
import time
import re
import requests
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURATION ---
st.set_page_config(
    page_title="SyncRoom (Streamlit)", 
    page_icon="🎵", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Force dark theme style
st.markdown("""
<style>
    /* Hide the "Manage app" button and other Streamlit branding */
    [data-testid="stSidebarNav"] { display: none; }
    .stDeployButton { display: none; }
    
    /* Main app styling */
    .stApp { 
        background-color: #0e1117; 
        color: white; 
    }
    
    /* Button styling */
    .stButton>button { 
        width: 100%; 
        border-radius: 5px; 
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white; 
        border: none;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    
    .stButton>button:hover { 
        transform: translateY(-2px);
        box-shadow: 0 7px 14px rgba(50, 50, 93, 0.1), 0 3px 6px rgba(0, 0, 0, 0.08);
    }
    
    /* Container styling */
    .css-1r6slb0 { 
        background-color: #262730; 
        border-radius: 10px;
        padding: 15px;
    }
    
    /* Chat message styling */
    .chat-message { 
        padding: 10px; 
        border-radius: 10px; 
        margin: 5px 0; 
        animation: fadeIn 0.5s ease-in;
    }
    
    .user-message { 
        background-color: #262730; 
        border-left: 4px solid #667eea;
    }
    
    .system-message { 
        background-color: rgba(26, 95, 180, 0.2); 
        font-style: italic;
        border-left: 4px solid #1a5fb4;
    }
    
    .video-card { 
        padding: 10px; 
        border-radius: 8px; 
        background-color: rgba(30, 30, 30, 0.7); 
        margin: 5px 0; 
        transition: all 0.3s ease;
    }
    
    .video-card:hover {
        background-color: rgba(30, 30, 30, 0.9);
        transform: translateX(5px);
    }
    
    /* Custom animations */
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    /* Hide Streamlit's default hamburger menu */
    #MainMenu { visibility: hidden; }
    
    /* Improve input styling */
    .stTextInput>div>div>input {
        background-color: #262730;
        color: white;
        border: 1px solid #444;
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border-radius: 5px 5px 0 0;
        padding: 10px 16px;
    }
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
                'total_pause_duration': 0,
                'room_creator': None,
                'created_at': time.time()
            }
            self.users[room_name] = set()
            self.room_activity[room_name] = time.time()
        return self.rooms[room_name]
    
    def add_user(self, room_name, username):
        room = self.get_room(room_name)
        
        # Check if username is already in use in this room
        if username in self.users[room_name]:
            # Add a number to make it unique
            counter = 1
            while f"{username}_{counter}" in self.users[room_name]:
                counter += 1
            username = f"{username}_{counter}"
        
        self.users[room_name].add(username)
        self.add_msg(room_name, "System", f"🎉 {username} joined the room")
        
        # Set room creator if it's the first user
        if room['room_creator'] is None:
            room['room_creator'] = username
            
        return True, username
    
    def remove_user(self, room_name, username):
        if room_name in self.users and username in self.users[room_name]:
            self.users[room_name].remove(username)
            self.add_msg(room_name, "System", f"👋 {username} left the room")
            
            # If room is empty, mark for cleanup
            if len(self.users[room_name]) == 0:
                self.room_activity[room_name] = time.time() - 7000  # Mark as inactive
    
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
            self.add_msg(room_name, "System", f"🎵 {username} {message}: {video_info['title']}")
        
        return True, message
    
    def extract_video_id(self, url):
        """Extract YouTube video ID from various URL formats"""
        # Clean the URL
        url = url.strip()
        
        # Common patterns
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
        if re.match(r'^[\w-]{11}$', url):
            return url
        
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
                self.add_msg(room_name, "System", f"⏭️ {username} skipped to: {next_vid['title']}")
            return True
        else:
            room['current_video'] = None
            if username:
                self.add_msg(room_name, "System", f"⏹️ {username} stopped playback")
            return False
    
    def remove_from_queue(self, room_name, index, username=""):
        room = self.get_room(room_name)
        if 0 <= index < len(room['queue']):
            removed = room['queue'].pop(index)
            self.room_activity[room_name] = time.time()
            if username:
                self.add_msg(room_name, "System", f"🗑️ {username} removed: {removed['title']}")
            return True
        return False
    
    def move_in_queue(self, room_name, from_idx, to_idx, username=""):
        room = self.get_room(room_name)
        if 0 <= from_idx < len(room['queue']) and 0 <= to_idx < len(room['queue']):
            item = room['queue'].pop(from_idx)
            room['queue'].insert(to_idx, item)
            self.room_activity[room_name] = time.time()
            if username:
                self.add_msg(room_name, "System", f"↕️ {username} moved song in queue")
            return True
        return False
    
    def clear_queue(self, room_name, username=""):
        room = self.get_room(room_name)
        room['queue'].clear()
        self.room_activity[room_name] = time.time()
        if username:
            self.add_msg(room_name, "System", f"🧹 {username} cleared the queue")
    
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
                self.add_msg(room_name, "System", f"⏯️ {username} {action} the video")
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
        # Only return rooms with recent activity
        current_time = time.time()
        active_rooms = []
        for room_name, last_active in self.room_activity.items():
            if current_time - last_active < 7200:  # 2 hours
                active_rooms.append(room_name)
        return sorted(active_rooms)
    
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

# --- 3. INITIALIZE MANAGER ---
manager = RoomManager()

# --- 4. SIDEBAR: ROOM SELECTION & LOGIN ---
with st.sidebar:
    # Custom header with logo
    st.markdown("""
    <div style="text-align: center; padding: 20px 0;">
        <h1 style="color: #667eea; margin-bottom: 5px;">🎵 SyncRoom</h1>
        <p style="color: #888; font-size: 14px;">Watch YouTube together</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # Initialize session state for user
    if 'username' not in st.session_state:
        st.session_state.username = ""
    if 'current_room' not in st.session_state:
        st.session_state.current_room = ""
    if 'joined' not in st.session_state:
        st.session_state.joined = False
    
    # Room selection section
    st.subheader("🏠 Select Room")
    
    # Get active rooms
    all_rooms = manager.list_rooms()
    
    # Room options
    room_options = ["➕ Create New Room"] + all_rooms
    
    selected_room_option = st.selectbox(
        "Choose a room",
        options=room_options,
        index=0,
        label_visibility="collapsed"
    )
    
    # Handle room selection
    if selected_room_option == "➕ Create New Room":
        room_name = st.text_input("Room Name", placeholder="Enter new room name...", key="new_room_name")
        if st.button("🎉 Create & Join", type="primary", use_container_width=True):
            if room_name and room_name.strip():
                room_name = room_name.strip()
                # Check if room already exists
                if room_name in all_rooms:
                    st.error(f"Room '{room_name}' already exists!")
                else:
                    st.session_state.current_room = room_name
                    st.success(f"Room '{room_name}' created!")
                    st.rerun()
            else:
                st.error("Please enter a room name")
    else:
        room_name = selected_room_option
        st.session_state.current_room = room_name
        st.info(f"Selected: **{room_name}**")
    
    st.divider()
    
    # User login section
    st.subheader("👤 Your Profile")
    
    # If user is already joined in this room
    if st.session_state.joined and st.session_state.current_room == room_name:
        st.success(f"✅ Joined as: **{st.session_state.username}**")
        
        # Show leave button
        if st.button("🚪 Leave Room", use_container_width=True):
            manager.remove_user(room_name, st.session_state.username)
            st.session_state.joined = False
            st.session_state.username = ""
            st.success("Left the room")
            st.rerun()
    
    else:
        # Join form
        username = st.text_input("Your Nickname", placeholder="Enter your nickname...", key="login_username")
        
        if st.button("🎯 Join Room", type="primary", use_container_width=True):
            if username and username.strip():
                username = username.strip()
                success, actual_username = manager.add_user(room_name, username)
                if success:
                    st.session_state.username = actual_username
                    st.session_state.joined = True
                    st.session_state.current_room = room_name
                    st.success(f"Welcome, {actual_username}!")
                    st.rerun()
            else:
                st.error("Please enter a nickname")
    
    st.divider()
    
    # Room info section (only if joined)
    if st.session_state.joined and room_name in manager.users:
        st.subheader("📊 Room Stats")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("👥 Users", len(manager.users[room_name]))
        with col2:
            room_data = manager.get_room(room_name)
            st.metric("🎵 Queue", len(room_data['queue']))
        
        # Active users list
        with st.expander("See who's online"):
            for user in sorted(manager.users[room_name]):
                if user == st.session_state.username:
                    st.write(f"**👉 {user} (You)**")
                else:
                    st.write(f"• {user}")
        
        # Room creator info
        if room_data.get('room_creator'):
            created_time = datetime.fromtimestamp(room_data['created_at']).strftime("%H:%M")
            st.caption(f"Created by {room_data['room_creator']} at {created_time}")
    
    st.divider()
    
    # Quick help
    with st.expander("❓ How to use"):
        st.markdown("""
        1. **Select or create** a room
        2. **Enter your nickname** and join
        3. **Paste YouTube URLs** to add songs
        4. **Chat** with others in the room
        5. **Control playback** together
        
        ### Tips:
        • Everyone sees the same video
        • Videos stay in sync automatically
        • Use the queue to plan ahead
        • Chat updates in real-time
        """)

# --- 5. AUTO-REFRESH SETUP ---
# Clean up inactive rooms periodically
if 'last_cleanup' not in st.session_state or time.time() - st.session_state.last_cleanup > 300:  # Every 5 minutes
    cleaned = manager.cleanup_inactive_rooms()
    st.session_state.last_cleanup = time.time()

# Determine refresh interval based on activity
refresh_interval = 2000  # Default: 2 seconds

# Check if user has joined
if not st.session_state.joined:
    # Show welcome screen
    st.title("🎵 Welcome to SyncRoom")
    st.markdown("### Watch YouTube videos together in real-time")
    
    col_welcome1, col_welcome2, col_welcome3 = st.columns([1, 2, 1])
    with col_welcome2:
        st.image("https://cdn-icons-png.flaticon.com/512/1384/1384060.png", width=150)
        st.markdown("""
        <div style="text-align: center;">
            <h3>👈 Start by joining a room</h3>
            <p>Select a room from the sidebar or create a new one!</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Show available rooms
    all_rooms = manager.list_rooms()
    if all_rooms:
        st.divider()
        st.subheader("🌐 Active Rooms")
        cols = st.columns(3)
        for idx, room in enumerate(all_rooms[:6]):  # Show first 6 rooms
            with cols[idx % 3]:
                room_data = manager.get_room(room)
                users_count = len(manager.users.get(room, []))
                st.metric(f"#{room}", f"{users_count} user{'s' if users_count != 1 else ''}")
    
    st.stop()

# User is joined, continue with main app
username = st.session_state.username
room_name = st.session_state.current_room
room_data = manager.get_room(room_name)

# Adjust refresh rate
if room_data['current_video'] and not room_data['paused']:
    refresh_interval = 1000  # 1 second when playing
else:
    refresh_interval = 3000  # 3 seconds when idle

# Apply auto-refresh
count = st_autorefresh(interval=refresh_interval, key="autorefresh", limit=100000)

# --- 6. MAIN APP INTERFACE ---
# Header
st.markdown(f"""
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
    <div>
        <h1 style="margin: 0;">🎵 {room_name}</h1>
        <p style="margin: 0; color: #888; font-size: 14px;">
            👤 {username} • 👥 {len(manager.users.get(room_name, []))} online • ⚡ Auto-sync
        </p>
    </div>
    <div style="text-align: right;">
        <small>🔄 Refreshing every {refresh_interval//1000}s</small>
    </div>
</div>
""", unsafe_allow_html=True)

# Main columns
col1, col2 = st.columns([2, 1])

# --- LEFT COLUMN: VIDEO PLAYER ---
with col1:
    # Current video player
    current = room_data['current_video']
    
    if current:
        # Calculate sync time considering pauses
        if room_data['paused'] and room_data['pause_time']:
            current_pause_duration = time.time() - room_data['pause_time']
        else:
            current_pause_duration = 0
        
        total_pause = room_data.get('total_pause_duration', 0) + current_pause_duration
        elapsed = max(0, int(time.time() - current['start_time'] - total_pause))
        
        # Format elapsed time
        elapsed_str = f"{elapsed // 60}:{elapsed % 60:02d}"
        
        # Video player header
        player_header = st.container()
        with player_header:
            col_title, col_status, col_time = st.columns([3, 1, 1])
            with col_title:
                st.markdown(f"### 🎬 {current['title'][:50]}{'...' if len(current['title']) > 50 else ''}")
                if current.get('added_by'):
                    st.caption(f"Added by: {current['added_by']}")
            with col_status:
                status = "⏸️ Paused" if room_data['paused'] else "▶️ Playing"
                st.markdown(f"**{status}**")
            with col_time:
                st.markdown(f"**⏱️ {elapsed_str}**")
        
        # Video player embed
        video_url = f"https://www.youtube.com/embed/{current['id']}?start={elapsed}&controls=1&modestbranding=1&rel=0"
        st.components.v1.html(f"""
        <div style="border-radius: 10px; overflow: hidden; margin: 10px 0; box-shadow: 0 10px 30px rgba(0,0,0,0.3);">
            <iframe width="100%" height="450" 
                src="{video_url}" 
                frameborder="0" 
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                allowfullscreen
                style="display: block;">
            </iframe>
        </div>
        """, height=470)
        
        # Playback controls
        st.markdown("### 🎛️ Controls")
        control_cols = st.columns(4)
        with control_cols[0]:
            if st.button("⏭️ Skip", use_container_width=True, help="Skip to next song"):
                manager.skip(room_name, username)
                st.rerun()
        with control_cols[1]:
            pause_text = "▶️ Resume" if room_data['paused'] else "⏸️ Pause"
            if st.button(pause_text, use_container_width=True, help="Pause/Resume playback"):
                manager.toggle_pause(room_name, username)
                st.rerun()
        with control_cols[2]:
            if st.button("🔄 Refresh", use_container_width=True, help="Refresh player"):
                st.rerun()
        with control_cols[3]:
            if st.button("🗑️ Clear", use_container_width=True, help="Stop playback and clear current"):
                if room_data['current_video']:
                    room_data['current_video'] = None
                    st.rerun()
        
    else:
        # No video playing
        st.markdown("### 🎵 No video playing")
        st.markdown("""
        <div style="
            height: 450px; 
            display: flex; 
            flex-direction: column; 
            justify-content: center; 
            align-items: center; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 10px;
            margin: 10px 0;
            color: white;
            text-align: center;
            padding: 20px;
        ">
            <h1 style="font-size: 48px; margin: 0;">🎬</h1>
            <h3>Add a song to start the party!</h3>
            <p>Paste a YouTube URL below to begin</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Add Song Section
    st.divider()
    st.markdown("### ➕ Add Music")
    
    add_tab1, add_tab2 = st.tabs(["🔗 Paste URL", "🔍 Quick Add"])
    
    with add_tab1:
        url_input = st.text_input(
            "YouTube URL or Video ID",
            placeholder="https://www.youtube.com/watch?v=... or just paste the ID",
            key="add_url_input"
        )
        
        col_add1, col_add2 = st.columns([3, 1])
        with col_add1:
            add_mode = st.radio("Add to:", ["Queue", "Play Now"], horizontal=True)
        with col_add2:
            if st.button("🎵 Add", use_container_width=True, type="primary"):
                if url_input:
                    success, message = manager.add_video(room_name, url_input, username)
                    if success:
                        # If "Play Now" is selected and there's a current video, skip to this one
                        if add_mode == "Play Now" and room_data['current_video']:
                            # Add to queue first, then skip
                            manager.skip(room_name, username)
                        st.success(message)
                        time.sleep(0.3)
                        st.rerun()
                    else:
                        st.error(message)
                else:
                    st.warning("Please enter a URL")
    
    with add_tab2:
        st.info("💡 Quick YouTube links")
        col_q1, col_q2, col_q3 = st.columns(3)
        
        # Popular music examples
        quick_links = {
            "Lo-fi Radio": "https://www.youtube.com/watch?v=jfKfPfyJRdk",
            "Jazz Vibes": "https://www.youtube.com/watch?v=WqMvI2qrX_c",
            "Synthwave": "https://www.youtube.com/watch?v=4xDzrJKXOOY"
        }
        
        with col_q1:
            if st.button("🎧 Lo-fi", use_container_width=True):
                manager.add_video(room_name, quick_links["Lo-fi Radio"], username)
                st.rerun()
        with col_q2:
            if st.button("🎷 Jazz", use_container_width=True):
                manager.add_video(room_name, quick_links["Jazz Vibes"], username)
                st.rerun()
        with col_q3:
            if st.button("🌃 Synthwave", use_container_width=True):
                manager.add_video(room_name, quick_links["Synthwave"], username)
                st.rerun()

# --- RIGHT COLUMN: CHAT & QUEUE ---
with col2:
    tab1, tab2 = st.tabs(["💬 Live Chat", "📜 Song Queue"])
    
    with tab1:
        # Chat messages
        chat_container = st.container(height=350)
        
        with chat_container:
            for msg in room_data['chat'][-25:]:  # Show last 25 messages
                if msg['user'] == "System":
                    st.markdown(f"""
                    <div class='system-message chat-message'>
                        <small>[{msg['time']}]</small><br>
                        {msg['text']}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # Highlight current user's messages
                    if msg['user'] == username:
                        st.markdown(f"""
                        <div class='user-message chat-message' style='border-left-color: #00ff88;'>
                            <strong>👉 {msg['user']}</strong> <small>[{msg['time']}]</small><br>
                            {msg['text']}
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div class='user-message chat-message'>
                            <strong>{msg['user']}</strong> <small>[{msg['time']}]</small><br>
                            {msg['text']}
                        </div>
                        """, unsafe_allow_html=True)
        
        # Chat input
        st.divider()
        chat_input_cols = st.columns([4, 1])
        with chat_input_cols[0]:
            chat_msg = st.text_input("Type a message...", key="chat_msg", label_visibility="collapsed")
        with chat_input_cols[1]:
            if st.button("Send", use_container_width=True):
                if chat_msg.strip():
                    manager.add_msg(room_name, username, chat_msg.strip())
                    st.rerun()
    
    with tab2:
        # Queue display
        queue_container = st.container(height=350)
        
        with queue_container:
            if room_data['queue']:
                st.markdown(f"### 📋 Queue ({len(room_data['queue'])} songs)")
                
                for i, song in enumerate(room_data['queue']):
                    with st.container():
                        col_s1, col_s2, col_s3 = st.columns([6, 1, 1])
                        with col_s1:
                            st.markdown(f"**{i+1}.** {song['title'][:40]}{'...' if len(song['title']) > 40 else ''}")
                            if song.get('added_by'):
                                st.caption(f"by {song['added_by']}")
                        with col_s2:
                            if st.button("↑", key=f"up_{i}", help="Move up"):
                                if i > 0:
                                    manager.move_in_queue(room_name, i, i-1, username)
                                    st.rerun()
                        with col_s3:
                            if st.button("🗑", key=f"del_{i}", help="Remove"):
                                manager.remove_from_queue(room_name, i, username)
                                st.rerun()
                        
                        st.divider()
                
                # Queue management buttons
                st.markdown("### 🛠️ Queue Tools")
                col_qm1, col_qm2 = st.columns(2)
                with col_qm1:
                    if st.button("Clear All", use_container_width=True):
                        if st.checkbox("Are you sure? This cannot be undone!"):
                            manager.clear_queue(room_name, username)
                            st.rerun()
                with col_qm2:
                    if st.button("Skip All", use_container_width=True, disabled=True):
                        st.info("Coming soon!")
            
            else:
                st.markdown("""
                <div style="
                    height: 300px; 
                    display: flex; 
                    flex-direction: column; 
                    justify-content: center; 
                    align-items: center; 
                    text-align: center;
                    color: #888;
                ">
                    <h1 style="font-size: 64px; margin: 0;">🎵</h1>
                    <h3>Queue is empty</h3>
                    <p>Add some songs to get started!</p>
                </div>
                """, unsafe_allow_html=True)

# --- FOOTER ---
st.divider()
footer_cols = st.columns(3)
with footer_cols[0]:
    st.caption(f"Room: **{room_name}**")
with footer_cols[1]:
    st.caption(f"User: **{username}**")
with footer_cols[2]:
    st.caption("SyncRoom v2.0 • Made with Streamlit")

# Add some debug info in expander (hidden by default)
with st.expander("🔧 Debug Info"):
    if st.checkbox("Show room data"):
        st.json(room_data)
    
    if st.checkbox("Show all rooms"):
        st.write("Active rooms:", manager.list_rooms())
        for room in manager.list_rooms():
            st.write(f"- {room}: {len(manager.users.get(room, []))} users")
    
    if st.button("Force cleanup"):
        cleaned = manager.cleanup_inactive_rooms(60)  # Clean rooms inactive for 1 minute
        st.write(f"Cleaned {cleaned} rooms")
        st.rerun()