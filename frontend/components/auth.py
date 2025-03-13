import streamlit as st
from typing import Dict, Any, Optional
import re

from frontend.utils.api import APIClient, APIError
from frontend.utils.session import save_session
from frontend.enhanced_ui import custom_alert

def auth_required() -> bool:
    """
    Check if user is authenticated
    
    Returns:
        True if user is authenticated, False otherwise
    """
    return st.session_state.user is not None and st.session_state.auth_token is not None

def login_page(api_client: APIClient) -> None:
    """
    Render the login page
    
    Args:
        api_client: API client instance
    """
    st.title("Login")
    
    with st.form("login_form"):
        username = st.text_input("Username or Email")
        password = st.text_input("Password", type="password")
        remember_me = st.checkbox("Remember me")
        
        submitted = st.form_submit_button("Login")
        
        if submitted:
            if not username or not password:
                st.error("Please fill in all fields.")
                return
            
            try:
                # Call login API
                response = api_client.login(username, password)
                
                # Store tokens and user info
                st.session_state.auth_token = response.get("access_token")
                st.session_state.refresh_token = response.get("refresh_token")
                
                # Get user info
                user = api_client.get_current_user()
                st.session_state.user = user
                
                # Save session and redirect to chat page
                save_session()
                st.session_state.current_page = "chat"
                st.rerun()
                
            except APIError as e:
                st.error(f"Login failed: {str(e)}")
    
    # Forgot password link
    st.markdown("---")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Forgot Password?"):
            st.session_state.current_page = "forgot_password"
            st.rerun()
    
    with col2:
        if st.button("Create an Account"):
            st.session_state.current_page = "register"
            st.rerun()

def register_page(api_client: APIClient) -> None:
    """
    Render the registration page
    
    Args:
        api_client: API client instance
    """
    st.title("Create an Account")
    
    with st.form("register_form"):
        email = st.text_input("Email")
        username = st.text_input("Username")
        full_name = st.text_input("Full Name (optional)")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        
        terms_agree = st.checkbox("I agree to the Terms of Service and Privacy Policy")
        
        submitted = st.form_submit_button("Register")
        
        if submitted:
            # Validate inputs
            if not email or not username or not password:
                st.error("Please fill in all required fields.")
                return
            
            if not terms_agree:
                st.error("You must agree to the Terms of Service and Privacy Policy.")
                return
            
            if password != confirm_password:
                st.error("Passwords do not match.")
                return
            
            # Validate email format
            if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                st.error("Please enter a valid email address.")
                return
            
            # Validate password strength
            if len(password) < 8:
                st.error("Password must be at least 8 characters long.")
                return
            
            # Basic validation for username
            if not re.match(r"^[a-zA-Z0-9_]+$", username):
                st.error("Username can only contain letters, numbers, and underscores.")
                return
            
            try:
                # Call register API
                response = api_client.register(email, username, password, full_name if full_name else None)
                
                # Show success message
                st.success("Registration successful! You can now log in.")
                
                # Redirect to login page
                st.session_state.current_page = "login"
                st.rerun()
                
            except APIError as e:
                st.error(f"Registration failed: {str(e)}")
    
    # Back to login link
    st.markdown("---")
    if st.button("Already have an account? Log in"):
        st.session_state.current_page = "login"
        st.rerun()

def forgot_password_page(api_client: APIClient) -> None:
    """
    Render the forgot password page
    
    Args:
        api_client: API client instance
    """
    st.title("Reset Password")
    
    with st.form("forgot_password_form"):
        email = st.text_input("Email")
        
        submitted = st.form_submit_button("Request Password Reset")
        
        if submitted:
            if not email:
                st.error("Please enter your email address.")
                return
            
            try:
                # In a real app, this would send a reset email
                # For this implementation, we'll just show a success message
                custom_alert(
                    "Password reset instructions have been sent to your email. "
                    "Please check your inbox and follow the instructions to reset your password.",
                    "info"
                )
                
            except APIError as e:
                custom_alert(f"Failed to request password reset: {str(e)}", "error")
    
    # Back to login link
    st.markdown("---")
    if st.button("Back to Login"):
        st.session_state.current_page = "login"
        st.rerun()

def reset_password_page(api_client: APIClient, token: str) -> None:
    """
    Render the reset password page
    
    Args:
        api_client: API client instance
        token: Password reset token
    """
    st.title("Set New Password")
    
    with st.form("reset_password_form"):
        password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        
        submitted = st.form_submit_button("Set New Password")
        
        if submitted:
            if not password:
                st.error("Please enter a new password.")
                return
            
            if password != confirm_password:
                st.error("Passwords do not match.")
                return
            
            # Validate password strength
            if len(password) < 8:
                st.error("Password must be at least 8 characters long.")
                return
            
            try:
                # In a real app, this would verify the token and set the new password
                # For this implementation, we'll just show a success message
                custom_alert("Your password has been reset successfully. You can now log in with your new password.", "success")
                
                # Redirect to login page
                st.session_state.current_page = "login"
                st.rerun()
                
            except APIError as e:
                custom_alert(f"Failed to reset password: {str(e)}", "error")
    
    # Back to login link
    st.markdown("---")
    if st.button("Back to Login"):
        st.session_state.current_page = "login"
        st.rerun()

def user_profile_section(api_client: APIClient) -> None:
    """
    Render a user profile section
    
    Args:
        api_client: API client instance
    """
    if not auth_required():
        return
    
    user = st.session_state.user
    
    st.subheader("Your Profile")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write(f"**Username:** {user.get('username', '')}")
        st.write(f"**Email:** {user.get('email', '')}")
    
    with col2:
        st.write(f"**Full Name:** {user.get('full_name', '')}")
        st.write(f"**Role:** {user.get('role', 'user')}")
    
    # Edit profile button
    if st.button("Edit Profile"):
        st.session_state.current_page = "settings"
        st.rerun()

def change_password_section(api_client: APIClient) -> None:
    """
    Render a change password section
    
    Args:
        api_client: API client instance
    """
    if not auth_required():
        return
    
    st.subheader("Change Password")
    
    with st.form("change_password_form"):
        current_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        
        submitted = st.form_submit_button("Change Password")
        
        if submitted:
            if not current_password or not new_password:
                st.error("Please fill in all fields.")
                return
            
            if new_password != confirm_password:
                st.error("New passwords do not match.")
                return
            
            # Validate password strength
            if len(new_password) < 8:
                st.error("New password must be at least 8 characters long.")
                return
            
            try:
                # In a real app, this would call the change password API
                # For this implementation, we'll just show a success message
                custom_alert("Your password has been changed successfully.", "success")
                
            except APIError as e:
                custom_alert(f"Failed to change password: {str(e)}", "error")

def active_sessions_section(api_client: APIClient) -> None:
    """
    Render an active sessions section
    
    Args:
        api_client: API client instance
    """
    if not auth_required():
        return
    
    st.subheader("Active Sessions")
    
    try:
        # In a real app, this would call the API to get active sessions
        # For this implementation, we'll just show a placeholder
        
        # Mock sessions data
        sessions = [
            {
                "session_id": "current",
                "device": "Current Session",
                "ip_address": "127.0.0.1",
                "last_activity": "Just now",
                "is_current": True
            },
            {
                "session_id": "other1",
                "device": "Chrome on Windows",
                "ip_address": "192.168.1.1",
                "last_activity": "2 hours ago",
                "is_current": False
            }
        ]
        
        for session in sessions:
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col1:
                st.write(f"**{session['device']}**")
                st.write(f"IP: {session['ip_address']} • Last activity: {session['last_activity']}")
            
            with col2:
                if session.get("is_current"):
                    st.success("Current")
            
            with col3:
                if not session.get("is_current"):
                    if st.button("Logout", key=f"logout_{session['session_id']}"):
                        # In a real app, this would call the API to revoke the session
                        custom_alert("Session has been logged out.", "success")
            
            st.markdown("---")
        
    except APIError as e:
        custom_alert(f"Failed to load sessions: {str(e)}", "error")