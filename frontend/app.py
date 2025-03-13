import os
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
import json

from frontend.enhanced_ui import apply_custom_css, apply_custom_theme
from frontend.components.auth import login_page, register_page, auth_required
from frontend.components.chat import chat_page
from frontend.components.dashboard import dashboard_page
from frontend.components.settings import settings_page
from frontend.utils.api import init_api_client
from frontend.utils.session import load_session, save_session, clear_session

# Page configuration
st.set_page_config(
    page_title="Solar LLM",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply custom styling
apply_custom_css()
apply_custom_theme()

# Initialize API client
api_client = init_api_client()

# Initialize session state variables if they don't exist
if 'user' not in st.session_state:
    st.session_state.user = None
if 'auth_token' not in st.session_state:
    st.session_state.auth_token = None
if 'current_page' not in st.session_state:
    st.session_state.current_page = 'chat'
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'conversation_id' not in st.session_state:
    st.session_state.conversation_id = None
if 'conversations' not in st.session_state:
    st.session_state.conversations = []

# Load session on startup
load_session()

# Define navigation
def sidebar():
    """Render the sidebar navigation"""
    with st.sidebar:
        st.image("frontend/static/img/logo.png", width=200)
        st.title("Solar LLM")
        
        # Show user info or login/register options
        if st.session_state.user:
            st.write(f"Welcome, {st.session_state.user.get('username', '')}")
            
            # Navigation
            st.header("Navigation")
            
            if st.button("Chat", key="nav_chat", use_container_width=True, 
                       help="Solar LLM Chat Assistant"):
                st.session_state.current_page = 'chat'
                st.rerun()
                
            if st.button("Dashboard", key="nav_dashboard", use_container_width=True,
                       help="View analytics and usage statistics"):
                st.session_state.current_page = 'dashboard'
                st.rerun()
                
            if st.button("Settings", key="nav_settings", use_container_width=True,
                       help="Configure your preferences"):
                st.session_state.current_page = 'settings'
                st.rerun()
                
            # Logout button
            if st.button("Logout", key="nav_logout", use_container_width=True):
                clear_session()
                st.session_state.user = None
                st.session_state.auth_token = None
                st.session_state.current_page = 'login'
                st.rerun()
        else:
            # Login/Register options
            if st.button("Login", key="nav_login", use_container_width=True):
                st.session_state.current_page = 'login'
                st.rerun()
                
            if st.button("Register", key="nav_register", use_container_width=True):
                st.session_state.current_page = 'register'
                st.rerun()
        
        # Display the current version
        st.sidebar.markdown("---")
        st.sidebar.caption("Version 1.0.0")
        
        # Theme toggle (Light/Dark)
        theme = st.sidebar.radio("Theme", ["Light", "Dark"], horizontal=True)
        if theme == "Dark":
            # Apply dark theme via JavaScript
            components.html(
                """
                <script>
                document.body.classList.add('dark-theme');
                document.body.classList.remove('light-theme');
                </script>
                """,
                height=0,
            )
        else:
            # Apply light theme via JavaScript
            components.html(
                """
                <script>
                document.body.classList.add('light-theme');
                document.body.classList.remove('dark-theme');
                </script>
                """,
                height=0,
            )

def main():
    """Main application function"""
    # Display sidebar
    sidebar()
    
    # Main content area
    current_page = st.session_state.current_page
    
    # Authentication pages
    if current_page == 'login':
        login_page(api_client)
    elif current_page == 'register':
        register_page(api_client)
    else:
        # Protected pages that require authentication
        if not auth_required():
            st.session_state.current_page = 'login'
            st.rerun()
        
        # Render the appropriate page
        if current_page == 'chat':
            chat_page(api_client)
        elif current_page == 'dashboard':
            dashboard_page(api_client)
        elif current_page == 'settings':
            settings_page(api_client)
        else:
            st.error(f"Unknown page: {current_page}")
            st.session_state.current_page = 'chat'
            st.rerun()
    
    # Save session state on each run
    save_session()

if __name__ == "__main__":
    main()