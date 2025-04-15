// --- DOM Elements ---
const chatContainer = document.getElementById('chat-container');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');
const micButton = document.getElementById('mic-button');
const statusDiv = document.getElementById('status');
const newChatButton = document.getElementById('new-chat-btn');
const settingsButton = document.getElementById('settings-btn');
const openHistoryButton = document.getElementById('open-history-btn');
const saveChatButton = document.getElementById('save-chat-btn');
const helpButton = document.getElementById('help-btn');
const initialPrompt = document.getElementById('initial-prompt');
const chatArea = document.querySelector('.chat-area');

// --- WebSocket and Session State ---
let sessionId = null;
let ws = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY_MS = 2000;

// --- Initialization ---
window.onload = initializeChat;

async function initializeChat() {
    setStatus('Initializing session...');
    enableInput(false);
    saveChatButton.disabled = true;
    resetUI();

    try {
        const response = await fetch('/create_session', { method: 'POST' });
        if (!response.ok) {
            const errorData = await response.text();
            throw new Error(`Failed to create session: ${response.status} ${response.statusText} - ${errorData}`);
        }
        const data = await response.json();
        sessionId = data.session_id;
        console.log("New Session ID:", sessionId);
        setStatus('Session created. Connecting WebSocket...');
        saveChatButton.disabled = false; // Enable save now that we have an ID
        connectWebSocket();
    } catch (error) {
        console.error('Initialization failed:', error);
        setStatus(`Error: ${error.message}`, true);
        appendMessage('error', `Failed to initialize chat session. Please check server logs or refresh.`);
    }
}

// --- WebSocket Management ---
function connectWebSocket() {
    if (!sessionId) {
        setStatus('Cannot connect: No session ID.', true);
        return;
    }
    if (ws && ws.readyState !== WebSocket.CLOSED) {
        console.log("Closing previous WebSocket connection.");
        ws.close(1000, "Starting new session");
    }

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/${sessionId}`;
    console.log("Connecting to WebSocket:", wsUrl);
    ws = new WebSocket(wsUrl);

    ws.onopen = function() {
        console.log('WebSocket connection established');
        setStatus('Connected');
        enableInput(true);
        reconnectAttempts = 0;
    };

    ws.onmessage = function(event) {
        let message; // Declare message variable here
        console.debug("Raw WS message received:", event.data); // Log raw data
        try {
            message = JSON.parse(event.data); // Parse here
            handleWebSocketMessage(message); // Pass parsed message
        } catch (error) {
            // Handle JSON parsing error separately
            console.error('Failed to parse incoming message JSON:', event.data, error);
            appendMessage('error', 'Received malformed JSON message from server.');
        }
    };

    ws.onerror = function(event) {
        console.error('WebSocket error:', event);
        setStatus('WebSocket error occurred.', true);
    };

    ws.onclose = function(event) {
        console.log(`WebSocket connection closed: Code=${event.code}, Reason='${event.reason}'`);
        enableInput(false);
        const wasConnected = ws !== null;
        ws = null;

        if (event.code !== 1000 && event.code !== 1001 && wasConnected && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
            reconnectAttempts++;
            const delay = RECONNECT_DELAY_MS * Math.pow(2, reconnectAttempts - 1);
            setStatus(`Connection lost. Reconnecting (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`, true);
            console.log(`Attempting reconnect in ${delay / 1000} seconds...`);
            setTimeout(connectWebSocket, delay);
        } else if (event.code === 1000 || event.code === 1001) {
            setStatus('Connection closed.');
        } else if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
            setStatus('Connection failed after multiple attempts. Please refresh.', true);
            appendMessage('error', 'Failed to reconnect to the server. Please refresh the page.');
        } else {
             setStatus('Disconnected.', true);
        }
    };
}


// --- Message Handling ---
function handleWebSocketMessage(message) { // message is already parsed
    console.debug("Handling parsed message:", message); // Log parsed message
    try {
        // Hide initial prompt on first actual content message
        if (initialPrompt.style.display !== 'none' && (message.type === 'stream' && message.content !== '[DONE]' || message.type === 'full_message' || (message.type === 'history' && message.messages?.length > 0))) {
            hideInitialPrompt();
        }

        switch (message.type) {
            case 'stream':
                if (message.content === "[DONE]") {
                    console.log("Stream [DONE] received.");
                    enableInput(true); // Re-enable input
                    // --- Render Markdown for the completed message ---
                    const lastMessage = chatContainer.lastElementChild;
                    if (lastMessage && lastMessage.classList.contains('assistant') && !lastMessage.dataset.rendered) {
                        console.log("Rendering final markdown for streamed message:", lastMessage);
                        renderMarkdown(lastMessage);
                        lastMessage.dataset.rendered = 'true'; // Mark as rendered
                    } else {
                         console.warn("Could not find suitable last message element to render markdown or it was already rendered.", lastMessage);
                    }
                    // --- End Markdown Rendering ---
                } else if (message.content !== null && message.content !== undefined) { // Check content exists
                    enableInput(false); // Disable input while streaming
                    appendStreamContent(message.content);
                } else {
                    console.warn("Received stream message with null/undefined content:", message)
                }
                break;
            case 'full_message':
                 if (message.role && message.content !== null && message.content !== undefined) { // Check content exists
                    console.log("Appending full message:", message);
                    appendMessage(message.role, message.content);
                } else {
                     console.warn("Received full_message with missing role/content:", message)
                }
                break;
            case 'history':
                console.log("Processing history:", message);
                chatContainer.innerHTML = ''; // Clear existing messages
                if (message.messages && Array.isArray(message.messages) && message.messages.length > 0) {
                    // hideInitialPrompt(); // Handled above
                    message.messages.forEach((msg, index) => {
                         console.debug(`Appending history message ${index}:`, msg);
                         appendMessage(msg.role, msg.content);
                    });
                } else {
                    showInitialPrompt();
                }
                break;
            case 'error':
                console.error('Server error message received:', message.detail);
                appendMessage('error', `Server error: ${message.detail || 'Unknown server error'}`);
                enableInput(true); // Re-enable input on server error
                break;
            default:
                console.warn('Received unknown message type:', message.type, message);
        }
    } catch (error) {
        // Catch errors from within the switch block or called functions
        console.error('Error handling WebSocket message content:', error); // Log the actual error
        console.error('Message content object causing error:', message); // Log the parsed message object
        appendMessage('error', `Client error processing message: ${error.message}. Check console.`); // Show more specific error
        // Optionally re-enable input if it makes sense for the error
        enableInput(true); // Re-enable input on client processing errors for now
    }
}

// --- UI Updates ---

function renderMarkdown(element) {
    if (!element) {
        console.warn("renderMarkdown called with null element.");
        return;
    }
    // Use textContent which should contain the accumulated raw markdown
    const rawMarkdown = element.textContent || "";
    console.log("Attempting to render markdown for element:", element);
    // console.log("Raw Markdown Content:", rawMarkdown); // Can be very verbose

    if (rawMarkdown.trim() === "") {
        console.log("Skipping markdown rendering for empty content.");
        return; // Don't process empty strings
    }

    try {
        // Configure marked - enable GitHub Flavored Markdown, breaks for newlines
        marked.setOptions({
             gfm: true,
             breaks: true,
        });

        // Use DOMPurify to sanitize the HTML generated by marked
        const cleanHtml = DOMPurify.sanitize(marked.parse(rawMarkdown), {
              USE_PROFILES: { html: true } // Allow standard HTML elements
        });
        // console.log("Sanitized HTML:", cleanHtml); // Can be very verbose
        element.innerHTML = cleanHtml; // Set the sanitized HTML content
        console.log("Markdown rendered successfully.");

    } catch (e) {
         console.error("Markdown rendering/sanitization error:", e);
         console.error("Markdown input that failed:", rawMarkdown);
         // Fallback to plain text using textContent for safety
         element.textContent = rawMarkdown;
    }
}


function appendMessage(role, content) {
    console.debug(`Appending message - Role: ${role}, Content Start: ${String(content).substring(0, 50)}...`);
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    // Always set text content first if we plan to render markdown from it
    // Ensure content is a string
    messageDiv.textContent = String(content);

    if (role === 'assistant') {
        console.debug("Rendering markdown for non-streamed/history assistant message.");
        renderMarkdown(messageDiv);
        messageDiv.dataset.rendered = 'true'; // Mark as rendered immediately
    } else {
        // User and error messages remain plain text (textContent already set)
        console.debug(`Appending non-assistant message (role: ${role}) as plain text.`);
    }

    chatContainer.appendChild(messageDiv);
    scrollToBottom();
}

function appendStreamContent(contentChunk) {
    let lastMessage = chatContainer.lastElementChild;
    // console.debug(`Appending stream chunk: "${contentChunk}"`); // Very verbose

    if (!lastMessage || !lastMessage.classList.contains('assistant') || lastMessage.dataset.rendered) {
        console.debug("Creating new assistant message div for stream.");
        lastMessage = document.createElement('div');
        lastMessage.className = 'message assistant';
        chatContainer.appendChild(lastMessage);
    }

    // Append raw text chunk while streaming
    lastMessage.textContent += String(contentChunk); // Ensure it's treated as string
    scrollToBottom(); // Scroll as content arrives
}


function resetUI() {
    chatContainer.innerHTML = '';
    showInitialPrompt();
    messageInput.value = '';
}

function hideInitialPrompt() {
    initialPrompt.style.display = 'none';
    chatArea.classList.add('chat-started');
}

function showInitialPrompt() {
    initialPrompt.style.display = 'flex';
     chatArea.classList.remove('chat-started');
}

function setStatus(message, isError = false) {
    statusDiv.textContent = message;
    statusDiv.style.color = isError ? '#dc3545' : '#6c757d';
    console.log(`Status: ${message}`);
}

function enableInput(enable) {
    messageInput.disabled = !enable;
    sendButton.disabled = !enable;
    micButton.disabled = !enable;
     // Keep save button enabled if session exists, independent of text input enable state
    saveChatButton.disabled = !sessionId;
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        // Scroll the main chat area container
        chatArea.scrollTop = chatArea.scrollHeight;
    });
}


// --- Event Listeners ---

sendButton.addEventListener('click', sendMessage);

messageInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

function sendMessage() {
    const messageText = messageInput.value.trim();
    if (!messageText) return;

    if (ws && ws.readyState === WebSocket.OPEN) {
         hideInitialPrompt();
        appendMessage('user', messageText);
        try {
            ws.send(JSON.stringify({
                type: "chat_message",
                content: messageText
            }));
            messageInput.value = '';
            enableInput(false); // Disable input until response stream starts/finishes
            setStatus('Waiting for response...');
        } catch (error) {
            console.error('Failed to send message:', error);
            setStatus('Error sending message.', true);
            appendMessage('error', 'Failed to send message. Check connection.');
            enableInput(true); // Re-enable input on send error
        }
    } else {
        setStatus('Not connected. Cannot send message.', true);
        appendMessage('error', 'Cannot send message. Connection is closed.');
    }
}


newChatButton.addEventListener('click', () => {
    if (confirm('Are you sure you want to start a new chat? The current conversation history (on the server) will be preserved under the old session ID, but this window will start fresh.')) {
        console.log("Starting new chat session...");
        initializeChat(); // Re-initialize
    }
});

settingsButton.addEventListener('click', () => {
    alert('Settings panel is not implemented yet.');
    console.log('Settings button clicked');
});

openHistoryButton.addEventListener('click', async () => {
    setStatus('Fetching history path...');
    try {
        const response = await fetch('/get_history_path');
        if (!response.ok) {
            throw new Error(`Failed to get path: ${response.statusText}`);
        }
        const data = await response.json();
        if (data.path) {
            alert(`Chat histories are saved in the main folder:\n${data.path}\n\nManually saved chats are in the 'saved_chats' subfolder within that path.\n\nNote: Browsers cannot open local folders directly.`);
            setStatus('History path displayed.');
        } else {
            throw new Error('Path not found in response.');
        }
    } catch (error) {
        console.error('Failed to fetch history path:', error);
        setStatus(`Error fetching history path: ${error.message}`, true);
        alert(`Error: Could not retrieve the chat history folder path from the server.`);
    }
});

saveChatButton.addEventListener('click', async () => {
    if (!sessionId) {
        alert("Cannot save chat: No active session ID.");
        return;
    }
    setStatus('Saving chat history...');
    saveChatButton.disabled = true;

    try {
        const response = await fetch(`/save_chat/${sessionId}`, { method: 'POST' });
        const responseData = await response.json();

        if (response.ok) {
            console.log("Chat saved successfully:", responseData);
            setStatus(`Chat saved as ${responseData.filename} in saved_chats`);
            setTimeout(() => {
                if (ws && ws.readyState === WebSocket.OPEN) {
                     setStatus('Connected');
                } else {
                    setStatus(statusDiv.textContent);
                }
                 // Re-enable only if session still valid
                saveChatButton.disabled = !sessionId;
            }, 2500);
        } else {
            console.error(`Failed to save chat: ${response.status}`, responseData);
            const errorDetail = responseData.detail || `Server responded with status ${response.status}`;
            setStatus(`Error saving chat: ${errorDetail}`, true);
            alert(`Error saving chat: ${errorDetail}`);
            saveChatButton.disabled = !sessionId; // Re-enable if session still valid
        }
    } catch (error) {
        console.error('Network or unexpected error saving chat:', error);
        setStatus(`Error saving chat: ${error.message}`, true);
        alert(`Error saving chat: ${error.message}`);
        saveChatButton.disabled = !sessionId; // Re-enable if session still valid
    }
});

micButton.addEventListener('click', () => {
     alert('Voice input is not implemented.');
});

helpButton.addEventListener('click', () => {
     alert('Help section is not implemented.');
});