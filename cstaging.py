from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit
import eventlet

# Standard eventlet patch for stability
eventlet.monkey_patch()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secure_chat_key'

# FIX: Added max_http_buffer_size to allow large GIFs (10MB limit)
socketio = SocketIO(app, 
                    cors_allowed_origins="*", 
                    async_mode='eventlet', 
                    ping_timeout=60, 
                    max_http_buffer_size=10 * 1024 * 1024) 

@app.route('/')
def index():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Team Chat</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; background: #f2f2f7; display: flex; flex-direction: column; height: 100vh; }
        .header { background: #fff; padding: 15px; text-align: center; border-bottom: 1px solid #d1d1d6; font-weight: bold; font-size: 1.2rem; transition: color 0.3s; }
        
        #messages { 
            flex: 1; 
            overflow-y: scroll; 
            padding: 20px; 
            display: flex; 
            flex-direction: column; 
            gap: 10px; 
        }
        
        .message-container { display: flex; flex-direction: column; max-width: 80%; }
        .message-bubble { 
            padding: 10px 15px; 
            border-radius: 18px; 
            background: #fff; 
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
            font-size: 16px;
            color: #000;
            line-height: 1.4;
        }
        .sender-name { font-size: 12px; color: #8e8e93; margin-bottom: 2px; margin-left: 10px; }
        .system-message { align-self: center; font-size: 13px; color: #8e8e93; margin: 10px 0; background: transparent; box-shadow: none; }
        
        .input-area { 
            padding: 20px; 
            background: #fff; 
            border-top: 1px solid #d1d1d6; 
            display: flex; 
            gap: 10px; 
            flex-wrap: wrap;
        }
        
        #username { padding: 10px; border: 1px solid #d1d1d6; border-radius: 10px; width: 20%; min-width: 80px; }
        #input { padding: 10px; border: 1px solid #d1d1d6; border-radius: 10px; flex: 1; min-width: 200px; }
        #imageUrl { padding: 10px; border: 1px solid #d1d1d6; border-radius: 10px; width: 30%; min-width: 150px; }
        #imageFile { padding: 5px; border: 1px solid #d1d1d6; border-radius: 10px; width: 30%; min-width: 150px; }
        #send { 
            padding: 10px 20px; 
            background: #007aff; 
            color: white; 
            border: none; 
            border-radius: 10px; 
            font-weight: bold; 
            cursor: pointer; 
        }
        #send:active { opacity: 0.8; }
        
        /* Volume Toggle Button */
        #volume-btn {
            background: none; border: none; font-size: 1.2rem; cursor: pointer; padding: 0 10px;
        }
    </style>
</head>
<body>
    <div class="header">
        町 LAN Team Chat 
        <button id="volume-btn" title="Toggle Sound">粕</button>
    </div>
    <div id="messages"></div>
    <div class="input-area">
        <input id="username" placeholder="Name" value="User">
        <input id="input" placeholder="Type a message..." autocomplete="off">
        <input id="imageUrl" placeholder="Image/GIF URL (optional)" autocomplete="off">
        <input type="file" id="imageFile" accept="image/*" style="display: none;">
        <button id="send">Send</button>
        <button id="uploadBtn" title="Upload Image/GIF">梼</button>
    </div>

    <script>
        const socket = io({ reconnection: true });

        const messages = document.getElementById("messages");
        const input = document.getElementById("input");
        const usernameInput = document.getElementById("username");
        const imageUrlInput = document.getElementById("imageUrl");
        const imageFileInput = document.getElementById("imageFile");
        const uploadBtn = document.getElementById("uploadBtn");
        const volumeBtn = document.getElementById("volume-btn");
        
        let soundEnabled = true;
        let unreadCount = 0;
        const originalTitle = document.title;
        
        // Base64 short beep sound
        const beepUrl = "https://www.myinstants.com/media/sounds/discord-notification.mp3"; 
        const audio = new Audio(beepUrl);

        // Restore username
        if(localStorage.getItem('chat_username')) {
            usernameInput.value = localStorage.getItem('chat_username');
        }

        // --- Notification Logic ---
        
        document.body.addEventListener('click', () => {
            if (Notification.permission === 'default') {
                Notification.requestPermission();
            }
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
        });

        // --- Chat Logic ---

        function scrollToBottom() {
            messages.scrollTop = messages.scrollHeight;
        }

        function addMessage(data) {
            const container = document.createElement("div");
            container.className = "message-container";
            
            if (data.type === 'system') {
                container.classList.add("system-message");
                container.innerText = data.msg;
                messages.appendChild(container);
                scrollToBottom();
                return;
            }

            const notifyText = data.type === 'image' ? (data.msg || 'sent an image') : data.msg;
            notifyUser(data.username, notifyText);

            const name = document.createElement("div");
            name.className = "sender-name";
            name.innerText = data.username;
            
            const bubble = document.createElement("div");
            bubble.className = "message-bubble";
            
            if (data.type === 'image') {
                const img = document.createElement("img");
                img.src = data.url;
                img.style.maxWidth = "300px";
                img.style.maxHeight = "300px";
                img.style.borderRadius = "10px";
                bubble.appendChild(img);
                if (data.msg) {
                    const caption = document.createElement("div");
                    caption.innerText = data.msg;
                    caption.style.marginTop = "5px";
                    bubble.appendChild(caption);
                }
            } else {
                bubble.innerText = data.msg;
            }
            
            container.appendChild(name);
            container.appendChild(bubble);
            
            if (data.username === usernameInput.value) {
                container.style.alignSelf = "flex-end";
                bubble.style.background = "#007aff";
                bubble.style.color = "#fff";
                name.style.textAlign = "right";
                name.style.marginRight = "10px";
            } else {
                container.style.alignSelf = "flex-start";
            }
            
            messages.appendChild(container);
            scrollToBottom();
        }

        function sendMessage() {
            const msg = input.value.trim();
            const user = usernameInput.value.trim() || "Anon";
            const imageUrl = imageUrlInput.value.trim();
            
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
                imageUrlInput.value = "";
                input.focus();
            }
        }

        // --- INPUT HANDLERS ---

        input.addEventListener("keypress", (e) => { if(e.key === "Enter") sendMessage(); });
        document.getElementById("send").addEventListener("click", sendMessage);

        uploadBtn.addEventListener('click', () => imageFileInput.click());
        imageFileInput.addEventListener('change', () => {
            const file = imageFileInput.files[0];
            if (file) handleFile(file);
            imageFileInput.value = ''; 
        });

        // --- GLOBAL PASTE / DROP HANDLER ---
        // Handles Windows Emoji Picker (Win+.) and standard files
        
        function handleMediaInput(e, dataTransfer) {
            // 1. Try HTML (Browser GIFs - preserves animation)
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

            // 2. Try Files (Windows Emoji Picker / Drag & Drop)
            const files = dataTransfer.files;
            if (files && files.length > 0) {
                for (let i = 0; i < files.length; i++) {
                    // Check if it's an image
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

        // Global Paste Listener (Works even if input isn't focused)
        document.addEventListener('paste', (e) => {
            handleMediaInput(e, e.clipboardData);
        });

        // Global Drag Over (Stops browser from opening file)
        document.addEventListener('dragover', (e) => {
            e.preventDefault(); 
        });

        // Global Drop (Stops browser from opening file)
        document.addEventListener('drop', (e) => {
            e.preventDefault(); 
            handleMediaInput(e, e.dataTransfer);
        });

        socket.on("connect", () => {
            document.querySelector('.header').style.color = '#000';
            console.log("Connected");
        });
        socket.on("disconnect", () => {
            document.querySelector('.header').style.color = 'red';
            console.log("Disconnected - Packet likely too large or server restart");
        });
        socket.on("message", (data) => addMessage(data));
    </script>
</body>
</html>
    """)

@socketio.on('message')
def handle_message(data):
    emit('message', data, broadcast=True)

if __name__ == '__main__':
    print("[*] Server running on http://0.0.0.0:8081")
    socketio.run(app, host='0.0.0.0', port=8081, debug=False)