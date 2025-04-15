import os
import datetime
import uuid
import json
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from starlette.websockets import WebSocketDisconnect
import openai
import uvicorn
from pydantic import BaseModel
from pathlib import Path

# Initialize FastAPI app
app = FastAPI()

# Initialize OpenAI client
openai.api_type = 'openai'
openai.api_key = os.getenv("OPENAI_API_KEY")

client = openai.OpenAI()

# Define models
MODELS = {
    'o1-preview': 'o1-preview',
    'o1-mini': 'o1-mini',
    'gpt-4o': 'gpt-4o',
    'gpt-4o-mini': 'gpt-4o-mini'
}

# Get the current date and time
current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Create a directory for storing chat histories
CHAT_DIR = Path("chat_histories")
CHAT_DIR.mkdir(exist_ok=True)

# Store active WebSocket connections
active_connections: Dict[str, WebSocket] = {}

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatSession(BaseModel):
    session_id: str
    messages: List[ChatMessage]
    system_prompt: str = "The current date and time is: {current_datetime}"

class MessageRequest(BaseModel):
    session_id: str
    message: str

def save_chat_history(session_id: str, messages: List[Dict[str, str]]):
    file_path = CHAT_DIR / f"{session_id}.json"
    with open(file_path, "w") as f:
        json.dump(messages, f)

def load_chat_history(session_id: str) -> List[Dict[str, str]]:
    file_path = CHAT_DIR / f"{session_id}.json"
    if file_path.exists():
        with open(file_path) as f:
            return json.load(f)
    return []

@app.get("/", response_class=HTMLResponse)
async def get_chat_interface():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>OpenAI Self-Evaluation with Streaming</title>
        <style>
            body { max-width: 60%; margin: 0 auto; padding: 20px; font-family: Arial, sans-serif; }
            #chat-container { height: 1000px; overflow-y: auto; border: 1px solid #ccc; padding: 10px; margin-bottom: 20px; }
            #message-input { width: 80%; padding: 10px; }
            button { padding: 10px 20px; background: #007bff; color: white; border: none; cursor: pointer; }
            .message { margin: 10px 0; padding: 10px; border-radius: 5px; }
            .user { background: #e9ecef; }
            .assistant { background: #f8f9fa; }
        </style>
    </head>
    <body>
        <h3>ChatGPT</h3>
        <div id="chat-container"></div>
        <div>
            <input type="text" id="message-input" placeholder="Engage with the AI...">
            <button onclick="sendMessage()">Send</button>
        </div>
        <script>
            let sessionId = null;
            let ws = null;

            async function initializeChat() {
                const response = await fetch('/create_session', { method: 'POST' });
                const data = await response.json();
                sessionId = data.session_id;
                connectWebSocket();
            }

            function connectWebSocket() {
                ws = new WebSocket(`ws://${window.location.host}/ws/${sessionId}`);
        
                ws.onopen = function() {
                    console.log('WebSocket connection established');
                };
        
                ws.onmessage = function(event) {
                    const message = JSON.parse(event.data);
                   if (message.type === "stream") {
                        if (message.content === "[DONE]") {
                           return;
                        }
                        appendStreamContent(message.content);
                    }
                };
                        ws.onclose = function() {
                    console.log('WebSocket connection closed');
                    setTimeout(connectWebSocket, 1000);
                };
            }

            function appendMessage(role, content) {
                const chatContainer = document.getElementById('chat-container');
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${role}`;
               messageDiv.textContent = content;
               chatContainer.appendChild(messageDiv);
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }

            function appendStreamContent(content) {
                const chatContainer = document.getElementById('chat-container');
                let lastMessage = chatContainer.lastElementChild;
        
                if (!lastMessage || !lastMessage.classList.contains('assistant')) {
                    lastMessage = document.createElement('div');
                    lastMessage.className = 'message assistant';
                    chatContainer.appendChild(lastMessage);
                }
        
                lastMessage.textContent += content;
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }

            function sendMessage() {
                const input = document.getElementById('message-input');
                const message = input.value.trim();
        
                if (message && ws && ws.readyState === WebSocket.OPEN) {
                    appendMessage('user', message);
                    ws.send(JSON.stringify({
                        message: message
                    }));
                   input.value = '';
                }
            }

            document.getElementById('message-input').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    sendMessage();
                }
            });

            initializeChat();
        </script>
    </body>
    </html>
    """

@app.post("/create_session")
async def create_session():
    session_id = str(uuid.uuid4())
    save_chat_history(session_id, [])
    return {"session_id": session_id}

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    active_connections[session_id] = websocket
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            messages = load_chat_history(session_id)
            messages.append({"role": "user", "content": message_data['message']})
            
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            response = client.chat.completions.create(
                model=MODELS['o1-preview'],
                messages=[
                    {
                        "role": "user",
                        "content": f"""<system_prompt>The current date and time is: {current_time}</system_prompt>
<context></context>
<user_prompt>{message_data['message']}</user_prompt>"""
                    }
                ],
                stream=True
            )
            
            assistant_message = ""
            for chunk in response:
                if chunk.choices[0].delta.content:
                    chunk_content = chunk.choices[0].delta.content
                    assistant_message += chunk_content
                    await websocket.send_json({
                        "type": "stream",
                        "content": chunk_content
                    })
            
            await websocket.send_json({
                "type": "stream",
                "content": "[DONE]"
            })
            
            messages.append({"role": "assistant", "content": assistant_message})
            save_chat_history(session_id, messages)
            
    except WebSocketDisconnect:
        del active_connections[session_id]
    except Exception as e:
        print(f"Error in WebSocket connection: {str(e)}")
        try:
            del active_connections[session_id]
            await websocket.close()
        except:
            pass

if __name__ == "__main__":
    # Run the server with host set to "0.0.0.0" to make it externally accessible
    uvicorn.run(app, host="0.0.0.0", port=8000)
