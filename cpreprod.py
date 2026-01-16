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
        :root {
            --primary: #2563eb;
            --primary-gradient: linear-gradient(135deg, #2563eb, #1d4ed8);
            --bg-color: #f3f4f6;
            --chat-bg: #ffffff;
            --text-main: #1f2937;
            --text-secondary: #6b7280;
            --bubble-self: #2563eb;
            --bubble-other: #ffffff;
            --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
            --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
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
        }

        /* --- Custom Scrollbar --- */
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background-color: #cbd5e1; border-radius: 20px; }
        ::-webkit-scrollbar-thumb:hover { background-color: #94a3b8; }

        /* --- Header --- */
        .header { 
            background: rgba(255, 255, 255, 0.85); 
            backdrop-filter: blur(12px);
            padding: 15px 25px; 
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(0,0,0,0.05);
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: var(--shadow-sm);
        }
        
        .logo-area { display: flex; align-items: center; gap: 10px; font-weight: 600; font-size: 1.1rem; color: #111; }
        .logo-icon { font-size: 1.4rem; }

        /* --- Online Status & Tooltip --- */
        .online-wrapper { position: relative; cursor: pointer; display: flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 20px; transition: background 0.2s; }
        .online-wrapper:hover { background: rgba(0,0,0,0.05); }
        .status-dot { width: 8px; height: 8px; background-color: #10b981; border-radius: 50%; box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2); }
        .online-count { font-size: 0.9rem; font-weight: 500; color: #374151; }

        .user-tooltip {
            display: none;
            position: absolute;
            right: 0;
            top: 120%;
            width: 200px;
            background: white;
            border-radius: 12px;
            padding: 8px 0;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
            border: 1px solid rgba(0,0,0,0.05);
            animation: fadeIn 0.2s ease-out;
            z-index: 50;
        }
        .online-wrapper:hover .user-tooltip { display: block; }
        .tooltip-header { padding: 8px 16px; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: #9ca3af; font-weight: 600; border-bottom: 1px solid #f3f4f6; }
        .user-item { padding: 8px 16px; font-size: 0.9rem; color: #4b5563; display: flex; align-items: center; gap: 8px; }
        .user-item:hover { background: #f9fafb; color: #111; }
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

        /* Styling for "Other" messages */
        .message-row.other .message-bubble { 
            background: var(--bubble-other); 
            color: var(--text-main); 
            border-bottom-left-radius: 4px;
        }

        /* Styling for "My" messages */
        .message-row.self .message-bubble { 
            background: var(--primary-gradient); 
            color: white; 
            border-bottom-right-radius: 4px;
            box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.2);
        }

        .message-meta { 
            font-size: 0.75rem; 
            color: #9ca3af; 
            margin-top: 4px; 
            display: flex; 
            gap: 8px; 
            padding: 0 4px;
        }
        .message-row.self .message-meta { justify-content: flex-end; }

        .system-message { 
            align-self: center; 
            background: rgba(0,0,0,0.03); 
            padding: 6px 16px; 
            border-radius: 20px; 
            font-size: 0.8rem; 
            color: #6b7280; 
            margin: 10px 0;
            max-width: 90%;
            text-align: center;
        }

        /* Images in chat */
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
            position: relative;
        }

        .input-dock {
            background: white;
            width: 100%;
            max-width: 900px;
            border-radius: 24px;
            padding: 10px;
            display: flex;
            align-items: center;
            gap: 10px;
            box-shadow: var(--shadow-md);
            border: 1px solid rgba(0,0,0,0.03);
            transition: transform 0.2s;
        }
        .input-dock:focus-within { transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); }

        .icon-btn {
            background: #f3f4f6;
            border: none;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2rem;
            color: #4b5563;
            transition: all 0.2s;
        }
        .icon-btn:hover { background: #e5e7eb; color: #111; }
        .icon-btn:active { transform: scale(0.95); }

        #username {
            border: none;
            background: #f9fafb;
            padding: 8px 12px;
            border-radius: 12px;
            font-weight: 600;
            color: #374151;
            width: 80px;
            text-align: center;
            font-size: 0.9rem;
            cursor: text;
        }
        #username:focus { background: #eff6ff; color: var(--primary); }

        #input {
            flex: 1;
            border: none;
            padding: 10px;
            font-size: 1rem;
            font-family: inherit;
        }
        #input::placeholder { color: #9ca3af; }

        #send {
            background: var(--primary-gradient);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 20px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            box-shadow: 0 2px 4px rgba(37, 99, 235, 0.3);
        }
        #send:hover { opacity: 0.9; transform: translateY(-1px); }
        #send:active { transform: translateY(1px); }

        /* Hidden inputs */
        #imageUrl, #imageFile { display: none; }

        /* Animations */
        @keyframes slideUp {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

    </style>
</head>
<body>
    <div class="header">
        <div class="logo-area">
            <span class="logo-icon">町</span>
            <span>LAN Chat</span>
            <button class="icon-btn" id="volume-btn" title="Toggle Sound" style="width: 32px; height: 32px; font-size: 1rem; margin-left: 10px; background: transparent;">粕</button>
        </div>

        <div class="online-wrapper">
            <div class="status-dot"></div>
            <div class="online-count" id="onlineStatus">Loading...</div>
            <div class="user-tooltip" id="userListDisplay">
                </div>
        </div>
    </div>
    
    <div id="messages"></div>
    
    <div class="input-wrapper">
        <div class="input-dock">
            <input id="username" title="Your Name" value="User">
            
            <button class="icon-btn" id="uploadBtn" title="Upload Image/GIF">梼</button>
            <input type="file" id="imageFile" accept="image/*">
            <input id="imageUrl"> 

            <input id="input" placeholder="Type a message..." autocomplete="off">
            <button id="send">Send</button>
        </div>
    </div>

    <script>
        const socket = io({ reconnection: true });

        const messages = document.getElementById("messages");
        const input = document.getElementById("input");
        const usernameInput = document.getElementById("username");
        const imageFileInput = document.getElementById("imageFile");
        const uploadBtn = document.getElementById("uploadBtn");
        const volumeBtn = document.getElementById("volume-btn");
        const onlineStatus = document.getElementById("onlineStatus");
        const userListDisplay = document.getElementById("userListDisplay");
        
        let soundEnabled = true;
        let unreadCount = 0;
        const originalTitle = document.title;
        const beepUrl = "https://www.myinstants.com/media/sounds/discord-notification.mp3"; 
        const audio = new Audio(beepUrl);

        if(localStorage.getItem('chat_username')) {
            usernameInput.value = localStorage.getItem('chat_username');
        }

        // --- Notifications ---
        document.body.addEventListener('click', () => {
            if (Notification.permission === 'default') Notification.requestPermission();
        }, { once: true });

        window.addEventListener('focus', () => {
            unreadCount = 0;
            document.title = originalTitle;
        });

        function notifyUser(sender, msg) {
            if (document.hidden || sender !== usernameInput.value) {
                if (soundEnabled) {
                    audio.currentTime = 0;
                    audio.play().catch(e => console.log("Audio blocked until interaction"));
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

        volumeBtn.addEventListener('click', () => {
            soundEnabled = !soundEnabled;
            volumeBtn.innerText = soundEnabled ? "粕" : "舶";
            volumeBtn.style.color = soundEnabled ? "#4b5563" : "#ef4444";
        });

        // --- Chat UI Logic ---

        function scrollToBottom() {
            messages.scrollTop = messages.scrollHeight;
        }

        function addMessage(data) {
            const isMe = data.username === usernameInput.value;
            
            // System Messages
            if (data.type === 'system') {
                const sysDiv = document.createElement("div");
                sysDiv.className = "system-message";
                sysDiv.innerText = data.msg;
                messages.appendChild(sysDiv);
                scrollToBottom();
                return;
            }

            // Notify
            const notifyText = data.type === 'image' ? (data.msg || 'sent an image') : data.msg;
            notifyUser(data.username, notifyText);

            // Container Row
            const row = document.createElement("div");
            row.className = `message-row ${isMe ? 'self' : 'other'}`;

            // Bubble
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

            // Meta (Name + Time)
            const meta = document.createElement("div");
            meta.className = "message-meta";
            
            const nameSpan = document.createElement("span");
            nameSpan.innerText = isMe ? "You" : data.username;
            nameSpan.style.fontWeight = "600";
            
            const timeSpan = document.createElement("span");
            timeSpan.innerText = data.timestamp || "";
            
            // Order depends on sender for aesthetics
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
            // Check hidden image url input in case someone pasted a raw link manually
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

        // --- Inputs & Uploads ---

        input.addEventListener("keypress", (e) => { if(e.key === "Enter") sendMessage(); });
        document.getElementById("send").addEventListener("click", sendMessage);

        uploadBtn.addEventListener('click', () => imageFileInput.click());
        imageFileInput.addEventListener('change', () => {
            const file = imageFileInput.files[0];
            if (file) handleFile(file);
            imageFileInput.value = ''; 
        });

        // --- PASTE / DROP HANDLERS (Keep this logic!) ---

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
            onlineStatus.innerText = "Offline";
            onlineStatus.style.color = "#ef4444";
        });

        socket.on("message", (data) => addMessage(data));

        socket.on("user_list", (data) => {
            onlineStatus.innerText = `${data.count} Online`;
            
            userListDisplay.innerHTML = '<div class="tooltip-header">Active Users</div>';
            data.users.forEach(user => {
                const div = document.createElement("div");
                div.className = "user-item";
                div.innerText = user;
                userListDisplay.appendChild(div);
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
    print("[*] Server running on http://0.0.0.0:8081")
    socketio.run(app, host='0.0.0.0', port=8081, debug=False)