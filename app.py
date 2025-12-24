import time
from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import secrets

app = Flask(__name__, static_url_path='')
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# --- IN-MEMORY DATA STORE ---
# Structure:
# rooms = {
#     'room_id': {
#         'current_video': {'id': 'videoId', 'title': 'Title', 'start_time': 123456789},
#         'queue': [{'id': 'vid', 'title': 'Title'}],
#         'users': ['User1', 'User2']
#     }
# }
rooms = {}

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

# --- SOCKET EVENTS ---

@socketio.on('join')
def on_join(data):
    username = data['username']
    room = data['room']
    
    join_room(room)
    
    if room not in rooms:
        rooms[room] = {
            'current_video': None,
            'queue': [],
            'users': []
        }
    
    if username not in rooms[room]['users']:
        rooms[room]['users'].append(username)
    
    # Notify room
    emit('message', {'user': 'System', 'text': f'{username} has joined the room.'}, room=room)
    
    # Send current state to ONLY the new user
    emit('sync_state', rooms[room], room=request.sid)

@socketio.on('add_to_queue')
def on_add_queue(data):
    room = data['room']
    video_id = data['video_id']
    title = data['title']
    
    if room in rooms:
        video_data = {'id': video_id, 'title': title}
        
        # If nothing playing, play immediately
        if rooms[room]['current_video'] is None:
            rooms[room]['current_video'] = video_data
            rooms[room]['current_video']['start_time'] = time.time()
            emit('play_video', rooms[room]['current_video'], room=room)
        else:
            rooms[room]['queue'].append(video_data)
            emit('update_queue', rooms[room]['queue'], room=room)

@socketio.on('video_ended')
def on_video_ended(data):
    # Logic: When a client reports video end, server decides next move.
    # To prevent double-skipping if multiple clients report end, we check timestamps or lock.
    # Simple approach: Trust the first reporter, but verify queue.
    room = data['room']
    if room in rooms:
        play_next(room)

@socketio.on('skip')
def on_skip(data):
    room = data['room']
    if room in rooms:
        play_next(room)

@socketio.on('send_message')
def on_send_message(data):
    room = data['room']
    emit('message', data, room=room)

@socketio.on('request_sync')
def on_request_sync(data):
    # Client asks "Where should I be?"
    room = data['room']
    if room in rooms and rooms[room]['current_video']:
        video = rooms[room]['current_video']
        elapsed = time.time() - video['start_time']
        emit('sync_time', {'elapsed': elapsed}, room=request.sid)

def play_next(room):
    if rooms[room]['queue']:
        next_video = rooms[room]['queue'].pop(0)
        next_video['start_time'] = time.time()
        rooms[room]['current_video'] = next_video
        emit('play_video', next_video, room=room)
        emit('update_queue', rooms[room]['queue'], room=room)
    else:
        rooms[room]['current_video'] = None
        emit('stop_video', {}, room=room)

if __name__ == '__main__':
    socketio.run(app)