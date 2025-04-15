## GPT-4.1 ChatStreamAI Web Browser Text-Streaming Chatbot Interface

<img src="https://github.com/alby13/ChatStreamAI/blob/main/gpt41-screenshot.jpg">

## Usage

1.  **Start Chatting:** Type your message in the input box at the bottom and press Enter or click the Send button.
2.  **Streaming Responses:** The assistant's response will stream in real-time. Markdown formatting will be applied once the full response is received.
3.  **New Chat:** *Note* Not Currently Working - Click the "New Chat" icon (pencil) in the top-left header to start a completely fresh session (clears the current view and gets a new session ID). *Note* Not Currently Working
4.  **History Path:** Click the "History Path" button in the header to see an alert displaying the absolute path on the *server* where the `chat_history` folder is located. Manually saved chats are within the `saved_chats` subfolder at that location.
5.  **Save Chat:** Click the "Save Chat" button (disk icon) in the header. This will create a timestamped copy of the *current* session's conversation history inside the `chat_history/saved_chats/` folder on the server.
6.  **Settings:** The "SETTINGS" button is currently a placeholder. This may be updated if there are settings for the GPT-4.1 model.

<br>

## Running the App as a Release (.exe version)

Download Version 2 from the Releases on the right. Unzip the zip file somewhere where you can find it easily.

1.  **Prepare the Distribution Folder:**
    *   **Edit the `.env` file** inside the directory is a plain text .env file that you need to change your API key on this line: `OPENAI_API_KEY=your_api_key_here`.

    The final folder structure for distribution should look like:
    ```
    ChatApp/  (This is the folder you distribute)
    ├── ChatStreamAI.exe
    ├── ... (other DLLs and files)
    │
    ├── static/       <-- Contains index.html, style.css, script.js
    │   ├── ...
    │
    └── .env          <-- Contains the API Key (user needs to add their key)
    ```

2.  **How to set up the app:**
    *   Place the entire `ChatStreamAI` folder somewhere convenient (e.g., Desktop, Documents).
    *   Edit the `.env` file within that folder and enter your own OpenAI API Key.
    *   Run the application by double-clicking `ChatStreamAI.exe`.

## Troubleshooting

*   **API Key Errors:** Ensure the `.env` file exists in the correct location (next to the `.exe` file) and contains the `OPENAI_API_KEY=...` line with a valid key. Check console logs for specific errors.
*   **Permission Errors (Executable):** The app needs write permissions in its directory to create `chat_history`. Avoid running from protected locations like `C:\Program Files`.

<br>

## Running the App as a Python program:


<br>

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

<br>

<br>

<br>

# Please Note: Everything below is for the old version for o1-preview, 2024

<img src="https://raw.githubusercontent.com/alby13/ChatStreamAI/refs/heads/main/screenshot.jpg">

## ChatStreamAI Browser ChatGPT o1-preview Text-Streaming Interface
This FastAPI application provides a real-time chat interface that allows users to interact with OpenAI's language models in the web browser via WebSocket connections. The application supports session management, chat history storage, and streaming responses from the AI.

## Features

- WebSocket Communication: Establishes a persistent connection for real-time message exchange between the client and the server.<br>
- Session Management: Each chat session is uniquely identified by a session ID, allowing users to maintain separate conversations.<br>
- Chat History: Stores chat messages in JSON format for each session, enabling users to retrieve past interactions.<br>
- Dynamic System Prompts: Incorporates the current date and time into the system prompt for context-aware responses.<br>
- Streaming Responses: Sends AI-generated responses in real-time, allowing for a more interactive user experience.<br>

## Components

- FastAPI: The web framework used to build the application.<br>
- OpenAI API: Utilizes OpenAI's language models to generate responses based on user input.<br>
- HTML/CSS Frontend: A simple web interface for users to send messages and view responses.<br>
- WebSocket: Facilitates real-time communication between the client and server.<br>

### Explanation of imports:

1. import os<br>
Purpose: The os module provides a way to interact with the operating system and access environment variables.

2. import datetime<br>
Purpose: The datetime module provides classes for manipulating dates and times in Python.

3. import uuid<br>
Purpose: The uuid module provides functions for generating unique identifiers.

4. import json<br>
Purpose: The json module provides functions for working with JSON data in Python.

5. from fastapi import FastAPI, WebSocket<br>
Purpose: FastAPI is a modern, fast (high-performance), web framework for building APIs with Python 3.7+ based on standard Python type hints.

6. from starlette.websockets import WebSocketDisconnect<br>
Purpose: The WebSocketDisconnect exception is raised when a WebSocket connection is disconnected.

7. import openai<br>
Purpose: The openai library provides a way to interact with the OpenAI API.

8. import uvicorn<br>
Purpose: Uvicorn is a lightning-fast ASGI server, which is used to run FastAPI applications.
