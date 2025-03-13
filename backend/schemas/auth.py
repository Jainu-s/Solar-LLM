from typing import Dict, Any, Optional, List
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field

class UserAuth(BaseModel):
    """User authentication model"""
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., description="User password")

class UserRegister(BaseModel):
    """User registration model"""
    email: EmailStr = Field(..., description="User email")
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    password: str = Field(..., min_length=8, description="Password")
    full_name: Optional[str] = Field(default=None, description="User's full name")

class UserLogin(BaseModel):
    """User login model"""
    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="Password")
    remember_me: bool = Field(default=False, description="Remember login")

class TokenResponse(BaseModel):
    """Token response model"""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(..., description="Token type (Bearer)")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    user_id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    session_id: str = Field(..., description="Session ID")

class RefreshRequest(BaseModel):
    """Token refresh request model"""
    refresh_token: str = Field(..., description="JWT refresh token")

class PasswordResetRequest(BaseModel):
    """Password reset request model"""
    email: EmailStr = Field(..., description="User email")

class PasswordResetConfirm(BaseModel):
    """Password reset confirmation model"""
    token: str = Field(..., description="Password reset token")
    password: str = Field(..., min_length=8, description="New password")

class PasswordChangeRequest(BaseModel):
    """Password change request model"""
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, description="New password")

class Session(BaseModel):
    """User session model"""
    session_id: str = Field(..., description="Session ID")
    user_id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    created_at: datetime = Field(..., description="Session creation timestamp")
    expires_at: datetime = Field(..., description="Session expiration timestamp")
    last_activity: datetime = Field(..., description="Last activity timestamp")
    ip_address: Optional[str] = Field(default=None, description="Client IP address")
    user_agent: Optional[str] = Field(default=None, description="Client user agent")

class ApiKeyRequest(BaseModel):
    """API key request model"""
    name: str = Field(..., description="API key name")
    expiry_days: int = Field(default=365, description="Days until expiration")

class ApiKey(BaseModel):
    """API key model"""
    id: str = Field(..., description="API key ID")
    name: str = Field(..., description="API key name")
    user_id: str = Field(..., description="User ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    expires_at: datetime = Field(..., description="Expiration timestamp")
    last_used: Optional[datetime] = Field(default=None, description="Last used timestamp")