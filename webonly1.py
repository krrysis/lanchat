from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit
import eventlet

# Standard eventlet patch for stability
eventlet.monkey_patch()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secure_chat_key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', ping_timeout=60)

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
        .header { background: #fff; padding: 15px; text-align: center; border-bottom: 1px solid #d1d1d6; font-weight: bold; font-size: 1.2rem; }
        
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
        💬 LAN Team Chat 
        <button id="volume-btn" title="Toggle Sound">🔔</button>
    </div>
    <div id="messages"></div>
    <div class="input-area">
        <input id="username" placeholder="Name" value="User">
        <input id="input" placeholder="Type a message..." autocomplete="off">
        <input id="imageUrl" placeholder="Image/GIF URL (optional)" autocomplete="off">
        <button id="send">Send</button>
    </div>

    <script>
        const socket = io({ reconnection: true });

        const messages = document.getElementById("messages");
        const input = document.getElementById("input");
        const usernameInput = document.getElementById("username");
        const imageUrlInput = document.getElementById("imageUrl");
        const volumeBtn = document.getElementById("volume-btn");
        
        let soundEnabled = true;
        let unreadCount = 0;
        const originalTitle = document.title;
        
        // Base64 short beep sound (no external file needed)
        const notificationSound = new Audio("data:audio/wav;base64,UklGRl9vT19XQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YU"); 
        // Note: The base64 string above is a placeholder. 
        // Replacing with a real short beep base64 for better experience:
        const beepUrl = "https://www.myinstants.com/media/sounds/discord-notification.mp3"; 
        const audio = new Audio(beepUrl);

        // Restore username
        if(localStorage.getItem('chat_username')) {
            usernameInput.value = localStorage.getItem('chat_username');
        }

        // --- Notification Logic ---
        
        // 1. Request Browser Permission on click
        document.body.addEventListener('click', () => {
            if (Notification.permission === 'default') {
                Notification.requestPermission();
            }
        }, { once: true });

        // 2. Handle Window Focus (Clear notifications)
        window.addEventListener('focus', () => {
            unreadCount = 0;
            document.title = originalTitle;
        });

        function notifyUser(sender, msg) {
            // Only notify if window is hidden or it's not me
            if (document.hidden || sender !== usernameInput.value) {
                
                // Sound
                if (soundEnabled) {
                    audio.currentTime = 0;
                    audio.play().catch(e => console.log("Audio blocked until interaction"));
                }

                // Title Flashing
                if (document.hidden) {
                    unreadCount++;
                    document.title = `(${unreadCount}) New Message!`;
                }
                
                // Desktop Notification
                if (document.hidden && Notification.permission === "granted") {
                    new Notification(`New message from ${sender}`, {
                        body: msg,
                        icon: 'https://cdn-icons-png.flaticon.com/512/134/134914.png'
                    });
                }
            }
        }

        // Toggle Sound
        volumeBtn.addEventListener('click', () => {
            soundEnabled = !soundEnabled;
            volumeBtn.innerText = soundEnabled ? "🔔" : "🔕";
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

            // NOTIFY USER HERE
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
                    data.msg = msg; // optional caption
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

        input.addEventListener("keypress", (e) => { if(e.key === "Enter") sendMessage(); });
        document.getElementById("send").addEventListener("click", sendMessage);
        
        socket.on("connect", () => {
            document.querySelector('.header').style.color = '#000';
        });
        socket.on("disconnect", () => {
            document.querySelector('.header').style.color = 'red';
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
    print("[*] Server running on http://0.0.0.0:8080")
    socketio.run(app, host='0.0.0.0', port=8080, debug=False)

