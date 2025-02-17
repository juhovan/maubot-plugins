from typing import List, Dict, Any, Optional
import re
import json

def format_message_history(messages: List[Dict[str, str]], max_length: int = 4096) -> str:
    """Format message history into a readable string with length limit."""
    formatted = []
    total_length = 0
    
    for msg in reversed(messages):
        message = f"{msg['role']}: {msg['content']}\n"
        message_length = len(message)
        
        if total_length + message_length > max_length:
            break
            
        formatted.insert(0, message)
        total_length += message_length
    
    return "".join(formatted)

def parse_function_call(response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse function call from the API response."""
    try:
        if "choices" in response and response["choices"]:
            message = response["choices"][0]["message"]
            if "tool_calls" in message and message["tool_calls"]:
                tool_call = message["tool_calls"][0]
                if "function" in tool_call:
                    function_call = tool_call["function"]
                    return {
                        "name": function_call["name"],
                        "arguments": json.loads(function_call["arguments"])
                    }
    except Exception:
        pass
    return None

def truncate_message_history(messages: List[Dict[str, str]], max_tokens: int = 4000) -> List[Dict[str, str]]:
    """Truncate message history to stay within token limit."""
    # Simple approximation: 1 token ≈ 4 characters
    char_limit = max_tokens * 4
    total_chars = 0
    
    for i, msg in enumerate(reversed(messages)):
        total_chars += len(msg["content"]) + len(msg["role"])
        if total_chars > char_limit:
            return messages[-(i):]
    
    return messages

def clean_markdown(text: str) -> str:
    """Clean markdown formatting from text."""
    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    # Remove inline code
    text = re.sub(r'`[^`]*`', '', text)
    # Remove bold/italic
    text = re.sub(r'\*\*?(.*?)\*\*?', r'\1', text)
    # Remove links
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    return text.strip()

def format_error_message(error: Exception) -> str:
    """Format error message for user display."""
    return f"An error occurred: {str(error)}" 
