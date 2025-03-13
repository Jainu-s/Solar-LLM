import os
import time
import uuid
import json
import hashlib
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta

import jwt
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from backend.db.mongodb import get_database
from backend.utils.logging import setup_logger
from backend.utils.cache import get_cache, set_cache
from backend.config import settings

logger = setup_logger("session")

# OAuth2 password bearer scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

class SessionManager:
    """
    Manages user sessions with features:
    - JWT token generation and validation
    - Session tracking and storage
    - Rate limiting
    - Session expiration and renewal
    - Multi-device support
    """
    
    def __init__(self):
        self.db = get_database()
        self.session_collection = self.db["sessions"]
        self.secret_key = settings.JWT_SECRET_KEY
        self.access_token_expire_minutes = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_token_expire_days = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
        
        # Create index for automatic cleanup
        self.session_collection.create_index(
            "expires_at", 
            expireAfterSeconds=0  # TTL index for automatic cleanup
        )
    
    def create_session(
        self,
        user_id: str,
        username: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        additional_claims: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new session
        
        Args:
            user_id: User ID
            username: Username
            ip_address: Optional client IP address
            user_agent: Optional user agent string
            additional_claims: Optional additional JWT claims
            
        Returns:
            Dictionary with session details
        """
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        # Calculate token expiration times
        current_time = datetime.utcnow()
        access_expires = current_time + timedelta(minutes=self.access_token_expire_minutes)
        refresh_expires = current_time + timedelta(days=self.refresh_token_expire_days)
        
        # Create JWT claims
        access_claims = {
            "sub": user_id,
            "username": username,
            "session_id": session_id,
            "exp": access_expires,
            "iat": current_time,
            "type": "access"
        }
        
        refresh_claims = {
            "sub": user_id,
            "username": username,
            "session_id": session_id,
            "exp": refresh_expires,
            "iat": current_time,
            "type": "refresh"
        }
        
        # Add additional claims
        if additional_claims:
            access_claims.update(additional_claims)
            refresh_claims.update(additional_claims)
        
        # Generate tokens
        access_token = jwt.encode(
            access_claims,
            self.secret_key,
            algorithm="HS256"
        )
        
        refresh_token = jwt.encode(
            refresh_claims,
            self.secret_key,
            algorithm="HS256"
        )
        
        # Store session in database
        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "username": username,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "created_at": current_time,
            "expires_at": refresh_expires,
            "last_activity": current_time,
            "refresh_token_hash": hashlib.sha256(refresh_token.encode()).hexdigest()
        }
        
        self.session_collection.insert_one(session_data)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.access_token_expire_minutes * 60,
            "user_id": user_id,
            "username": username,
            "session_id": session_id
        }
    
    def validate_token(
        self,
        token: str,
        token_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate a JWT token
        
        Args:
            token: JWT token
            token_type: Optional token type to validate ("access" or "refresh")
            
        Returns:
            Dictionary with token claims
            
        Raises:
            HTTPException: If token is invalid
        """
        try:
            # Decode token
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=["HS256"]
            )
            
            # Check token type if specified
            if token_type and payload.get("type") != token_type:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid token type. Expected {token_type}."
                )
            
            # Get session from database
            session_id = payload.get("session_id")
            session = self.session_collection.find_one({"session_id": session_id})
            
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session not found or expired"
                )
            
            # Update last activity
            self.session_collection.update_one(
                {"session_id": session_id},
                {"$set": {"last_activity": datetime.utcnow()}}
            )
            
            return payload
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
    
    def refresh_access_token(
        self,
        refresh_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Refresh an access token using a refresh token
        
        Args:
            refresh_token: Refresh token
            ip_address: Optional client IP address
            user_agent: Optional user agent string
            
        Returns:
            Dictionary with new tokens
            
        Raises:
            HTTPException: If refresh token is invalid
        """
        try:
            # Validate refresh token
            payload = self.validate_token(refresh_token, token_type="refresh")
            
            # Calculate refresh token hash
            refresh_token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            
            # Check if refresh token matches stored hash
            session = self.session_collection.find_one({
                "session_id": payload.get("session_id"),
                "refresh_token_hash": refresh_token_hash
            })
            
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid refresh token"
                )
            
            # Generate new access token
            user_id = payload.get("sub")
            username = payload.get("username")
            session_id = payload.get("session_id")
            
            current_time = datetime.utcnow()
            access_expires = current_time + timedelta(minutes=self.access_token_expire_minutes)
            
            access_claims = {
                "sub": user_id,
                "username": username,
                "session_id": session_id,
                "exp": access_expires,
                "iat": current_time,
                "type": "access"
            }
            
            # Add any additional claims from original token
            for key, value in payload.items():
                if key not in access_claims and key not in ["exp", "iat", "type"]:
                    access_claims[key] = value
            
            # Generate new access token
            access_token = jwt.encode(
                access_claims,
                self.secret_key,
                algorithm="HS256"
            )
            
            # Update session with new activity
            self.session_collection.update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "last_activity": current_time,
                        "ip_address": ip_address,
                        "user_agent": user_agent
                    }
                }
            )
            
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": self.access_token_expire_minutes * 60,
                "user_id": user_id,
                "username": username,
                "session_id": session_id
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error refreshing access token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error refreshing access token"
            )
    
    def revoke_session(self, session_id: str) -> bool:
        """
        Revoke a session
        
        Args:
            session_id: Session ID
            
        Returns:
            True if session was revoked, False otherwise
        """
        try:
            result = self.session_collection.delete_one({"session_id": session_id})
            
            return result.deleted_count > 0
            
        except Exception as e:
            logger.error(f"Error revoking session: {str(e)}")
            return False
    
    def revoke_all_user_sessions(self, user_id: str) -> int:
        """
        Revoke all sessions for a user
        
        Args:
            user_id: User ID
            
        Returns:
            Number of revoked sessions
        """
        try:
            result = self.session_collection.delete_many({"user_id": user_id})
            
            return result.deleted_count
            
        except Exception as e:
            logger.error(f"Error revoking user sessions: {str(e)}")
            return 0
    
    def get_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all active sessions for a user
        
        Args:
            user_id: User ID
            
        Returns:
            List of active sessions
        """
        try:
            sessions = list(self.session_collection.find(
                {"user_id": user_id},
                {
                    "_id": 0,
                    "refresh_token_hash": 0
                }
            ))
            
            # Convert datetime objects to strings
            for session in sessions:
                for key in ["created_at", "expires_at", "last_activity"]:
                    if key in session and isinstance(session[key], datetime):
                        session[key] = session[key].isoformat()
            
            return sessions
            
        except Exception as e:
            logger.error(f"Error getting user sessions: {str(e)}")
            return []
    
    def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions
        
        Returns:
            Number of deleted sessions
        """
        try:
            # Find and delete expired sessions
            current_time = datetime.utcnow()
            result = self.session_collection.delete_many({
                "expires_at": {"$lt": current_time}
            })
            
            return result.deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {str(e)}")
            return 0
    
    async def get_current_user(
        self,
        token: str = Depends(oauth2_scheme)
    ) -> Dict[str, Any]:
        """
        Get the current user from a token
        
        Args:
            token: JWT token
            
        Returns:
            Dictionary with user information
            
        Raises:
            HTTPException: If token is invalid
        """
        try:
            # Validate token
            payload = self.validate_token(token, token_type="access")
            
            # Get user from database
            user_id = payload.get("sub")
            user = self.db["users"].find_one({"_id": user_id})
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found"
                )
            
            # Convert ObjectId to string
            user["_id"] = str(user["_id"])
            
            return user
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting current user: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error getting current user"
            )
    
    def generate_api_key(self, user_id: str, name: str, expiry_days: int = 365) -> str:
        """
        Generate an API key for a user
        
        Args:
            user_id: User ID
            name: API key name
            expiry_days: Number of days until expiration
            
        Returns:
            Generated API key
        """
        try:
            # Generate API key
            api_key = hashlib.sha256(os.urandom(32)).hexdigest()
            
            # Calculate expiration
            current_time = datetime.utcnow()
            expires_at = current_time + timedelta(days=expiry_days)
            
            # Store API key in database
            self.db["api_keys"].insert_one({
                "api_key_hash": hashlib.sha256(api_key.encode()).hexdigest(),
                "user_id": user_id,
                "name": name,
                "created_at": current_time,
                "expires_at": expires_at,
                "last_used": None
            })
            
            return api_key
            
        except Exception as e:
            logger.error(f"Error generating API key: {str(e)}")
            raise
    
    def validate_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Validate an API key
        
        Args:
            api_key: API key
            
        Returns:
            Dictionary with user information
            
        Raises:
            HTTPException: If API key is invalid
        """
        try:
            # Calculate API key hash
            api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            
            # Find API key in database
            api_key_doc = self.db["api_keys"].find_one({
                "api_key_hash": api_key_hash,
                "expires_at": {"$gt": datetime.utcnow()}
            })
            
            if not api_key_doc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid API key"
                )
            
            # Get user from database
            user_id = api_key_doc["user_id"]
            user = self.db["users"].find_one({"_id": user_id})
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found"
                )
            
            # Update last used timestamp
            self.db["api_keys"].update_one(
                {"api_key_hash": api_key_hash},
                {"$set": {"last_used": datetime.utcnow()}}
            )
            
            # Convert ObjectId to string
            user["_id"] = str(user["_id"])
            
            return user
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error validating API key: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error validating API key"
            )
    
    async def get_user_from_request(self, request: Request) -> Optional[Dict[str, Any]]:
        """
        Get the current user from a request
        
        Args:
            request: FastAPI request
            
        Returns:
            Dictionary with user information or None if not authenticated
        """
        try:
            # Check for authorization header
            auth_header = request.headers.get("Authorization")
            
            if auth_header:
                # Extract token from header
                if auth_header.startswith("Bearer "):
                    token = auth_header.replace("Bearer ", "")
                    
                    # Validate token
                    payload = self.validate_token(token)
                    
                    # Get user from database
                    user_id = payload.get("sub")
                    user = self.db["users"].find_one({"_id": user_id})
                    
                    if user:
                        # Convert ObjectId to string
                        user["_id"] = str(user["_id"])
                        return user
                
                # Check if it's an API key
                elif auth_header.startswith("ApiKey "):
                    api_key = auth_header.replace("ApiKey ", "")
                    return self.validate_api_key(api_key)
            
            # Check for session cookie
            session_cookie = request.cookies.get("session")
            
            if session_cookie:
                try:
                    # Parse session cookie
                    session_data = json.loads(session_cookie)
                    
                    # Validate token
                    token = session_data.get("access_token")
                    
                    if token:
                        payload = self.validate_token(token)
                        
                        # Get user from database
                        user_id = payload.get("sub")
                        user = self.db["users"].find_one({"_id": user_id})
                        
                        if user:
                            # Convert ObjectId to string
                            user["_id"] = str(user["_id"])
                            return user
                except:
                    pass
            
            # Check for API key in query parameters
            api_key = request.query_params.get("api_key")
            
            if api_key:
                return self.validate_api_key(api_key)
            
            # User not authenticated
            return None
            
        except Exception as e:
            logger.error(f"Error getting user from request: {str(e)}")
            return None

# Add this function after the SessionManager class
def ensure_safe_indices():
    """Ensure all indices are created safely, handling any conflicts."""
    db = get_database()
    
    try:
        # Fix the timestamp TTL index issue
        try:
            # Try to drop the existing timestamp index if it exists
            db["sessions"].drop_index("timestamp_1")
            logger.info("Dropped existing timestamp index to recreate with TTL")
        except Exception as e:
            # If index doesn't exist or can't be dropped, that's fine
            logger.debug(f"No existing timestamp index to drop: {str(e)}")
        
        # Now create the TTL index
        db["sessions"].create_index("timestamp", expireAfterSeconds=86400)
        logger.info("Created TTL index on timestamp with 86400s expiry")
        
        # Continue with other indices if needed
        
    except Exception as e:
        logger.error(f"Error ensuring TTL indices: {str(e)}")
        # Continue execution, don't halt startup

# Call this function during application startup to ensure indices are properly set
# For example, you could add it to your main.py startup code

# Create singleton instance
session_manager = SessionManager()