# ChatStream Browser ChatGPT o1 Text-Streaming Interface
This FastAPI application provides a real-time chat interface that allows users to interact with OpenAI's language models via WebSocket connections. The application supports session management, chat history storage, and streaming responses from the AI.

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


### Copyright &copy; 2024 alby13

All Rights Reserved.

This software is proprietary and may not be used, copied, modified, or distributed without the express written permission of the copyright holder.
