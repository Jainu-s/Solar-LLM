import streamlit as st
import time
import re
from typing import List, Dict, Any, Optional
import uuid

from frontend.utils.api import APIClient, APIError
from frontend.utils.session import initialize_conversation_if_needed, save_session
from frontend.enhanced_ui import (
    chat_message, 
    chat_suggestions, 
    loading_animation, 
    formatted_markdown,
    render_feedback_mechanism
)

# Function to handle message submission
def handle_message_submit():
    """Handle message submission from the chat input"""
    if not st.session_state.get("chat_input") or not st.session_state.get("chat_input").strip():
        return
    
    # Get user input
    user_message = st.session_state.chat_input
    
    # Clear input field
    st.session_state.chat_input = ""
    
    # Add message to chat history
    st.session_state.chat_history.append({
        "role": "user",
        "content": user_message
    })
    
    # Set processing flag to show loading indicator
    st.session_state.processing = True
    
    # Automatically rerun to update UI
    st.rerun()

# Function to handle suggestion click
def handle_suggestion_click(suggestion: str):
    """Handle a suggestion being clicked"""
    # Add message to chat history
    st.session_state.chat_history.append({
        "role": "user",
        "content": suggestion
    })
    
    # Set processing flag to show loading indicator
    st.session_state.processing = True
    
    # Automatically rerun to update UI
    st.rerun()

# Function to process the chat message and get a response
def process_chat_message(api_client: APIClient):
    """Process the latest chat message and get a response"""
    if not hasattr(st.session_state, "processing") or not st.session_state.processing:
        return
    
    # Get the latest user message
    if not st.session_state.chat_history or st.session_state.chat_history[-1]["role"] != "user":
        st.session_state.processing = False
        return
    
    user_message = st.session_state.chat_history[-1]["content"]
    
    try:
        # Get conversation settings
        web_search = st.session_state.get("web_search", False)
        model = st.session_state.get("selected_model")
        temperature = st.session_state.get("temperature", 0.7)
        
        # Generate response using API
        response = api_client.send_message(
            user_message,
            conversation_id=st.session_state.conversation_id,
            model=model,
            web_search=web_search,
            temperature=temperature
        )
        
        # Extract response content
        assistant_message = response.get("message", {})
        
        # Add response to chat history
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": assistant_message.get("content", "I couldn't generate a response. Please try again."),
            "metadata": assistant_message.get("metadata", {})
        })
        
        # Store conversation ID if this is a new conversation
        if "conversation_id" in response:
            st.session_state.conversation_id = response["conversation_id"]
            save_session()
        
        # Store suggestions
        st.session_state.suggestions = response.get("suggestions", [])
        
    except APIError as e:
        # Add error message to chat history
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": f"Error: {str(e)}",
            "metadata": {"error": True}
        })
    
    # Clear processing flag
    st.session_state.processing = False

# Render chat interface with conversation history
def render_chat_interface():
    """Render the chat interface with message history"""
    # Create container for messages
    messages_container = st.container()
    
    # Create container for input area
    input_container = st.container()
    
    # Check if suggestions exist
    has_suggestions = "suggestions" in st.session_state and st.session_state.suggestions
    
    with messages_container:
        # Render all messages in the chat history
        if st.session_state.chat_history:
            for idx, message in enumerate(st.session_state.chat_history):
                is_user = message["role"] == "user"
                chat_message(message, is_user)
                
                # Add feedback mechanism after bot responses
                if not is_user and idx == len(st.session_state.chat_history) - 1:
                    # Only show feedback for the latest bot response
                    # Create a unique ID for this feedback
                    message_id = str(uuid.uuid4())
                    render_feedback_mechanism(message_id)
        else:
            # Show welcome message
            st.markdown("""
            ## Welcome to Solar LLM! 👋
            
            I'm your virtual assistant specializing in solar energy systems and technology. 
            Ask me anything about solar power, renewable energy, or related topics!
            
            **Some things you can ask me:**
            - How do solar panels work?
            - What is the ROI on a residential solar system?
            - How many solar panels do I need for my home?
            - What are the latest solar technologies?
            - How to calculate solar system requirements?
            """)
    
    # Show loading animation if processing
    if st.session_state.get("processing", False):
        loading_animation()
    
    # Show suggestions if available and not processing
    if has_suggestions and not st.session_state.get("processing", False):
        st.subheader("Suggested questions:")
        chat_suggestions(st.session_state.suggestions, handle_suggestion_click)
    
    with input_container:
        # Options row
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            st.session_state.web_search = st.checkbox(
                "Web Search", 
                value=st.session_state.get("web_search", False),
                help="Enable web search for real-time information"
            )
        
        with col2:
            models = ["Default", "GPT-3.5", "GPT-4", "Claude"]
            st.session_state.selected_model = st.selectbox(
                "Model",
                options=models,
                index=models.index(st.session_state.get("selected_model", "Default")),
                help="Select the AI model to use"
            )
        
        with col3:
            st.session_state.temperature = st.slider(
                "Temperature",
                min_value=0.1,
                max_value=1.0,
                value=st.session_state.get("temperature", 0.7),
                step=0.1,
                help="Higher values make output more random, lower values more deterministic"
            )
        
        # Chat input
        st.text_area(
            "Message Solar LLM",
            key="chat_input",
            height=100,
            placeholder="Type your message here...",
            on_change=handle_message_submit,
            label_visibility="collapsed"
        )
        
        # Send button
        st.button("Send Message", on_click=handle_message_submit)

# Main chat page function
def chat_page(api_client: APIClient):
    """Main chat page component"""
    st.title("Solar LLM Chat")
    
    # Initialize conversation if needed
    initialize_conversation_if_needed(api_client)
    
    # Initialize chat history if needed
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    
    # Process any pending messages
    process_chat_message(api_client)
    
    # Render the chat interface
    render_chat_interface()
    
    # Options for the chat
    with st.sidebar:
        st.subheader("Conversation")
        
        # Option to start a new conversation
        if st.button("New Conversation"):
            # Create a new conversation
            try:
                response = api_client.create_conversation("New Conversation")
                st.session_state.conversation_id = response["id"]
                st.session_state.chat_history = []
                st.success("Started a new conversation")
                st.rerun()
            except APIError as e:
                st.error(f"Failed to create new conversation: {str(e)}")
        
        # Conversation history
        st.subheader("Previous Conversations")
        
        try:
            # Get up to 5 recent conversations
            conversations = api_client.get_conversations(limit=5)
            
            if conversations:
                for conv in conversations:
                    # Skip current conversation
                    if conv.get("id") == st.session_state.get("conversation_id"):
                        continue
                    
                    # Show conversation title and button to load it
                    title = conv.get("title", "Untitled Conversation")
                    if st.button(f"{title[:30]}...", key=f"conv_{conv['id']}"):
                        # Load conversation
                        conversation = api_client.get_conversation(conv["id"])
                        
                        # Update session state
                        st.session_state.conversation_id = conv["id"]
                        st.session_state.chat_history = [
                            {
                                "role": msg["role"],
                                "content": msg["content"],
                                "metadata": msg.get("metadata", {})
                            }
                            for msg in conversation.get("messages", [])
                        ]
                        st.rerun()
            else:
                st.write("No previous conversations")
                
        except APIError as e:
            st.error(f"Failed to load conversations: {str(e)}")
        
        # Upload documents section
        st.subheader("Upload Document")
        
        uploaded_file = st.file_uploader(
            "Upload a document to reference in the conversation",
            type=["pdf", "txt", "docx", "csv", "json"]
        )
        
        if uploaded_file:
            # Save uploaded file to temp location
            file_path = f"temp_{uploaded_file.name}"
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # Upload file to server
            try:
                file_response = api_client.upload_file(
                    file_path,
                    title=uploaded_file.name,
                    add_to_index=True
                )
                
                st.success(f"File uploaded: {uploaded_file.name}")
                
                # Suggest a query about the document
                doc_type = uploaded_file.name.split(".")[-1]
                doc_query = f"I just uploaded a {doc_type} file named {uploaded_file.name}. Can you help me analyze it?"
                
                if st.button("Ask about this document"):
                    # Add message to chat history
                    st.session_state.chat_history.append({
                        "role": "user",
                        "content": doc_query
                    })
                    
                    # Set processing flag
                    st.session_state.processing = True
                    st.rerun()
                
            except APIError as e:
                st.error(f"Failed to upload file: {str(e)}")