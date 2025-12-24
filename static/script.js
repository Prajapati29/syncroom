const socket = io();
let player;
let roomID = "";
let username = "";
let isApiReady = false;

// 1. YouTube IFrame API Setup
var tag = document.createElement('script');
tag.src = "https://www.youtube.com/iframe_api";
var firstScriptTag = document.getElementsByTagName('script')[0];
firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);

function onYouTubeIframeAPIReady() {
    player = new YT.Player('player', {
        height: '100%',
        width: '100%',
        playerVars: { 'playsinline': 1, 'controls': 1, 'disablekb': 1 },
        events: {
            'onReady': onPlayerReady,
            'onStateChange': onPlayerStateChange
        }
    });
}

function onPlayerReady(event) {
    isApiReady = true;
}

function onPlayerStateChange(event) {
    // If video ends (state=0), tell server
    if (event.data === YT.PlayerState.ENDED) {
        socket.emit('video_ended', { room: roomID });
    }
}

// 2. Room & UI Logic
function joinRoom() {
    username = document.getElementById('username').value || 'Guest';
    // Check URL params first, then input
    const urlParams = new URLSearchParams(window.location.search);
    roomID = urlParams.get('room') || document.getElementById('room-input').value;
    
    if (!roomID) { alert("Please enter a room name"); return; }

    document.getElementById('login-screen').classList.add('hidden');
    document.getElementById('app-screen').classList.remove('hidden');
    document.getElementById('room-display').innerText = `Room: ${roomID}`;

    socket.emit('join', { username: username, room: roomID });
}

// Auto-join if URL has ?room=XYZ
window.onload = () => {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('room')) {
        document.getElementById('room-input').value = urlParams.get('room');
    }
};

function copyLink() {
    const url = `${window.location.origin}/?room=${roomID}`;
    navigator.clipboard.writeText(url);
    alert("Link copied: " + url);
}

function leaveRoom() {
    window.location.href = "/";
}

// 3. Playback Logic
function addSong() {
    const url = document.getElementById('youtube-url').value;
    
    // Improved logic to extract ID from standard URLs (v=) AND short URLs (youtu.be)
    // It also ignores extra parameters like ?si= or &t=
    let vidId = "";
    
    try {
        if (url.includes("v=")) {
            vidId = url.split('v=')[1].split('&')[0].split('?')[0];
        } else if (url.includes("youtu.be/")) {
            vidId = url.split('youtu.be/')[1].split('?')[0];
        }
    } catch (e) {
        console.error("Error parsing URL", e);
    }

    if (vidId && vidId.length === 11) {
        socket.emit('add_to_queue', { room: roomID, video_id: vidId, title: "Video " + vidId });
        document.getElementById('youtube-url').value = "";
    } else {
        alert("Invalid YouTube Link. Please use a standard link.");
    }
}

// 4. Socket Listeners

socket.on('message', (data) => {
    const box = document.getElementById('chat-box');
    const msg = document.createElement('div');
    msg.className = 'chat-msg';
    msg.innerHTML = `<b>${data.user}:</b> ${data.text}`;
    box.appendChild(msg);
    box.scrollTop = box.scrollHeight;
});

socket.on('play_video', (data) => {
    if(!isApiReady) return;
    
    document.getElementById('current-song').innerText = `Playing: ${data.title}`;
    player.loadVideoById(data.id);
    
    // Calculate sync time
    // Server time vs local time diff is handled roughly here.
    // For precision, we use the server's elapsed calculation.
    socket.emit('request_sync', { room: roomID });
});

socket.on('sync_time', (data) => {
    if(player && player.seekTo) {
        player.seekTo(data.elapsed, true);
        player.playVideo();
    }
});

socket.on('stop_video', () => {
    if(player) player.stopVideo();
    document.getElementById('current-song').innerText = "Nothing Playing";
});

socket.on('update_queue', (queue) => {
    const list = document.getElementById('queue-list');
    list.innerHTML = "";
    queue.forEach(vid => {
        const li = document.createElement('li');
        li.innerText = vid.title;
        list.appendChild(li);
    });
});

socket.on('sync_state', (state) => {
    if (state.current_video) {
        document.getElementById('current-song').innerText = `Playing: ${state.current_video.title}`;
        player.loadVideoById(state.current_video.id);
        
        // Handle immediate sync
        // Calculate elapsed time on client side relative to server start
        // Note: Ideally request_sync is better to account for clock skew
        document.getElementById('overlay').style.display = 'flex'; // Ask user to click to sync
    }
    // Update queue
    if (state.queue) {
        const list = document.getElementById('queue-list');
        list.innerHTML = "";
        state.queue.forEach(vid => {
            const li = document.createElement('li');
            li.innerText = vid.title;
            list.appendChild(li);
        });
    }
});

// Chat
function handleChat(e) {
    if (e.key === 'Enter') {
        const input = document.getElementById('msg-input');
        socket.emit('send_message', { room: roomID, user: username, text: input.value });
        input.value = "";
    }
}