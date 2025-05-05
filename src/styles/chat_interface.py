chat_interface_styles = '''
.chat-container {
    display: flex;
    flex-direction: column;
    height: 80vh;
    background-color: #FFFFFF;
    border-radius: 10px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    padding: 1rem;
}

.chat-history {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
    background-color: #F8F9FA;
    border-radius: 8px;
    margin-bottom: 1rem;
}

.chat-input-container {
    padding: 1rem;
    background-color: #FFFFFF;
    border-top: 1px solid #E9ECEF;
}

/* Message bubbles */
.user-message {
    background-color: #DCF8C6;
    padding: 0.75rem 1rem;
    border-radius: 15px;
    margin: 0.5rem 0;
    max-width: 70%;
    margin-left: auto;
    word-wrap: break-word;
}

.assistant-message {
    background-color: #E8E8E8;
    padding: 0.75rem 1rem;
    border-radius: 15px;
    margin: 0.5rem 0;
    max-width: 70%;
    margin-right: auto;
    word-wrap: break-word;
}

/* Input styling */
.form-control {
    border-radius: 20px;
    border: 1px solid #E9ECEF;
    padding: 0.75rem 1rem;
}

.form-control:focus {
    box-shadow: none;
    border-color: #80bdff;
}

/* Typing indicator */
.typing-indicator {
    background-color: #E8E8E8;
    padding: 8px 16px;
    border-radius: 15px;
    display: inline-block;
    font-size: 14px;
    animation: pulse 1.5s infinite;
    margin-left: 10px;
    margin-bottom: 10px;
    color: #666;
}

@keyframes pulse {
    0% { opacity: .4; }
    50% { opacity: 1; }
    100% { opacity: .4; }
}
'''