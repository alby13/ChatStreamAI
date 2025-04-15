import os
import datetime
import uuid
import json
import logging
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

import openai
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.websockets import WebSocketDisconnect, WebSocketState
from pydantic import BaseModel, ValidationError

# --- Configuration & Initialization ---

# Load environment variables from .env file (optional, good for local dev)
load_dotenv()

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),  # Currently Logs go to console
        # logging.FileHandler("chat_app.log") # Optional
    ],
)
logger = logging.getLogger(__name__)

# --- Environment Variable Validation ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("FATAL: OPENAI_API_KEY environment variable not set.")
    raise ValueError("OPENAI_API_KEY environment variable not set.")

# Initialize OpenAI Client (Ensure API key is set before this)
try:
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    # Test connection (optional but recommended)
    client.models.list() # Make a simple call to check credentials/connectivity
    logger.info("OpenAI client initialized successfully.")
except openai.AuthenticationError:
     logger.error("FATAL: OpenAI Authentication Error. Check API key.")
     raise
except Exception as e:
    logger.error(f"FATAL: Failed to initialize OpenAI client: {e}", exc_info=True)
    raise

# Define models available for chat
MODELS = {
    'gpt-4.1-2025-04-14': 'gpt-4.1-2025-04-14',
    'o1-preview': 'o1-preview',
    'o1-mini': 'o1-mini',
    'gpt-4o': 'gpt-4o',
    'gpt-4o-mini': 'gpt-4o-mini'
}
DEFAULT_MODEL = 'gpt-4.1-2025-04-14' # Or choose your preferred default

# Context Window Limit (Characters)
MAX_CONTEXT_CHARS = 300_000

# Chat History Configuration
CHAT_DIR = Path("chat_history") # <-- Renamed directory
SAVED_CHATS_SUBDIR = "saved_chats"
SAVED_CHATS_DIR = CHAT_DIR / SAVED_CHATS_SUBDIR # Path to the subdirectory

try:
    # Create both the main directory and the subdirectory
    CHAT_DIR.mkdir(exist_ok=True)
    SAVED_CHATS_DIR.mkdir(exist_ok=True)
    logger.info(f"Main chat history directory set to: {CHAT_DIR.resolve()}")
    logger.info(f"Saved chats subdirectory set to: {SAVED_CHATS_DIR.resolve()}")
    # Test write permissions in the main directory
    test_file = CHAT_DIR / f".write_test_{uuid.uuid4()}"
    test_file.touch()
    test_file.unlink()
except OSError as e:
    logger.error(f"FATAL: Could not create or access chat directories '{CHAT_DIR}' or '{SAVED_CHATS_DIR}': {e}", exc_info=True)
    raise

# Active WebSocket Connections (Consider alternatives like Redis for multi-worker setups)
active_connections: Dict[str, WebSocket] = {}

# --- Pydantic Models for Data Validation ---

class ChatMessage(BaseModel):
    role: str  # Typically "user" or "assistant" (or "system")
    content: str

class WebSocketRequest(BaseModel):
    type: str  # e.g., "chat_message", "get_history"
    content: Optional[str] = None # Content for 'chat_message'

class WebSocketResponse(BaseModel):
    type: str  # e.g., "stream", "full_message", "error", "history"
    content: Optional[Union[str, List[ChatMessage]]] = None # For stream or full_message
    role: Optional[str] = None # For full_message
    messages: Optional[List[ChatMessage]] = None # For history
    detail: Optional[str] = None # For error messages

# --- Utility Functions ---

def save_chat_history(session_id: str, messages: List[Dict[str, str]]):
    """Saves live chat messages to a JSON file with error handling."""
    file_path = CHAT_DIR / f"{session_id}.json"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
        logger.debug(f"Live chat history saved for session {session_id} in {CHAT_DIR}")
    except IOError as e:
        logger.error(f"Error saving chat history for session {session_id} to {file_path}: {e}", exc_info=True)
        # Decide if you want to raise an exception or just log
    except Exception as e:
        logger.error(f"Unexpected error saving chat history for session {session_id}: {e}", exc_info=True)

def load_chat_history(session_id: str) -> List[Dict[str, str]]:
    """Loads chat messages from a JSON file with error handling."""
    file_path = CHAT_DIR / f"{session_id}.json"
    if not file_path.exists():
        logger.warning(f"No live chat history found for session {session_id} in {CHAT_DIR}")
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            history = json.load(f)
            # Basic validation: Ensure it's a list of dicts with 'role' and 'content'
            if not isinstance(history, list) or not all(
                isinstance(msg, dict) and 'role' in msg and 'content' in msg for msg in history
            ):
                logger.error(f"Invalid format in chat history file for session {session_id}: {file_path}")
                # Corrupted file - perhaps rename it and return empty?
                # backup_path = file_path.with_suffix(".json.corrupted")
                # file_path.rename(backup_path)
                # logger.info(f"Renamed corrupted history file to {backup_path}")
                return [] # Return empty history to avoid crashing
            logger.debug(f"Chat history loaded for session {session_id}")
            return history
    except (IOError, json.JSONDecodeError) as e:
        logger.error(f"Error loading live chat history for session {session_id} from {file_path}: {e}", exc_info=True)
        return [] # Return empty history on error
    except Exception as e:
        logger.error(f"Unexpected error loading live chat history for session {session_id}: {e}", exc_info=True)
        return []


async def send_ws_message(websocket: WebSocket, message: WebSocketResponse):
    """Safely sends a message over WebSocket, handling potential disconnects."""
    try:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json(message.model_dump(exclude_none=True))
    except WebSocketDisconnect:
        logger.warning(f"Client disconnected before message could be sent: {message.type}")
    except RuntimeError as e:
        # Handles sending on a closed connection sometimes raises RuntimeError
         if "Cannot call send" in str(e):
             logger.warning(f"Attempted to send on closed/closing websocket: {message.type}")
         else:
             logger.error(f"Runtime error sending WebSocket message: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error sending WebSocket message: {e}", exc_info=True)

# --- Utility Functions ---

def _limit_context_by_chars(
    system_prompt: str,
    history: List[Dict[str, str]],
    max_chars: int,
    model_name: str = "gpt-4.1-turbo" # Pass model for potential future tokenization
) -> List[Dict[str, str]]:
    """
    Limits the message history sent to the API based on character count.

    Keeps the system prompt and trims oldest messages first until the total
    character count is below the max_chars limit.

    Args:
        system_prompt: The system prompt content.
        history: The list of user/assistant messages (dicts with 'role' and 'content').
        max_chars: The maximum allowed character count for the context.
        model_name: The target model name (future use for tokenization).

    Returns:
        A list of messages (including system prompt) ready to be sent to the API,
        respecting the character limit.
    """
    system_message = {"role": "system", "content": system_prompt}
    working_messages = [system_message] + history  # Start with system + full history

    current_chars = len(system_prompt) + sum(len(msg.get("content", "")) for msg in history)

    if current_chars <= max_chars:
        logger.debug(f"Context within limit: {current_chars} chars. Sending full history.")
        return working_messages # No trimming needed

    logger.info(f"Context limit ({max_chars} chars) exceeded: {current_chars} chars. Trimming oldest messages.")

    # Calculate chars to remove
    chars_to_remove = current_chars - max_chars
    removed_chars_count = 0
    original_message_count = len(history)

    # Trim oldest messages (index 1 is the oldest conversational message)
    # Keep removing from the front of the conversational history (after system prompt)
    while current_chars > max_chars and len(working_messages) > 1: # Always keep system prompt
        removed_message = working_messages.pop(1) # Remove the oldest message after system prompt
        removed_len = len(removed_message.get("content", ""))
        current_chars -= removed_len
        removed_chars_count += removed_len
        logger.debug(f"Removed message (role: {removed_message.get('role', 'N/A')}, len: {removed_len}). Current chars: {current_chars}")

    final_message_count = len(working_messages) - 1 # Exclude system prompt for count comparison
    logger.info(
        f"Context trimmed. Removed ~{removed_chars_count} chars. "
        f"Final message count for API: {final_message_count} (originally {original_message_count}). "
        f"Final char count for API: {current_chars}"
    )

    # Safety check: If even the system prompt + latest message exceed limit,
    # this loop might empty history. The API might still fail, but we've tried.
    if len(working_messages) <= 1 and current_chars > max_chars:
         logger.warning(f"System prompt + latest message might still exceed limit ({current_chars} > {max_chars}). API call may fail.")

    return working_messages


# --- FastAPI Application Setup ---

app = FastAPI(title="Robust OpenAI Chat Service", version="1.0.0")

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- API Endpoints ---

@app.get("/", response_class=FileResponse)
async def get_chat_interface():
    """Serves the main chat HTML page."""
    html_file_path = Path("static/index.html")
    if not html_file_path.is_file():
         logger.error("FATAL: static/index.html not found.")
         raise HTTPException(status_code=500, detail="Chat interface file not found.")
    return FileResponse(html_file_path)

@app.post("/create_session", status_code=status.HTTP_201_CREATED)
async def create_session():
    """Creates a new chat session ID and initializes history."""
    session_id = str(uuid.uuid4())
    try:
        # Initialize with an empty history
        save_chat_history(session_id, [])
        logger.info(f"New chat session created: {session_id}")
        return {"session_id": session_id}
    except Exception as e:
        # Error during initial save_chat_history
        logger.error(f"Failed to initialize session {session_id} history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not create chat session.")

@app.get("/get_history_path", response_class=JSONResponse)
async def get_history_folder_path():
    """Returns the absolute path of the chat history directory."""
    try:
        # Ensure the path exists; it should have been created at startup
        CHAT_DIR.mkdir(exist_ok=True)
        resolved_path = str(CHAT_DIR.resolve())
        logger.info(f"Providing chat history path: {resolved_path}")
        return {"path": resolved_path}
    except Exception as e:
        logger.error(f"Could not resolve chat history path: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not determine chat history path.")

@app.post("/save_chat/{session_id}", status_code=status.HTTP_200_OK)
async def save_chat_session_manually(session_id: str):
    """
    Saves a copy of the current chat history for the given session_id
    to a new file with a timestamp.
    """
    logger.info(f"Received request to save chat for session: {session_id}")

    # Validate session_id format (basic)
    try:
        uuid.UUID(session_id)
    except ValueError:
        logger.warning(f"Invalid session ID format for save request: {session_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session ID format."
        )

    original_file_path = CHAT_DIR / f"{session_id}.json"

    if not original_file_path.exists():
        logger.warning(f"Attempted to save non-existent chat history for session: {session_id} from {CHAT_DIR}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No chat history found for session {session_id}.")

    try:
        # Ensure the SAVED_CHATS_DIR exists
        SAVED_CHATS_DIR.mkdir(exist_ok=True)

        # Generate timestamp string (suitable for filenames)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # Construct new filename
        new_filename = f"session_{session_id}_saved_{timestamp}.json"
        new_file_path = SAVED_CHATS_DIR / new_filename

        # Copy the existing history file to the new timestamped file
        shutil.copy2(original_file_path, new_file_path) # copy2 preserves metadata like modification time

        logger.info(f"Successfully saved chat history for session {session_id} to {new_file_path} (in {SAVED_CHATS_SUBDIR})")
        return {"message": "Chat history saved successfully.", "filename": new_filename}

    except FileNotFoundError:
         logger.error(f"Original history file disappeared before saving for session {session_id}", exc_info=True)
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat history file not found during save.")
    except IOError as e:
        logger.error(f"IOError while saving chat history for session {session_id} to {SAVED_CHATS_DIR}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save chat history due to server I/O error.")
    except Exception as e:
        logger.error(f"Unexpected error saving chat history for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected server error occurred during save.")

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """Handles WebSocket connections for chat sessions."""
    # Validate session_id format (basic)
    try:
        uuid.UUID(session_id)
    except ValueError:
        logger.warning(f"Invalid session ID format received: {session_id}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    logger.info(f"WebSocket connection accepted for session: {session_id}")
    active_connections[session_id] = websocket

    # Load existing history or start fresh
    messages = load_chat_history(session_id)
    # Optional: Send history to client on connect
    # await send_ws_message(websocket, WebSocketResponse(type="history", messages=[ChatMessage(**msg) for msg in messages]))

    try:
        while True:
            # Receive message from client
            try:
                raw_data = await websocket.receive_text()
                data = json.loads(raw_data)
                request_data = WebSocketRequest.model_validate(data)
                logger.debug(f"Received message from {session_id}: {request_data.type}")

            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for session {session_id} (client closed)")
                break # Exit the loop cleanly
            except json.JSONDecodeError:
                logger.warning(f"Received invalid JSON from session {session_id}")
                await send_ws_message(websocket, WebSocketResponse(type="error", detail="Invalid JSON format."))
                continue # Wait for next message
            except ValidationError as e:
                logger.warning(f"Received invalid message structure from session {session_id}: {e}")
                await send_ws_message(websocket, WebSocketResponse(type="error", detail=f"Invalid message structure: {e}"))
                continue # Wait for next message
            except Exception as e: # Catch unexpected errors during receive/parse
                 logger.error(f"Error receiving/parsing message from {session_id}: {e}", exc_info=True)
                 await send_ws_message(websocket, WebSocketResponse(type="error", detail="Server error processing your request."))
                 break # Assume connection is unstable

            # Process based on message type
            if request_data.type == "chat_message" and request_data.content:
                user_message_content = request_data.content
                messages.append({"role": "user", "content": user_message_content})

                # Prepare messages for OpenAI API
                # Define System prompt (customize System Instructions Here)
                current_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
                system_prompt = f"You are a helpful assistant. The current date and time is: {current_time}."

                # --- Limit Context Window ---
                api_messages_to_send = _limit_context_by_chars(
                    system_prompt=system_prompt,
                    history=messages, # Send the full, up-to-date history
                    max_chars=MAX_CONTEXT_CHARS,
                    model_name=DEFAULT_MODEL
                )
                # -----------------------------

                # Construct the message list for the API
                # Send system prompt + full history (adjust context window management for production)
                api_messages = [{"role": "system", "content": system_prompt}] + messages

                assistant_response_content = ""
                try:
                    logger.info(f"Sending request to OpenAI for session {session_id} (model: {DEFAULT_MODEL}) with {len(api_messages_to_send)} messages ({sum(len(m['content']) for m in api_messages_to_send)} chars).")
                    response_stream = client.chat.completions.create(
                        model=DEFAULT_MODEL,
                        messages=api_messages,
                        stream=True
                    )

                    # Stream response back to client
                    for chunk in response_stream:
                        # Check if content is present and not None
                        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content is not None:
                            chunk_content = chunk.choices[0].delta.content
                            assistant_response_content += chunk_content
                            # Send chunk to client
                            await send_ws_message(websocket, WebSocketResponse(type="stream", content=chunk_content))

                    # Send termination signal after stream
                    await send_ws_message(websocket, WebSocketResponse(type="stream", content="[DONE]"))
                    logger.info(f"Successfully streamed response for session {session_id}")

                except openai.APIConnectionError as e:
                    logger.error(f"OpenAI API Connection Error for session {session_id}: {e}", exc_info=True)
                    await send_ws_message(websocket, WebSocketResponse(type="error", detail="Could not connect to AI service."))
                except openai.RateLimitError as e:
                     logger.warning(f"OpenAI Rate Limit Error for session {session_id}: {e}", exc_info=True)
                     await send_ws_message(websocket, WebSocketResponse(type="error", detail="AI service is temporarily overloaded. Please try again later."))
                except openai.APIStatusError as e:
                     logger.error(f"OpenAI API Status Error for session {session_id}: Status={e.status_code} Response={e.response}", exc_info=True)
                     await send_ws_message(websocket, WebSocketResponse(type="error", detail=f"AI service error (Status: {e.status_code}). Please try again."))
                except Exception as e: # Catch-all for other OpenAI or streaming errors
                    logger.error(f"Error during OpenAI call or streaming for session {session_id}: {e}", exc_info=True)
                    # Attempt to send error before potentially breaking
                    await send_ws_message(websocket, WebSocketResponse(type="error", detail="An unexpected error occurred while communicating with the AI."))
                    # Depending on the error, you might want to break or continue
                    # break

                # --- Save History ---
                # Only append the assistant response if it was generated
                if assistant_response_content:
                     messages.append({"role": "assistant", "content": assistant_response_content})
                     save_chat_history(session_id, messages) # Save history including the new exchange
                elif not any(m['type'] == 'error' for m in [msg async for msg in websocket.iter_json()]): # Crude check if an error wasn't already sent
                     # If response was empty and no stream error sent, maybe log or send a generic message?
                     logger.warning(f"OpenAI response was empty for session {session_id}")
                     # await send_ws_message(websocket, WebSocketResponse(type="full_message", role="assistant", content="I received your message but didn't have a response."))


            else:
                # Handle other message types or ignore
                logger.debug(f"Received unhandled message type '{request_data.type}' or empty content from {session_id}")


    except WebSocketDisconnect:
        # This catches disconnects that happen outside the explicit receive_text try-block
        logger.info(f"WebSocket disconnected unexpectedly for session {session_id}")
    except Exception as e:
        # Catch-all for unexpected errors within the main loop
        logger.error(f"Unexpected error in WebSocket handler for session {session_id}: {e}", exc_info=True)
        # Try to inform the client before closing, if possible
        await send_ws_message(websocket, WebSocketResponse(type="error", detail="A critical server error occurred. Connection closing."))
    finally:
        # --- Cleanup ---
        logger.info(f"Cleaning up connection for session: {session_id}")
        if session_id in active_connections:
            del active_connections[session_id]
            logger.debug(f"Removed session {session_id} from active connections.")
        # Ensure WebSocket is closed, even if disconnect was already handled
        if websocket.client_state != WebSocketState.DISCONNECTED:
             try:
                 await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
                 logger.info(f"WebSocket connection explicitly closed for session: {session_id}")
             except RuntimeError as e: # Handle cases where close is called on an already closing connection
                  if "Cannot call close" in str(e):
                      logger.warning(f"Attempted to close an already closing/closed websocket for session {session_id}")
                  else:
                      logger.error(f"Runtime error during WebSocket close for {session_id}: {e}", exc_info=True)
             except Exception as e:
                 logger.error(f"Error closing WebSocket for session {session_id}: {e}", exc_info=True)


# --- Server Execution ---

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn server...")
    # Use reload=True only for development
    # For production, run via: uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4 (adjust workers as needed)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) # Set reload=False for production
