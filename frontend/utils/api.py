import requests
import json
import streamlit as st
from typing import Dict, Any, List, Optional, Union
import os
from urllib.parse import urljoin
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api_client")

class APIClient:
    """API client for interacting with the backend"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = requests.Session()
    
    def set_auth_token(self, token: str) -> None:
        """Set the authorization token for requests"""
        self.session.headers.update({"Authorization": f"Bearer {token}"})
    
    def clear_auth_token(self) -> None:
        """Clear the authorization token"""
        if "Authorization" in self.session.headers:
            del self.session.headers["Authorization"]
    
    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the API
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            data: Request data (for POST, PUT, etc.)
            params: Query parameters
            files: Files to upload
            
        Returns:
            API response as dictionary
        """
        url = urljoin(self.base_url, endpoint)
        
        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=params, **kwargs)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, params=params, files=files, **kwargs)
            elif method.upper() == "PUT":
                response = self.session.put(url, json=data, params=params, **kwargs)
            elif method.upper() == "DELETE":
                response = self.session.delete(url, json=data, params=params, **kwargs)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # Check for HTTP errors
            response.raise_for_status()
            
            # Return JSON response if available
            if response.content:
                return response.json()
            return {}
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request error: {str(e)}")
            
            # Try to parse error response
            error_msg = "Unknown error"
            try:
                if hasattr(e, "response") and e.response is not None:
                    error_data = e.response.json()
                    error_msg = error_data.get("detail", str(e))
            except:
                error_msg = str(e)
            
            raise APIError(error_msg)
    
    # Auth endpoints
    def register(self, email: str, username: str, password: str, full_name: Optional[str] = None) -> Dict[str, Any]:
        """Register a new user"""
        data = {
            "email": email,
            "username": username,
            "password": password
        }
        
        if full_name:
            data["full_name"] = full_name
        
        return self._make_request("POST", "/api/auth/register", data=data)
    
    def login(self, username: str, password: str) -> Dict[str, Any]:
        """Log in a user"""
        data = {
            "username": username,
            "password": password
        }
        
        response = self._make_request("POST", "/api/auth/login", data=data)
        
        # Set auth token for future requests
        if "access_token" in response:
            self.set_auth_token(response["access_token"])
        
        return response
    
    def logout(self, session_id: Optional[str] = None) -> None:
        """Log out the current user"""
        params = {}
        if session_id:
            params["session_id"] = session_id
        
        self._make_request("POST", "/api/auth/logout", params=params)
        self.clear_auth_token()
    
    def get_current_user(self) -> Dict[str, Any]:
        """Get the current user's profile"""
        return self._make_request("GET", "/api/auth/me")
    
    def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh an access token"""
        data = {
            "refresh_token": refresh_token
        }
        
        response = self._make_request("POST", "/api/auth/refresh", data=data)
        
        # Set new auth token for future requests
        if "access_token" in response:
            self.set_auth_token(response["access_token"])
        
        return response
    
    # Chat endpoints
    def send_message(
        self, 
        query: str, 
        conversation_id: Optional[str] = None,
        model: Optional[str] = None,
        web_search: bool = False,
        max_tokens: int = 512,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """Send a chat message"""
        data = {
            "query": query,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "web_search": web_search
        }
        
        if conversation_id:
            data["conversation_id"] = conversation_id
        
        if model:
            data["model"] = model
        
        return self._make_request("POST", "/api/chat/query", data=data)
    
    def get_suggestions(
        self, 
        conversation_id: Optional[str] = None,
        category: str = "general",
        count: int = 4
    ) -> List[str]:
        """Get query suggestions"""
        params = {
            "category": category,
            "count": count
        }
        
        if conversation_id:
            params["conversation_id"] = conversation_id
        
        response = self._make_request("GET", "/api/chat/suggestions", params=params)
        return response
    
    def submit_feedback(
        self,
        query: str,
        response: str,
        conversation_id: str,
        feedback: str,
        rating: Optional[int] = None
    ) -> Dict[str, Any]:
        """Submit feedback for a response"""
        data = {
            "query": query,
            "response": response,
            "conversation_id": conversation_id,
            "feedback": feedback
        }
        
        if rating is not None:
            data["rating"] = rating
        
        return self._make_request("POST", "/api/chat/feedback", data=data)
    
    def create_conversation(self, title: Optional[str] = None) -> Dict[str, Any]:
        """Create a new conversation"""
        data = {}
        if title:
            data["title"] = title
        
        return self._make_request("POST", "/api/chat/conversations", data=data)
    
    def get_conversations(self, limit: int = 10, skip: int = 0) -> List[Dict[str, Any]]:
        """Get user conversations"""
        params = {
            "limit": limit,
            "skip": skip
        }
        
        return self._make_request("GET", "/api/chat/conversations", params=params)
    
    def get_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """Get a conversation by ID"""
        return self._make_request("GET", f"/api/chat/conversations/{conversation_id}")
    
    def delete_conversation(self, conversation_id: str) -> None:
        """Delete a conversation"""
        self._make_request("DELETE", f"/api/chat/conversations/{conversation_id}")
    
    # File endpoints
    def upload_file(
        self, 
        file_path: str, 
        title: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        add_to_index: bool = True
    ) -> Dict[str, Any]:
        """Upload a file"""
        if not os.path.exists(file_path):
            raise ValueError(f"File not found: {file_path}")
        
        form_data = {
            "add_to_index": str(add_to_index).lower()
        }
        
        if title:
            form_data["title"] = title
        
        if description:
            form_data["description"] = description
        
        if category:
            form_data["category"] = category
        
        if tags:
            form_data["tags"] = ",".join(tags)
        
        files = {
            "file": (os.path.basename(file_path), open(file_path, "rb"))
        }
        
        try:
            return self._make_request(
                "POST", 
                "/api/files/upload", 
                data=None,  # No JSON data for multipart form
                files=files,
                params=form_data
            )
        finally:
            # Close the file
            files["file"][1].close()
    
    def list_files(
        self, 
        category: Optional[str] = None,
        file_type: Optional[str] = None,
        limit: int = 50,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        """List user files"""
        params = {
            "limit": limit,
            "skip": skip
        }
        
        if category:
            params["category"] = category
        
        if file_type:
            params["file_type"] = file_type
        
        return self._make_request("GET", "/api/files/list", params=params)
    
    def get_file(self, file_id: str, download: bool = False) -> Dict[str, Any]:
        """Get file details or download file"""
        params = {
            "download": str(download).lower()
        }
        
        return self._make_request("GET", f"/api/files/{file_id}", params=params)
    
    def delete_file(self, file_id: str, remove_from_index: bool = True) -> None:
        """Delete a file"""
        params = {
            "remove_from_index": str(remove_from_index).lower()
        }
        
        self._make_request("DELETE", f"/api/files/{file_id}", params=params)
    
    # Dashboard/Admin endpoints
    def get_system_status(self) -> Dict[str, Any]:
        """Get system status"""
        try:
            return self._make_request("GET", "/api/admin/status")
        except APIError:
            # Non-admin users can't access this endpoint
            return {"status": "unauthorized"}
    
    def get_analytics_dashboard(self, days: int = 7) -> Dict[str, Any]:
        """Get analytics dashboard data"""
        try:
            params = {
                "days": days
            }
            
            return self._make_request("GET", "/api/admin/analytics/dashboard", params=params)
        except APIError:
            # Non-admin users can't access this endpoint
            return {"status": "unauthorized"}

class APIError(Exception):
    """Exception raised for API errors"""
    pass

def init_api_client() -> APIClient:
    """Initialize the API client with configured base URL"""
    # Get API URL from environment or default to localhost
    api_url = os.environ.get("API_URL", "http://localhost:8000")
    
    # Create client instance
    client = APIClient(api_url)
    
    # If we have an auth token in session state, set it
    if "auth_token" in st.session_state and st.session_state.auth_token:
        client.set_auth_token(st.session_state.auth_token)
    
    return client