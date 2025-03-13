import os
import time
import re
import hashlib
import secrets
from typing import Dict, Any, Optional, List, Tuple, Union
from datetime import datetime, timedelta

import bcrypt
import jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status

from backend.db.mongodb import get_database
from backend.utils.logging import setup_logger
from backend.utils.session import session_manager
from backend.config import settings

logger = setup_logger("auth")

# Password context for hashing and verification
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    """
    Authentication service with features:
    - Password hashing and verification
    - Password strength validation
    - User registration and login
    - Rate limiting
    - Brute force protection
    - Password reset flow
    """
    
    def __init__(self):
        self.db = get_database()
        self.user_collection = self.db["users"]
        self.login_attempts_collection = self.db["login_attempts"]
        self.secret_key = settings.JWT_SECRET_KEY
        self.password_reset_expire_minutes = settings.PASSWORD_RESET_EXPIRE_MINUTES
        
        # Ensure indices
        self._ensure_indices()
    
    def _ensure_indices(self) -> None:
        """Ensure database indices for auth-related collections"""
        try:
            # User collection indices
            self.user_collection.create_index("email", unique=True)
            self.user_collection.create_index("username", unique=True)
            
            # Login attempts indices
            self.login_attempts_collection.create_index("ip_address")
            self.login_attempts_collection.create_index("email")
            self.login_attempts_collection.create_index("timestamp")
            self.login_attempts_collection.create_index(
                [("ip_address", 1), ("timestamp", 1)]
            )
            self.login_attempts_collection.create_index(
                [("email", 1), ("timestamp", 1)]
            )
            
            # Create TTL index for login attempts cleanup
            self.login_attempts_collection.create_index(
                "timestamp",
                expireAfterSeconds=24 * 60 * 60  # 24 hours
            )
            
        except Exception as e:
            logger.error(f"Error ensuring indices: {str(e)}")
    
    def hash_password(self, password: str) -> str:
        """
        Hash a password using bcrypt
        
        Args:
            password: Password to hash
            
        Returns:
            Hashed password
        """
        return pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verify a password against a hash
        
        Args:
            plain_password: Plain text password
            hashed_password: Hashed password
            
        Returns:
            True if password matches hash, False otherwise
        """
        return pwd_context.verify(plain_password, hashed_password)
    
    def validate_password_strength(self, password: str) -> Tuple[bool, str]:
        """
        Validate password strength
        
        Args:
            password: Password to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check password length
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        
        # Check for uppercase letters
        if not re.search(r"[A-Z]", password):
            return False, "Password must contain at least one uppercase letter"
        
        # Check for lowercase letters
        if not re.search(r"[a-z]", password):
            return False, "Password must contain at least one lowercase letter"
        
        # Check for digits
        if not re.search(r"\d", password):
            return False, "Password must contain at least one digit"
        
        # Check for special characters
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            return False, "Password must contain at least one special character"
        
        return True, ""
    
    def register_user(
        self,
        email: str,
        username: str,
        password: str,
        full_name: Optional[str] = None,
        role: str = "user"
    ) -> Dict[str, Any]:
        """
        Register a new user
        
        Args:
            email: User email
            username: Username
            password: User password
            full_name: Optional full name
            role: User role (default: "user")
            
        Returns:
            Dictionary with created user
            
        Raises:
            HTTPException: If registration fails
        """
        try:
            # Normalize email and username
            email = email.lower().strip()
            username = username.lower().strip()
            
            # Check if email or username already exists
            existing_user = self.user_collection.find_one({
                "$or": [
                    {"email": email},
                    {"username": username}
                ]
            })
            
            if existing_user:
                if existing_user.get("email") == email:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email already registered"
                    )
                
                if existing_user.get("username") == username:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Username already taken"
                    )
            
            # Validate password strength
            is_valid, error_message = self.validate_password_strength(password)
            
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_message
                )
            
            # Hash password
            hashed_password = self.hash_password(password)
            
            # Create user
            user = {
                "email": email,
                "username": username,
                "password": hashed_password,
                "full_name": full_name,
                "role": role,
                "created_at": datetime.utcnow(),
                "last_login": None,
                "active": True,
                "settings": {
                    "theme": "light",
                    "language": "en"
                }
            }
            
            # Insert user
            result = self.user_collection.insert_one(user)
            
            # Get created user
            created_user = self.user_collection.find_one({"_id": result.inserted_id})
            
            # Remove password from returned user
            created_user.pop("password", None)
            
            # Convert ObjectId to string
            created_user["_id"] = str(created_user["_id"])
            
            return created_user
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error registering user: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error registering user"
            )
    
    def authenticate_user(
        self,
        email_or_username: str,
        password: str,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Authenticate a user
        
        Args:
            email_or_username: User email or username
            password: User password
            ip_address: Optional client IP address
            
        Returns:
            Dictionary with user data
            
        Raises:
            HTTPException: If authentication fails
        """
        try:
            # Normalize input
            email_or_username = email_or_username.lower().strip()
            
            # Check for too many login attempts
            if ip_address:
                self._check_login_attempts(email_or_username, ip_address)
            
            # Find user
            user = self.user_collection.find_one({
                "$or": [
                    {"email": email_or_username},
                    {"username": email_or_username}
                ]
            })
            
            # Check if user exists and password matches
            if not user or not self.verify_password(password, user["password"]):
                # Record failed attempt
                if ip_address:
                    self._record_login_attempt(
                        email_or_username,
                        ip_address,
                        success=False
                    )
                
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials"
                )
            
            # Check if user is active
            if not user.get("active", True):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User account is disabled"
                )
            
            # Update last login time
            self.user_collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"last_login": datetime.utcnow()}}
            )
            
            # Record successful login
            if ip_address:
                self._record_login_attempt(
                    email_or_username,
                    ip_address,
                    success=True
                )
            
            # Remove password from returned user
            user.pop("password", None)
            
            # Convert ObjectId to string
            user["_id"] = str(user["_id"])
            
            return user
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error authenticating user: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error authenticating user"
            )
    
    def _check_login_attempts(self, email_or_username: str, ip_address: str) -> None:
        """
        Check for too many login attempts
        
        Args:
            email_or_username: User email or username
            ip_address: Client IP address
            
        Raises:
            HTTPException: If too many login attempts
        """
        # Get current time
        current_time = datetime.utcnow()
        one_hour_ago = current_time - timedelta(hours=1)
        
        # Count failed attempts for IP address
        ip_attempts = self.login_attempts_collection.count_documents({
            "ip_address": ip_address,
            "timestamp": {"$gte": one_hour_ago},
            "success": False
        })
        
        # Count failed attempts for email/username
        email_attempts = self.login_attempts_collection.count_documents({
            "email": email_or_username,
            "timestamp": {"$gte": one_hour_ago},
            "success": False
        })
        
        # Check limits
        if ip_attempts >= 10 or email_attempts >= 5:
            # Calculate lockout time
            lockout_minutes = min(30, max(5, ip_attempts // 2))
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many login attempts. Please try again in {lockout_minutes} minutes."
            )
    
    def _record_login_attempt(
        self,
        email_or_username: str,
        ip_address: str,
        success: bool
    ) -> None:
        """
        Record a login attempt
        
        Args:
            email_or_username: User email or username
            ip_address: Client IP address
            success: Whether the login was successful
        """
        try:
            # Create login attempt record
            login_attempt = {
                "email": email_or_username,
                "ip_address": ip_address,
                "timestamp": datetime.utcnow(),
                "success": success
            }
            
            # Insert record
            self.login_attempts_collection.insert_one(login_attempt)
            
        except Exception as e:
            logger.error(f"Error recording login attempt: {str(e)}")
    
    def create_password_reset_token(self, email: str) -> str:
        """
        Create a password reset token
        
        Args:
            email: User email
            
        Returns:
            Password reset token
            
        Raises:
            HTTPException: If user not found
        """
        try:
            # Normalize email
            email = email.lower().strip()
            
            # Find user
            user = self.user_collection.find_one({"email": email})
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            # Calculate token expiration
            current_time = datetime.utcnow()
            expires = current_time + timedelta(minutes=self.password_reset_expire_minutes)
            
            # Create token data
            token_data = {
                "sub": str(user["_id"]),
                "email": email,
                "exp": expires,
                "iat": current_time,
                "type": "password_reset"
            }
            
            # Generate token
            token = jwt.encode(
                token_data,
                self.secret_key,
                algorithm="HS256"
            )
            
            # Store reset token in database
            self.user_collection.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {
                        "reset_token": hashlib.sha256(token.encode()).hexdigest(),
                        "reset_token_expires": expires
                    }
                }
            )
            
            return token
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating password reset token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error creating password reset token"
            )
    
    def reset_password(self, token: str, new_password: str) -> bool:
        """
        Reset a user's password using a reset token
        
        Args:
            token: Password reset token
            new_password: New password
            
        Returns:
            True if password was reset, False otherwise
            
        Raises:
            HTTPException: If token is invalid or expired
        """
        try:
            # Decode token
            try:
                payload = jwt.decode(
                    token,
                    self.secret_key,
                    algorithms=["HS256"]
                )
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
            
            # Check token type
            if payload.get("type") != "password_reset":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type"
                )
            
            # Get user ID and email
            user_id = payload.get("sub")
            email = payload.get("email")
            
            # Calculate token hash
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            
            # Find user by ID and verify token
            user = self.user_collection.find_one({
                "_id": user_id,
                "email": email,
                "reset_token": token_hash,
                "reset_token_expires": {"$gt": datetime.utcnow()}
            })
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token"
                )
            
            # Validate password strength
            is_valid, error_message = self.validate_password_strength(new_password)
            
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_message
                )
            
            # Hash new password
            hashed_password = self.hash_password(new_password)
            
            # Update user password and clear reset token
            self.user_collection.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {"password": hashed_password},
                    "$unset": {"reset_token": "", "reset_token_expires": ""}
                }
            )
            
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error resetting password: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error resetting password"
            )
    
    def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str
    ) -> bool:
        """
        Change a user's password
        
        Args:
            user_id: User ID
            current_password: Current password
            new_password: New password
            
        Returns:
            True if password was changed, False otherwise
            
        Raises:
            HTTPException: If current password is incorrect
        """
        try:
            # Find user
            user = self.user_collection.find_one({"_id": user_id})
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            # Verify current password
            if not self.verify_password(current_password, user["password"]):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Current password is incorrect"
                )
            
            # Validate new password strength
            is_valid, error_message = self.validate_password_strength(new_password)
            
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_message
                )
            
            # Hash new password
            hashed_password = self.hash_password(new_password)
            
            # Update user password
            self.user_collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"password": hashed_password}}
            )
            
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error changing password: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error changing password"
            )
    
    def update_user_profile(
        self,
        user_id: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update a user's profile
        
        Args:
            user_id: User ID
            data: Profile data to update
            
        Returns:
            Updated user profile
            
        Raises:
            HTTPException: If update fails
        """
        try:
            # Create update data
            update_data = {}
            
            # Check for unique fields
            if "email" in data:
                new_email = data["email"].lower().strip()
                
                # Check if email already exists
                existing_user = self.user_collection.find_one({
                    "email": new_email,
                    "_id": {"$ne": user_id}
                })
                
                if existing_user:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email already registered"
                    )
                
                update_data["email"] = new_email
            
            if "username" in data:
                new_username = data["username"].lower().strip()
                
                # Check if username already exists
                existing_user = self.user_collection.find_one({
                    "username": new_username,
                    "_id": {"$ne": user_id}
                })
                
                if existing_user:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Username already taken"
                    )
                
                update_data["username"] = new_username
            
            # Add other fields
            for field in ["full_name", "settings"]:
                if field in data:
                    update_data[field] = data[field]
            
            # Update user
            if update_data:
                self.user_collection.update_one(
                    {"_id": user_id},
                    {"$set": update_data}
                )
            
            # Get updated user
            updated_user = self.user_collection.find_one({"_id": user_id})
            
            if not updated_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            # Remove password from returned user
            updated_user.pop("password", None)
            
            # Convert ObjectId to string
            updated_user["_id"] = str(updated_user["_id"])
            
            return updated_user
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating user profile: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error updating user profile"
            )
    
    def deactivate_user(self, user_id: str) -> bool:
        """
        Deactivate a user account
        
        Args:
            user_id: User ID
            
        Returns:
            True if user was deactivated, False otherwise
        """
        try:
            # Update user
            result = self.user_collection.update_one(
                {"_id": user_id},
                {"$set": {"active": False}}
            )
            
            # Revoke all sessions
            session_manager.revoke_all_user_sessions(user_id)
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Error deactivating user: {str(e)}")
            return False
    
    def reactivate_user(self, user_id: str) -> bool:
        """
        Reactivate a user account
        
        Args:
            user_id: User ID
            
        Returns:
            True if user was reactivated, False otherwise
        """
        try:
            # Update user
            result = self.user_collection.update_one(
                {"_id": user_id},
                {"$set": {"active": True}}
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Error reactivating user: {str(e)}")
            return False

# Create singleton instance
auth_service = AuthService()