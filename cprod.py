from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit
import eventlet
from datetime import datetime

# Standard eventlet patch for stability
eventlet.monkey_patch()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secure_chat_key'

# Max buffer size set to 10MB to allow large GIFs
socketio = SocketIO(app, 
                    cors_allowed_origins="*", 
                    async_mode='eventlet', 
                    ping_timeout=60, 
                    max_http_buffer_size=10 * 1024 * 1024)

# Global dictionary to track connected users: {session_id: username}
CONNECTED_USERS = {}

@app.route('/')
def index():
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <title>LAN Chat</title>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    
    <style>
        /* --- THEME VARIABLES --- */
        :root {
            /* Default: Blue */
            --primary: #2563eb; 
            --primary-light: #3b82f6;
            
            /* Light Mode Defaults */
            --bg-color: #f3f4f6;
            --chat-bg: #ffffff;
            --text-main: #1f2937;
            --text-secondary: #6b7280;
            --bubble-other-bg: #ffffff;
            --bubble-other-text: #1f2937;
            --input-bg: #ffffff;
            --input-border: rgba(0,0,0,0.05);
            --header-bg: rgba(255, 255, 255, 0.85);
            --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
            --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }

        /* Dark Mode Overrides */
        [data-theme="dark"] {
            --bg-color: #111827;
            --chat-bg: #1f2937;
            --text-main: #f9fafb;
            --text-secondary: #9ca3af;
            --bubble-other-bg: #374151;
            --bubble-other-text: #f3f4f6;
            --input-bg: #1f2937;
            --input-border: rgba(255,255,255,0.1);
            --header-bg: rgba(17, 24, 39, 0.85);
            --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.3);
            --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
        }

        * { box-sizing: border-box; outline: none; }

        body { 
            font-family: 'Inter', -apple-system, sans-serif; 
            margin: 0; 
            background-color: var(--bg-color); 
            display: flex; 
            flex-direction: column; 
            height: 100vh; 
            overflow: hidden;
            color: var(--text-main);
            transition: background-color 0.3s, color 0.3s;
        }

        /* --- Scrollbar --- */
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background-color: var(--text-secondary); opacity: 0.5; border-radius: 20px; }
        
        /* --- Header --- */
        .header { 
            background: var(--header-bg); 
            backdrop-filter: blur(12px);
            padding: 15px 25px; 
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--input-border);
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: var(--shadow-sm);
            transition: background 0.3s;
        }
        
        .logo-area { display: flex; align-items: center; gap: 10px; font-weight: 600; font-size: 1.1rem; }
        .logo-icon { font-size: 1.4rem; }

        .header-controls { display: flex; align-items: center; gap: 10px; }

        /* --- Online Status --- */
        .online-wrapper { position: relative; cursor: pointer; display: flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 20px; transition: background 0.2s; }
        .online-wrapper:hover { background: rgba(128,128,128,0.1); }
        .status-dot { width: 8px; height: 8px; background-color: #10b981; border-radius: 50%; box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2); }
        .online-count { font-size: 0.9rem; font-weight: 500; }

        .user-tooltip {
            display: none;
            position: absolute;
            right: 0;
            top: 120%;
            width: 200px;
            background: var(--input-bg);
            border-radius: 12px;
            padding: 8px 0;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
            border: 1px solid var(--input-border);
            animation: fadeIn 0.2s ease-out;
            z-index: 50;
            color: var(--text-main);
        }
        .online-wrapper:hover .user-tooltip { display: block; }
        .tooltip-header { padding: 8px 16px; font-size: 0.75rem; text-transform: uppercase; color: var(--text-secondary); font-weight: 600; border-bottom: 1px solid var(--input-border); }
        .user-item { padding: 8px 16px; font-size: 0.9rem; display: flex; align-items: center; gap: 8px; }
        .user-item::before { content: ''; display: block; width: 6px; height: 6px; background: #10b981; border-radius: 50%; }

        /* --- Chat Area --- */
        #messages { 
            flex: 1; 
            overflow-y: auto; 
            padding: 20px 5%; 
            display: flex; 
            flex-direction: column; 
            gap: 16px; 
            scroll-behavior: smooth;
        }

        .message-row { display: flex; flex-direction: column; max-width: 65%; width: fit-content; animation: slideUp 0.3s ease-out; }
        .message-row.self { align-self: flex-end; align-items: flex-end; }
        
        .message-bubble { 
            padding: 12px 18px; 
            border-radius: 18px; 
            font-size: 0.95rem; 
            line-height: 1.5; 
            position: relative;
            box-shadow: var(--shadow-sm);
            word-wrap: break-word;
        }

        .message-row.other .message-bubble { 
            background: var(--bubble-other-bg); 
            color: var(--bubble-other-text); 
            border-bottom-left-radius: 4px;
        }

        .message-row.self .message-bubble { 
            background: var(--primary); 
            color: white; 
            border-bottom-right-radius: 4px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0, 0.2);
        }

        .message-meta { 
            font-size: 0.75rem; 
            color: var(--text-secondary); 
            margin-top: 4px; 
            display: flex; 
            gap: 8px; 
            padding: 0 4px;
        }

        .system-message { 
            align-self: center; 
            background: rgba(128,128,128,0.1); 
            padding: 6px 16px; 
            border-radius: 20px; 
            font-size: 0.8rem; 
            color: var(--text-secondary); 
            margin: 10px 0;
            max-width: 90%;
            text-align: center;
        }

        .chat-image { 
            max-width: 100%; 
            border-radius: 12px; 
            display: block; 
            margin-bottom: 5px;
            cursor: pointer;
            transition: transform 0.2s;
        }
        .chat-image:hover { transform: scale(1.02); }

        /* --- Input Area --- */
        .input-wrapper { 
            padding: 20px; 
            background: transparent;
            display: flex;
            justify-content: center;
        }

        .input-dock {
            background: var(--input-bg);
            width: 100%;
            max-width: 900px;
            border-radius: 24px;
            padding: 10px;
            display: flex;
            align-items: center;
            gap: 10px;
            box-shadow: var(--shadow-md);
            border: 1px solid var(--input-border);
            transition: transform 0.2s, background 0.3s;
        }
        .input-dock:focus-within { transform: translateY(-2px); }

        .icon-btn {
            background: rgba(128,128,128,0.1);
            border: none;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2rem;
            color: var(--text-secondary);
            transition: all 0.2s;
        }
        .icon-btn:hover { background: rgba(128,128,128,0.2); color: var(--text-main); }
        .icon-btn:active { transform: scale(0.95); }

        #username {
            border: none;
            background: rgba(128,128,128,0.05);
            padding: 8px 12px;
            border-radius: 12px;
            font-weight: 600;
            color: var(--text-main);
            width: 80px;
            text-align: center;
            font-size: 0.9rem;
        }
        #username:focus { background: rgba(128,128,128,0.1); color: var(--primary); }

        #input {
            flex: 1;
            border: none;
            padding: 10px;
            font-size: 1rem;
            font-family: inherit;
            background: transparent;
            color: var(--text-main);
        }
        #input::placeholder { color: var(--text-secondary); }

        #send {
            background: var(--primary);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 20px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        #send:hover { opacity: 0.9; transform: translateY(-1px); }

        /* --- Settings Modal --- */
        .modal-overlay {
            display: none;
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.5);
            backdrop-filter: blur(4px);
            z-index: 200;
            justify-content: center;
            align-items: center;
        }
        .modal {
            background: var(--input-bg);
            color: var(--text-main);
            padding: 25px;
            border-radius: 20px;
            width: 90%;
            max-width: 400px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
            animation: fadeIn 0.2s;
        }
        .modal h2 { margin-top: 0; font-size: 1.2rem; }
        .setting-row { margin-bottom: 20px; }
        .setting-label { display: block; margin-bottom: 8px; font-weight: 500; font-size: 0.9rem; color: var(--text-secondary); }
        
        /* Color Picker Grid */
        .color-grid { display: flex; gap: 10px; flex-wrap: wrap; }
        .color-option { width: 32px; height: 32px; border-radius: 50%; cursor: pointer; border: 2px solid transparent; transition: transform 0.2s; }
        .color-option:hover { transform: scale(1.1); }
        .color-option.selected { border-color: var(--text-main); }

        /* Switch Toggle */
        .switch { position: relative; display: inline-block; width: 50px; height: 26px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #ccc; border-radius: 34px; transition: .4s; }
        .slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 4px; bottom: 4px; background-color: white; border-radius: 50%; transition: .4s; }
        input:checked + .slider { background-color: var(--primary); }
        input:checked + .slider:before { transform: translateX(24px); }

        .modal-close {
            margin-top: 10px;
            width: 100%;
            padding: 10px;
            border: none;
            background: rgba(128,128,128,0.1);
            color: var(--text-main);
            border-radius: 10px;
            cursor: pointer;
            font-weight: 600;
        }
        .modal-close:hover { background: rgba(128,128,128,0.2); }

        #imageUrl, #imageFile { display: none; }
        @keyframes slideUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

    </style>
</head>
<body>
    <div class="header">
        <div class="logo-area">
            <span class="logo-icon">☣️</span>
            <span>LAN Chat</span>
        </div>

        <div class="header-controls">
            <div class="online-wrapper">
                <div class="status-dot"></div>
                <div class="online-count" id="onlineStatus">Loading...</div>
                <div class="user-tooltip" id="userListDisplay"></div>
            </div>

            <button class="icon-btn" id="settings-btn" title="Settings" style="background: transparent;">🎨</button>
        </div>
    </div>
    
    <div id="messages"></div>
    
    <div class="input-wrapper">
        <div class="input-dock">
            <input id="username" title="Your Name" value="User">
            <button class="icon-btn" id="uploadBtn" title="Upload Image/GIF">📁</button>
            <input type="file" id="imageFile" accept="image/*">
            <input id="imageUrl"> 
            <input id="input" placeholder="Type a message..." autocomplete="off">
            <button id="send">Send</button>
        </div>
    </div>

    <div class="modal-overlay" id="settingsModal">
        <div class="modal">
            <h2>Appearance Settings</h2>
            
            <div class="setting-row">
                <span class="setting-label">Accent Color</span>
                <div class="color-grid" id="colorGrid">
                    </div>
            </div>

            <div class="setting-row" style="display: flex; justify-content: space-between; align-items: center;">
                <span class="setting-label" style="margin: 0;">Dark Mode</span>
                <label class="switch">
                    <input type="checkbox" id="darkModeToggle">
                    <span class="slider"></span>
                </label>
            </div>
            
            <div class="setting-row" style="display: flex; justify-content: space-between; align-items: center;">
                 <span class="setting-label" style="margin: 0;">Sound Effects</span>
                 <label class="switch">
                    <input type="checkbox" id="soundToggle" checked>
                    <span class="slider"></span>
                </label>
            </div>

            <button class="modal-close" id="closeSettings">Done</button>
        </div>
    </div>

    <script>
        const socket = io({ reconnection: true });
        
        // --- THEME LOGIC ---
        const colors = [
            '#2563eb', // Blue
            '#9333ea', // Purple
            '#16a34a', // Green
            '#ea580c', // Orange
            '#db2777', // Pink
            '#0d9488'  // Teal
        ];

        const root = document.documentElement;
        const colorGrid = document.getElementById('colorGrid');
        const darkModeToggle = document.getElementById('darkModeToggle');
        
        // Load Saved Settings
        const savedColor = localStorage.getItem('theme_color') || '#2563eb';
        const savedTheme = localStorage.getItem('theme_mode') || 'light';
        const savedSound = localStorage.getItem('sound_enabled');

        // Apply Initial State
        root.style.setProperty('--primary', savedColor);
        if (savedTheme === 'dark') {
            root.setAttribute('data-theme', 'dark');
            darkModeToggle.checked = true;
        }

        // Render Color Grid
        colors.forEach(color => {
            const div = document.createElement('div');
            div.className = 'color-option';
            div.style.backgroundColor = color;
            if (color === savedColor) div.classList.add('selected');
            
            div.onclick = () => {
                document.querySelectorAll('.color-option').forEach(el => el.classList.remove('selected'));
                div.classList.add('selected');
                root.style.setProperty('--primary', color);
                localStorage.setItem('theme_color', color);
            };
            colorGrid.appendChild(div);
        });

        // Toggle Dark Mode
        darkModeToggle.addEventListener('change', (e) => {
            if (e.target.checked) {
                root.setAttribute('data-theme', 'dark');
                localStorage.setItem('theme_mode', 'dark');
            } else {
                root.removeAttribute('data-theme');
                localStorage.setItem('theme_mode', 'light');
            }
        });

        // --- ELEMENTS ---
        const messages = document.getElementById("messages");
        const input = document.getElementById("input");
        const usernameInput = document.getElementById("username");
        const imageFileInput = document.getElementById("imageFile");
        const uploadBtn = document.getElementById("uploadBtn");
        const settingsBtn = document.getElementById("settings-btn");
        const settingsModal = document.getElementById("settingsModal");
        const closeSettings = document.getElementById("closeSettings");
        const soundToggle = document.getElementById("soundToggle");
        
        let soundEnabled = savedSound !== 'false'; // Default to true
        soundToggle.checked = soundEnabled;

        soundToggle.addEventListener('change', (e) => {
            soundEnabled = e.target.checked;
            localStorage.setItem('sound_enabled', soundEnabled);
        });

        // Modal Logic
        settingsBtn.onclick = () => settingsModal.style.display = 'flex';
        closeSettings.onclick = () => settingsModal.style.display = 'none';
        settingsModal.onclick = (e) => {
            if (e.target === settingsModal) settingsModal.style.display = 'none';
        };

        // --- CHAT LOGIC ---
        let unreadCount = 0;
        const originalTitle = document.title;
        const beepUrl = "https://www.myinstants.com/media/sounds/discord-notification.mp3"; 
        const audio = new Audio(beepUrl);

        if(localStorage.getItem('chat_username')) {
            usernameInput.value = localStorage.getItem('chat_username');
        }

        window.addEventListener('focus', () => {
            unreadCount = 0;
            document.title = originalTitle;
        });

        function notifyUser(sender, msg) {
            if (document.hidden || sender !== usernameInput.value) {
                if (soundEnabled) {
                    audio.currentTime = 0;
                    audio.play().catch(e => console.log("Audio blocked"));
                }
                if (document.hidden) {
                    unreadCount++;
                    document.title = `(${unreadCount}) New Message!`;
                }
                if (document.hidden && Notification.permission === "granted") {
                    new Notification(`New message from ${sender}`, {
                        body: msg,
                        icon: 'https://cdn-icons-png.flaticon.com/512/134/134914.png'
                    });
                }
            }
        }

        function scrollToBottom() {
            messages.scrollTop = messages.scrollHeight;
        }

        function addMessage(data) {
            const isMe = data.username === usernameInput.value;
            
            if (data.type === 'system') {
                const sysDiv = document.createElement("div");
                sysDiv.className = "system-message";
                sysDiv.innerText = data.msg;
                messages.appendChild(sysDiv);
                scrollToBottom();
                return;
            }

            const notifyText = data.type === 'image' ? (data.msg || 'sent an image') : data.msg;
            notifyUser(data.username, notifyText);

            const row = document.createElement("div");
            row.className = `message-row ${isMe ? 'self' : 'other'}`;

            const bubble = document.createElement("div");
            bubble.className = "message-bubble";

            if (data.type === 'image') {
                const img = document.createElement("img");
                img.src = data.url;
                img.className = "chat-image";
                img.onclick = () => window.open(data.url, '_blank');
                bubble.appendChild(img);
                if (data.msg) {
                    const caption = document.createElement("div");
                    caption.innerText = data.msg;
                    caption.style.marginTop = "8px";
                    bubble.appendChild(caption);
                }
            } else {
                bubble.innerText = data.msg;
            }

            const meta = document.createElement("div");
            meta.className = "message-meta";
            
            const nameSpan = document.createElement("span");
            nameSpan.innerText = isMe ? "You" : data.username;
            nameSpan.style.fontWeight = "600";
            
            const timeSpan = document.createElement("span");
            timeSpan.innerText = data.timestamp || "";
            
            if (isMe) {
                meta.appendChild(timeSpan);
                meta.appendChild(nameSpan);
            } else {
                meta.appendChild(nameSpan);
                meta.appendChild(timeSpan);
            }

            row.appendChild(bubble);
            row.appendChild(meta);
            messages.appendChild(row);
            scrollToBottom();
        }

        function sendMessage() {
            const msg = input.value.trim();
            const user = usernameInput.value.trim() || "Anon";
            const imageUrl = document.getElementById('imageUrl').value.trim(); 
            
            if (msg || imageUrl) {
                localStorage.setItem('chat_username', user);
                const data = {username: user};
                if (imageUrl) {
                    data.type = 'image';
                    data.url = imageUrl;
                    data.msg = msg; 
                } else {
                    data.type = 'text';
                    data.msg = msg;
                }
                socket.emit("message", data);
                input.value = "";
                document.getElementById('imageUrl').value = "";
                input.focus();
            }
        }

        input.addEventListener("keypress", (e) => { if(e.key === "Enter") sendMessage(); });
        document.getElementById("send").addEventListener("click", sendMessage);

        uploadBtn.addEventListener('click', () => imageFileInput.click());
        imageFileInput.addEventListener('change', () => {
            const file = imageFileInput.files[0];
            if (file) handleFile(file);
            imageFileInput.value = ''; 
        });

        function handleMediaInput(e, dataTransfer) {
            const html = dataTransfer.getData('text/html');
            if (html) {
                const doc = new DOMParser().parseFromString(html, 'text/html');
                const img = doc.querySelector('img');
                if (img && img.src) {
                    e.preventDefault();
                    sendImage(img.src);
                    return true;
                }
            }
            const files = dataTransfer.files;
            if (files && files.length > 0) {
                for (let i = 0; i < files.length; i++) {
                    if (files[i].type.startsWith('image/')) {
                        e.preventDefault();
                        handleFile(files[i]);
                        return true; 
                    }
                }
            }
            return false;
        }

        function handleFile(file) {
            const reader = new FileReader();
            reader.onload = () => sendImage(reader.result);
            reader.readAsDataURL(file);
        }

        function sendImage(url) {
            const user = usernameInput.value.trim() || "Anon";
            localStorage.setItem('chat_username', user);
            socket.emit("message", {
                username: user,
                type: 'image',
                url: url,
                msg: ''
            });
        }

        document.addEventListener('paste', (e) => handleMediaInput(e, e.clipboardData));
        document.addEventListener('dragover', (e) => e.preventDefault());
        document.addEventListener('drop', (e) => {
            e.preventDefault(); 
            handleMediaInput(e, e.dataTransfer);
        });

        // --- Socket Events ---
        socket.on("connect", () => {
            const user = usernameInput.value || "Anon";
            socket.emit('register', user);
        });

        socket.on("disconnect", () => {
            document.getElementById('onlineStatus').innerText = "Offline";
            document.getElementById('onlineStatus').style.color = "#ef4444";
        });

        socket.on("message", (data) => addMessage(data));

        socket.on("user_list", (data) => {
            document.getElementById('onlineStatus').innerText = `${data.count} Online`;
            document.getElementById('onlineStatus').style.color = "";
            
            const list = document.getElementById('userListDisplay');
            list.innerHTML = '<div class="tooltip-header">Active Users</div>';
            data.users.forEach(user => {
                const div = document.createElement("div");
                div.className = "user-item";
                div.innerText = user;
                list.appendChild(div);
            });
        });
    </script>
</body>
</html>
    """)

# --- SocketIO Handlers ---

@socketio.on('connect')
def handle_connect():
    pass

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in CONNECTED_USERS:
        del CONNECTED_USERS[request.sid]
    broadcast_user_list()

@socketio.on('register')
def handle_register(username):
    CONNECTED_USERS[request.sid] = username
    broadcast_user_list()

@socketio.on('message')
def handle_message(data):
    CONNECTED_USERS[request.sid] = data['username']
    data['timestamp'] = datetime.now().strftime('%H:%M')
    emit('message', data, broadcast=True)
    broadcast_user_list()

def broadcast_user_list():
    users = list(set(CONNECTED_USERS.values())) 
    emit('user_list', {'count': len(CONNECTED_USERS), 'users': users}, broadcast=True)

if __name__ == '__main__':
    print("[*] Server running on http://0.0.0.0:8080")
    socketio.run(app, host='0.0.0.0', port=8081, debug=False)
