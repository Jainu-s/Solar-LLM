import streamlit as st
from typing import Dict, Any, Optional, List
import json

from frontend.utils.api import APIClient, APIError
from frontend.utils.session import get_user_setting, set_user_setting, save_session
from frontend.enhanced_ui import custom_alert
from frontend.components.auth import change_password_section, active_sessions_section

def settings_page(api_client: APIClient):
    """
    Main settings page component
    
    Args:
        api_client: API client instance
    """
    st.title("Settings")
    
    # Create tabs for different settings categories
    tabs = st.tabs(["Application", "Chat", "Profile", "Appearance", "Advanced"])
    
    # Application Settings
    with tabs[0]:
        render_application_settings(api_client)
    
    # Chat Settings
    with tabs[1]:
        render_chat_settings(api_client)
    
    # Profile Settings
    with tabs[2]:
        render_profile_settings(api_client)
    
    # Appearance Settings
    with tabs[3]:
        render_appearance_settings(api_client)
    
    # Advanced Settings
    with tabs[4]:
        render_advanced_settings(api_client)

def render_application_settings(api_client: APIClient):
    """Render application settings section"""
    st.header("Application Settings")
    
    # Language settings
    st.subheader("Language")
    
    language = st.selectbox(
        "Interface Language",
        options=["English", "Spanish", "French", "German", "Chinese", "Japanese"],
        index=0,
        key="language_setting"
    )
    
    if st.button("Save Language Setting"):
        set_user_setting("language", language)
        st.success(f"Language set to {language}")
    
    # Notifications settings
    st.subheader("Notifications")
    
    email_notifications = st.checkbox(
        "Email Notifications",
        value=get_user_setting("email_notifications", True),
        help="Receive email notifications for important updates"
    )
    
    browser_notifications = st.checkbox(
        "Browser Notifications",
        value=get_user_setting("browser_notifications", True),
        help="Receive browser notifications when using the web app"
    )
    
    if st.button("Save Notification Settings"):
        set_user_setting("email_notifications", email_notifications)
        set_user_setting("browser_notifications", browser_notifications)
        st.success("Notification settings saved")
    
    # API key management
    st.subheader("API Access")
    
    # Display existing API keys
    api_keys = get_user_setting("api_keys", [])
    
    if api_keys:
        st.write("Your API Keys:")
        
        for i, key in enumerate(api_keys):
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col1:
                st.write(f"**{key['name']}**")
                st.write(f"Created: {key['created']}")
            
            with col2:
                st.write(f"Status: {'Active' if key['active'] else 'Inactive'}")
            
            with col3:
                if st.button("Revoke", key=f"revoke_key_{i}"):
                    # Revoke key
                    api_keys[i]["active"] = False
                    set_user_setting("api_keys", api_keys)
                    st.success(f"API key '{key['name']}' revoked")
                    st.rerun()
    else:
        st.info("You don't have any API keys yet.")
    
    # Create new API key
    with st.expander("Create New API Key"):
        with st.form("create_api_key_form"):
            key_name = st.text_input("Key Name", placeholder="e.g., Development, Production")
            key_expiry = st.selectbox(
                "Expiration",
                options=["30 days", "90 days", "1 year", "Never"]
            )
            
            submitted = st.form_submit_button("Create API Key")
            
            if submitted:
                if not key_name:
                    st.error("Please provide a name for your API key")
                else:
                    # In a real app, call the API to create a key
                    # Here we'll simulate it
                    import datetime
                    import uuid
                    
                    new_key = {
                        "name": key_name,
                        "key": f"sk-{uuid.uuid4().hex}",
                        "created": datetime.datetime.now().strftime("%Y-%m-%d"),
                        "expires": "Never" if key_expiry == "Never" else (
                            datetime.datetime.now() + datetime.timedelta(
                                days=30 if "30" in key_expiry else 
                                     90 if "90" in key_expiry else 365
                            )
                        ).strftime("%Y-%m-%d"),
                        "active": True
                    }
                    
                    # Add to existing keys
                    api_keys.append(new_key)
                    set_user_setting("api_keys", api_keys)
                    
                    # Show the key to the user (only once)
                    st.success(f"API key created successfully!")
                    st.code(new_key["key"], language=None)
                    st.warning("Save this key securely! It won't be shown again.")

def render_chat_settings(api_client: APIClient):
    """Render chat settings section"""
    st.header("Chat Settings")
    
    # Default model
    st.subheader("Default Model")
    
    models = ["Default", "GPT-3.5", "GPT-4", "Claude"]
    default_model = st.selectbox(
        "Select default AI model",
        options=models,
        index=models.index(get_user_setting("default_model", "Default")),
        help="Model to use for generating responses"
    )
    
    # Response settings
    st.subheader("Response Settings")
    
    temperature = st.slider(
        "Temperature",
        min_value=0.1,
        max_value=1.0,
        value=get_user_setting("temperature", 0.7),
        step=0.1,
        help="Higher values make output more random, lower values more deterministic"
    )
    
    max_tokens = st.slider(
        "Maximum Response Length",
        min_value=100,
        max_value=2000,
        value=get_user_setting("max_tokens", 800),
        step=100,
        help="Maximum number of tokens in response"
    )
    
    web_search_default = st.checkbox(
        "Enable Web Search by Default",
        value=get_user_setting("web_search_default", False),
        help="Use web search for real-time information by default"
    )
    
    # Context settings
    st.subheader("Conversation Context")
    
    context_length = st.slider(
        "Context Length",
        min_value=1,
        max_value=20,
        value=get_user_setting("context_length", 10),
        step=1,
        help="Number of previous messages to include in context"
    )
    
    remember_conversations = st.checkbox(
        "Remember Conversations Between Sessions",
        value=get_user_setting("remember_conversations", True),
        help="Load previous conversations when you return"
    )
    
    # Save settings
    if st.button("Save Chat Settings"):
        set_user_setting("default_model", default_model)
        set_user_setting("temperature", temperature)
        set_user_setting("max_tokens", max_tokens)
        set_user_setting("web_search_default", web_search_default)
        set_user_setting("context_length", context_length)
        set_user_setting("remember_conversations", remember_conversations)
        
        # Update session state for chat
        st.session_state.selected_model = default_model
        st.session_state.temperature = temperature
        st.session_state.web_search = web_search_default
        
        st.success("Chat settings saved")
    
    # Data management
    st.subheader("Data Management")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Clear Chat History", use_container_width=True):
            # Clear chat history
            if "chat_history" in st.session_state:
                st.session_state.chat_history = []
            st.success("Chat history cleared")
    
    with col2:
        if st.button("Delete All Conversations", use_container_width=True):
            # In a real app, call API to delete all conversations
            st.warning("Are you sure? This cannot be undone.")
            confirm = st.button("Yes, delete all conversations")
            
            if confirm:
                # Delete conversations
                st.success("All conversations deleted")

def render_profile_settings(api_client: APIClient):
    """Render profile settings section"""
    st.header("Profile Settings")
    
    # Display current user info
    user = st.session_state.user
    
    # Edit profile form
    with st.form("edit_profile_form"):
        st.subheader("Personal Information")
        
        email = st.text_input("Email", value=user.get("email", ""))
        username = st.text_input("Username", value=user.get("username", ""))
        full_name = st.text_input("Full Name", value=user.get("full_name", ""))
        
        submitted = st.form_submit_button("Update Profile")
        
        if submitted:
            try:
                # In a real app, call API to update profile
                # Here we'll simulate it
                user["email"] = email
                user["username"] = username
                user["full_name"] = full_name
                
                # Update session state
                st.session_state.user = user
                save_session()
                
                st.success("Profile updated successfully")
                
            except APIError as e:
                st.error(f"Failed to update profile: {str(e)}")
    
    # Change password section
    st.markdown("---")
    change_password_section(api_client)
    
    # Active sessions section
    st.markdown("---")
    active_sessions_section(api_client)
    
    # Account management
    st.markdown("---")
    st.subheader("Account Management")
    
    # Export data option
    if st.button("Export Your Data"):
        # In a real app, call API to export user data
        st.info("Your data export is being prepared. You'll be notified when it's ready to download.")
    
    # Delete account option (with confirmation)
    with st.expander("Delete Account"):
        st.warning(
            "⚠️ **Warning:** Deleting your account is permanent and cannot be undone. "
            "All your data, including conversations and documents, will be permanently deleted."
        )
        
        with st.form("delete_account_form"):
            confirm_text = st.text_input(
                "Type 'DELETE' to confirm",
                help="Please type 'DELETE' in uppercase to confirm account deletion"
            )
            password = st.text_input("Enter your password", type="password")
            
            submitted = st.form_submit_button("Delete My Account")
            
            if submitted:
                if confirm_text != "DELETE":
                    st.error("Please type 'DELETE' to confirm")
                elif not password:
                    st.error("Please enter your password")
                else:
                    try:
                        # In a real app, call API to delete account
                        st.success(
                            "Your account has been scheduled for deletion. "
                            "You'll be logged out and your data will be removed within 24 hours."
                        )
                        
                        # Log the user out
                        # This would happen in a real app
                        
                    except APIError as e:
                        st.error(f"Failed to delete account: {str(e)}")

def render_appearance_settings(api_client: APIClient):
    """Render appearance settings section"""
    st.header("Appearance Settings")
    
    # Theme selection
    st.subheader("Theme")
    
    theme = st.selectbox(
        "Select theme",
        options=["Light", "Dark", "System Default"],
        index=["Light", "Dark", "System Default"].index(get_user_setting("theme", "Light")),
        help="Choose between light and dark themes"
    )
    
    # Color scheme
    st.subheader("Color Scheme")
    
    color_scheme = st.selectbox(
        "Primary Color",
        options=["Blue", "Green", "Purple", "Orange", "Red"],
        index=["Blue", "Green", "Purple", "Orange", "Red"].index(get_user_setting("color_scheme", "Blue")),
        help="Primary color for the interface"
    )
    
    # Display hexadecimal color preview
    color_hex = {
        "Blue": "#2563EB",
        "Green": "#10B981",
        "Purple": "#8B5CF6",
        "Orange": "#F97316",
        "Red": "#EF4444"
    }.get(color_scheme, "#2563EB")
    
    st.markdown(f"""
    <div style="background-color: {color_hex}; width: 100px; height: 50px; border-radius: 5px;"></div>
    <p>Hex: {color_hex}</p>
    """, unsafe_allow_html=True)
    
    # Font settings
    st.subheader("Font Settings")
    
    font_size = st.selectbox(
        "Font Size",
        options=["Small", "Medium", "Large"],
        index=["Small", "Medium", "Large"].index(get_user_setting("font_size", "Medium")),
        help="Adjust the text size throughout the interface"
    )
    
    # UI density
    st.subheader("UI Density")
    
    ui_density = st.selectbox(
        "Interface Density",
        options=["Compact", "Comfortable", "Spacious"],
        index=["Compact", "Comfortable", "Spacious"].index(get_user_setting("ui_density", "Comfortable")),
        help="Adjust spacing between UI elements"
    )
    
    # Save settings
    if st.button("Save Appearance Settings"):
        set_user_setting("theme", theme)
        set_user_setting("color_scheme", color_scheme)
        set_user_setting("font_size", font_size)
        set_user_setting("ui_density", ui_density)
        st.success("Appearance settings saved")
        
        # Apply theme
        if theme == "Dark":
            # Apply dark theme via JavaScript
            st.markdown(
                """
                <script>
                document.body.classList.add('dark-theme');
                document.body.classList.remove('light-theme');
                </script>
                """,
                unsafe_allow_html=True
            )
        else:
            # Apply light theme via JavaScript
            st.markdown(
                """
                <script>
                document.body.classList.add('light-theme');
                document.body.classList.remove('dark-theme');
                </script>
                """,
                unsafe_allow_html=True
            )
    
    # Preview theme button
    if st.button("Preview Theme"):
        # Toggle theme for preview
        preview_theme = "Dark" if theme == "Light" else "Light"
        st.info(f"Previewing {preview_theme} theme. Click 'Save Appearance Settings' to apply.")
        
        # Apply preview theme
        if preview_theme == "Dark":
            st.markdown(
                """
                <script>
                document.body.classList.add('dark-theme');
                document.body.classList.remove('light-theme');
                </script>
                """,
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                """
                <script>
                document.body.classList.add('light-theme');
                document.body.classList.remove('dark-theme');
                </script>
                """,
                unsafe_allow_html=True
            )

def render_advanced_settings(api_client: APIClient):
    """Render advanced settings section"""
    st.header("Advanced Settings")
    
    st.warning(
        "⚠️ **Caution:** These settings are for advanced users. "
        "Incorrect configuration may affect application functionality."
    )
    
    # Debug mode
    st.subheader("Developer Options")
    
    debug_mode = st.checkbox(
        "Debug Mode",
        value=get_user_setting("debug_mode", False),
        help="Show additional debugging information"
    )
    
    verbose_logging = st.checkbox(
        "Verbose Logging",
        value=get_user_setting("verbose_logging", False),
        help="Enable detailed logging for troubleshooting"
    )
    
    # Cache settings
    st.subheader("Cache Settings")
    
    use_response_cache = st.checkbox(
        "Enable Response Caching",
        value=get_user_setting("use_response_cache", True),
        help="Cache responses for faster repeat queries"
    )
    
    cache_ttl = st.slider(
        "Cache TTL (minutes)",
        min_value=5,
        max_value=1440,
        value=get_user_setting("cache_ttl", 60),
        step=5,
        help="Time-to-live for cached responses"
    )
    
    # RAG settings
    st.subheader("RAG Settings")
    
    similarity_threshold = st.slider(
        "Similarity Threshold",
        min_value=0.5,
        max_value=0.95,
        value=get_user_setting("similarity_threshold", 0.75),
        step=0.05,
        help="Minimum similarity score for document retrieval (higher = stricter matches)"
    )
    
    max_chunks = st.slider(
        "Maximum Chunks",
        min_value=1,
        max_value=20,
        value=get_user_setting("max_chunks", 5),
        step=1,
        help="Maximum number of document chunks to retrieve"
    )
    
    # Web search settings
    st.subheader("Web Search Settings")
    
    search_providers = ["DuckDuckGo", "Google", "Bing", "Custom"]
    search_provider = st.selectbox(
        "Search Provider",
        options=search_providers,
        index=search_providers.index(get_user_setting("search_provider", "DuckDuckGo")),
        help="Provider for web search functionality"
    )
    
    if search_provider == "Custom":
        custom_search_url = st.text_input(
            "Custom Search URL",
            value=get_user_setting("custom_search_url", ""),
            help="URL template for custom search (use {query} as placeholder)"
        )
    
    # Save settings
    if st.button("Save Advanced Settings"):
        set_user_setting("debug_mode", debug_mode)
        set_user_setting("verbose_logging", verbose_logging)
        set_user_setting("use_response_cache", use_response_cache)
        set_user_setting("cache_ttl", cache_ttl)
        set_user_setting("similarity_threshold", similarity_threshold)
        set_user_setting("max_chunks", max_chunks)
        set_user_setting("search_provider", search_provider)
        
        if search_provider == "Custom" and custom_search_url:
            set_user_setting("custom_search_url", custom_search_url)
        
        st.success("Advanced settings saved")
    
    # Reset settings
    st.subheader("Reset Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Reset to Defaults", use_container_width=True):
            # Reset all settings to defaults
            default_settings = {
                "theme": "Light",
                "color_scheme": "Blue",
                "font_size": "Medium",
                "ui_density": "Comfortable",
                "default_model": "Default",
                "temperature": 0.7,
                "max_tokens": 800,
                "web_search_default": False,
                "context_length": 10,
                "remember_conversations": True,
                "debug_mode": False,
                "verbose_logging": False,
                "use_response_cache": True,
                "cache_ttl": 60,
                "similarity_threshold": 0.75,
                "max_chunks": 5,
                "search_provider": "DuckDuckGo"
            }
            
            # Apply defaults
            for key, value in default_settings.items():
                set_user_setting(key, value)
            
            st.success("All settings reset to defaults")
            st.rerun()
    
    with col2:
        if st.button("Clear All Settings", use_container_width=True):
            # Clear all settings
            if "settings" in st.session_state:
                st.session_state.settings = {}
                save_session()
            
            st.success("All settings cleared")
            st.rerun()