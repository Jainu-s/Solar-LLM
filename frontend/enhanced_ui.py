import os
import streamlit as st
import streamlit.components.v1 as components
from typing import Optional, Dict, Any, List

def apply_custom_css():
    """Apply custom CSS to the Streamlit app"""
    # Get the directory of this file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Load CSS files
    css_files = [
        os.path.join(current_dir, "static", "css", "main.css"),
        os.path.join(current_dir, "static", "css", "themes.css")
    ]
    
    css = ""
    for css_file in css_files:
        if os.path.exists(css_file):
            with open(css_file, "r") as f:
                css += f.read() + "\n"
    
    # Apply the CSS
    st.markdown(f"""
        <style>
        {css}
        </style>
    """, unsafe_allow_html=True)
    
    # Hide Streamlit's default menu and footer
    hide_streamlit_style = """
        <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        .stDeployButton {display:none;}
        .stSidebar [data-testid="stSidebarNav"] {display:none;}
        [data-testid="collapsedControl"] {display:none;}
        </style>
    """
    st.markdown(hide_streamlit_style, unsafe_allow_html=True)

def apply_custom_theme():
    """Apply a custom theme to the Streamlit app"""
    # Set custom theme using st.set_theme
    # Currently, Streamlit doesn't support setting themes programmatically
    # This is a placeholder for future functionality
    pass

def card(title: str, content: Any, footer: Optional[Any] = None):
    """Render a custom card component"""
    with st.container():
        st.markdown(f"""
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">{title}</h3>
                </div>
                <div class="card-content">
                    {content if isinstance(content, str) else ""}
                </div>
                {f'<div class="card-footer">{footer}</div>' if footer else ''}
            </div>
        """, unsafe_allow_html=True)

def chat_message(message: Dict[str, Any], is_user: bool = False):
    """Render a custom chat message component"""
    role = "user" if is_user else "assistant"
    
    message_html = f"""
    <div class="chat-message chat-message-{role}">
        <div class="chat-message-content">
            {message.get('content', '')}
        </div>
    </div>
    """
    
    st.markdown(message_html, unsafe_allow_html=True)

def chat_suggestions(suggestions: List[str], on_click=None):
    """Render chat suggestions as clickable buttons"""
    if not suggestions:
        return
    
    col1, col2 = st.columns([6, 6])
    
    # Split suggestions into two columns
    half = len(suggestions) // 2 + len(suggestions) % 2
    first_half = suggestions[:half]
    second_half = suggestions[half:]
    
    with col1:
        for i, suggestion in enumerate(first_half):
            if st.button(suggestion, key=f"sugg_{i}"):
                if on_click:
                    on_click(suggestion)
    
    with col2:
        for i, suggestion in enumerate(second_half):
            if st.button(suggestion, key=f"sugg_{i+half}"):
                if on_click:
                    on_click(suggestion)

def formatted_markdown(content: str):
    """Render markdown content with custom formatting"""
    st.markdown(f"""
        <div class="markdown-content">
            {content}
        </div>
    """, unsafe_allow_html=True)

def custom_file_uploader(label: str, accept_multiple_files: bool = False, key: Optional[str] = None):
    """Custom styled file uploader"""
    uploaded_file = st.file_uploader(
        label, 
        accept_multiple_files=accept_multiple_files,
        key=key
    )
    return uploaded_file

def custom_text_input(label: str, placeholder: str = "", value: str = "", key: Optional[str] = None):
    """Custom styled text input"""
    # Currently using Streamlit's native text_input
    # Could be extended with custom JavaScript for enhanced functionality
    return st.text_input(label, placeholder=placeholder, value=value, key=key)

def custom_text_area(label: str, placeholder: str = "", value: str = "", key: Optional[str] = None, height: int = 200):
    """Custom styled text area"""
    # Currently using Streamlit's native text_area
    # Could be extended with custom JavaScript for enhanced functionality
    return st.text_area(label, placeholder=placeholder, value=value, key=key, height=height)

def custom_button(label: str, on_click=None, key: Optional[str] = None, type: str = "primary"):
    """Custom styled button"""
    # Currently using Streamlit's native button
    # Could be extended with custom JavaScript for enhanced functionality
    return st.button(label, on_click=on_click, key=key)

def custom_select(label: str, options: List[str], index: int = 0, key: Optional[str] = None):
    """Custom styled select dropdown"""
    # Currently using Streamlit's native selectbox
    # Could be extended with custom JavaScript for enhanced functionality
    return st.selectbox(label, options, index=index, key=key)

def custom_alert(message: str, type: str = "info"):
    """Custom styled alert component"""
    icon = {
        "info": "ℹ️",
        "success": "✅",
        "warning": "⚠️",
        "error": "❌"
    }.get(type, "ℹ️")
    
    alert_html = f"""
    <div class="alert alert-{type}">
        {icon} {message}
    </div>
    """
    
    st.markdown(alert_html, unsafe_allow_html=True)

def custom_badge(text: str, type: str = "primary"):
    """Custom badge component"""
    badge_html = f"""
    <span class="badge badge-{type}">
        {text}
    </span>
    """
    
    st.markdown(badge_html, unsafe_allow_html=True)

def custom_tabs(tabs: Dict[str, Any], key: Optional[str] = None):
    """Custom tabs component"""
    tab_names = list(tabs.keys())
    
    # Use Streamlit's native tabs
    st_tabs = st.tabs(tab_names)
    
    for i, (tab_name, tab_content) in enumerate(tabs.items()):
        with st_tabs[i]:
            # Render the tab content
            if callable(tab_content):
                tab_content()
            else:
                st.markdown(tab_content, unsafe_allow_html=True)

def loading_animation():
    """Show a custom loading animation"""
    loading_html = """
    <div class="loading-animation">
        <div class="spinner"></div>
        <p>Processing your request...</p>
    </div>
    
    <style>
    .loading-animation {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 2rem;
    }
    
    .spinner {
        width: 50px;
        height: 50px;
        border: 3px solid rgba(59, 130, 246, 0.3);
        border-radius: 50%;
        border-top-color: #3B82F6;
        animation: spin 1s ease-in-out infinite;
    }
    
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    </style>
    """
    
    st.markdown(loading_html, unsafe_allow_html=True)

def syntax_highlight(code: str, language: str = "python"):
    """Syntax highlight code blocks using Prism.js"""
    prism_js = """
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/prism.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/components/prism-python.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/components/prism-bash.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/components/prism-javascript.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/components/prism-java.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/components/prism-json.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/plugins/autoloader/prism-autoloader.min.js"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/themes/prism.min.css" rel="stylesheet" />
    <link href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/themes/prism-okaidia.min.css" rel="stylesheet" />
    """
    
    # Sanitize the code for HTML
    import html
    sanitized_code = html.escape(code)
    
    code_html = f"""
    {prism_js}
    <pre><code class="language-{language}">{sanitized_code}</code></pre>
    <script>
    // Apply syntax highlighting
    Prism.highlightAll();
    </script>
    """
    
    components.html(code_html, height=30 + 20 * code.count('\n'))

def render_html(html_content: str, height: int = 300):
    """Render custom HTML safely"""
    components.html(html_content, height=height)

def render_feedback_mechanism(query_id: str, on_submit=None):
    """Render a feedback mechanism for responses"""
    feedback_html = """
    <div class="feedback-container">
        <div class="feedback-question">Was this response helpful?</div>
        <div class="feedback-buttons">
            <button class="feedback-button" id="thumbs-up">👍</button>
            <button class="feedback-button" id="thumbs-down">👎</button>
        </div>
        <div class="feedback-form" id="feedback-form" style="display: none;">
            <textarea class="feedback-textarea" id="feedback-text" placeholder="How can we improve this response?"></textarea>
            <button class="feedback-submit" id="feedback-submit">Submit Feedback</button>
        </div>
    </div>
    
    <style>
    .feedback-container {
        margin-top: 1rem;
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: var(--bg-secondary);
    }
    
    .feedback-question {
        font-size: 0.875rem;
        margin-bottom: 0.5rem;
    }
    
    .feedback-buttons {
        display: flex;
        gap: 0.5rem;
    }
    
    .feedback-button {
        background: none;
        border: 1px solid var(--border-medium);
        border-radius: 0.25rem;
        padding: 0.25rem 0.5rem;
        cursor: pointer;
        transition: background-color 0.15s ease-in-out;
    }
    
    .feedback-button:hover {
        background-color: var(--bg-tertiary);
    }
    
    .feedback-form {
        margin-top: 1rem;
    }
    
    .feedback-textarea {
        width: 100%;
        min-height: 5rem;
        padding: 0.5rem;
        border: 1px solid var(--border-medium);
        border-radius: 0.25rem;
        margin-bottom: 0.5rem;
        background-color: var(--bg-primary);
        color: var(--text-primary);
    }
    
    .feedback-submit {
        background-color: var(--interactive-normal);
        color: white;
        border: none;
        border-radius: 0.25rem;
        padding: 0.5rem 1rem;
        cursor: pointer;
    }
    
    .feedback-submit:hover {
        background-color: var(--interactive-hover);
    }
    </style>
    
    <script>
    // Feedback mechanism
    document.getElementById('thumbs-up').addEventListener('click', function() {
        this.style.backgroundColor = 'var(--success-50)';
        this.style.borderColor = 'var(--success)';
        document.getElementById('thumbs-down').style.backgroundColor = '';
        document.getElementById('thumbs-down').style.borderColor = 'var(--border-medium)';
        document.getElementById('feedback-form').style.display = 'block';
    });
    
    document.getElementById('thumbs-down').addEventListener('click', function() {
        this.style.backgroundColor = 'var(--error-50)';
        this.style.borderColor = 'var(--error)';
        document.getElementById('thumbs-up').style.backgroundColor = '';
        document.getElementById('thumbs-up').style.borderColor = 'var(--border-medium)';
        document.getElementById('feedback-form').style.display = 'block';
    });
    
    document.getElementById('feedback-submit').addEventListener('click', function() {
        const feedbackText = document.getElementById('feedback-text').value;
        const isPositive = document.getElementById('thumbs-up').style.backgroundColor !== '';
        
        // Call the Streamlit function to handle feedback
        if (typeof window.parent.postMessage === 'function') {
            window.parent.postMessage({
                type: 'streamlit:feedback',
                queryId: '%s',
                isPositive: isPositive,
                feedbackText: feedbackText
            }, '*');
        }
        
        // Hide the form and show a thank you message
        document.getElementById('feedback-form').innerHTML = '<p>Thank you for your feedback!</p>';
    });
    </script>
    """ % query_id
    
    components.html(feedback_html, height=200)