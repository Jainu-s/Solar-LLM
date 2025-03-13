import os
import json
import streamlit as st
from typing import Dict, Any, Optional
import datetime
import time

# Session file path
SESSION_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "session.json")

def save_session() -> None:
    """Save session state to a file"""
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
    
    # Prepare session data
    session_data = {
        "auth_token": st.session_state.get("auth_token"),
        "refresh_token": st.session_state.get("refresh_token"),
        "user": st.session_state.get("user"),
        "conversation_id": st.session_state.get("conversation_id"),
        "settings": st.session_state.get("settings", {}),
        "timestamp": time.time()
    }
    
    # Don't save chat history to file for privacy
    
    # Save to file
    try:
        with open(SESSION_FILE, "w") as f:
            json.dump(session_data, f)
    except Exception as e:
        st.error(f"Failed to save session: {str(e)}")

def load_session() -> None:
    """Load session state from a file"""
    if not os.path.exists(SESSION_FILE):
        return
    
    try:
        with open(SESSION_FILE, "r") as f:
            session_data = json.load(f)
        
        # Check session expiration (24 hours)
        timestamp = session_data.get("timestamp", 0)
        if time.time() - timestamp > 24 * 60 * 60:
            clear_session()
            return
        
        # Load session data
        if "auth_token" in session_data:
            st.session_state.auth_token = session_data["auth_token"]
        
        if "refresh_token" in session_data:
            st.session_state.refresh_token = session_data["refresh_token"]
        
        if "user" in session_data:
            st.session_state.user = session_data["user"]
        
        if "conversation_id" in session_data:
            st.session_state.conversation_id = session_data["conversation_id"]
        
        if "settings" in session_data:
            st.session_state.settings = session_data["settings"]
        
    except Exception as e:
        st.error(f"Failed to load session: {str(e)}")
        clear_session()

def clear_session() -> None:
    """Clear the session file and state"""
    # Clear session file
    if os.path.exists(SESSION_FILE):
        try:
            os.remove(SESSION_FILE)
        except Exception as e:
            st.error(f"Failed to clear session file: {str(e)}")
    
    # Clear session state
    if "auth_token" in st.session_state:
        del st.session_state.auth_token
    
    if "refresh_token" in st.session_state:
        del st.session_state.refresh_token
    
    if "user" in st.session_state:
        del st.session_state.user
    
    if "conversation_id" in st.session_state:
        del st.session_state.conversation_id
    
    if "chat_history" in st.session_state:
        del st.session_state.chat_history
    
    st.session_state.current_page = "login"

def update_access_token(token: str) -> None:
    """Update the access token in session state"""
    st.session_state.auth_token = token
    save_session()

def get_user_setting(key: str, default: Any = None) -> Any:
    """Get a user setting from session state"""
    if "settings" not in st.session_state:
        st.session_state.settings = {}
    
    return st.session_state.settings.get(key, default)

def set_user_setting(key: str, value: Any) -> None:
    """Set a user setting in session state"""
    if "settings" not in st.session_state:
        st.session_state.settings = {}
    
    st.session_state.settings[key] = value
    save_session()

def get_token_expiry() -> Optional[float]:
    """Get the access token expiry time"""
    if "token_expiry" not in st.session_state:
        return None
    
    return st.session_state.token_expiry

def set_token_expiry(expires_in: int) -> None:
    """Set the access token expiry time"""
    # Calculate expiry time from current time plus expires_in seconds
    st.session_state.token_expiry = time.time() + expires_in

def should_refresh_token() -> bool:
    """Check if the access token should be refreshed"""
    expiry = get_token_expiry()
    if expiry is None:
        return False
    
    # Refresh if less than 5 minutes remaining
    return time.time() + 300 > expiry

def initialize_conversation_if_needed(api_client):
    """Initialize a new conversation if one doesn't exist"""
    if "conversation_id" not in st.session_state or not st.session_state.conversation_id:
        try:
            # Create a new conversation
            response = api_client.create_conversation("New Conversation")
            st.session_state.conversation_id = response["id"]
            st.session_state.chat_history = []
            
            # Save session
            save_session()
        except Exception as e:
            st.error(f"Failed to create conversation: {str(e)}")