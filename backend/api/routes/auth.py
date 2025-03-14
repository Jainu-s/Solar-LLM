from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks, Response, Cookie
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field

from backend.utils.auth import auth_service
from backend.utils.session import session_manager
from backend.utils.analytics import analytics_service
from backend.utils.logging import setup_logger
from backend.config import settings

logger = setup_logger("auth_routes")

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    responses={404: {"description": "Not found"}},
)

class UserCreate(BaseModel):
    """User registration schema"""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    """User login schema"""
    username: str
    password: str
    remember_me: bool = False

class TokenResponse(BaseModel):
    """Token response schema"""
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    user_id: str
    username: str

class RefreshTokenRequest(BaseModel):
    """Refresh token request schema"""
    refresh_token: str

class PasswordResetRequest(BaseModel):
    """Password reset request schema"""
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    """Password reset confirmation schema"""
    token: str
    password: str = Field(..., min_length=8)

class PasswordChangeRequest(BaseModel):
    """Password change request schema"""
    current_password: str
    new_password: str = Field(..., min_length=8)

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    user: UserCreate,
    background_tasks: BackgroundTasks,
    request: Request
):
    """
    Register a new user
    """
    try:
        logger.info(f"Registration attempt for username: {user.username}, email: {user.email}")
        
        # Register user
        created_user = auth_service.register_user(
            user.email,
            user.username,
            user.password,
            user.full_name
        )
        
        logger.info(f"User registered successfully: {user.username}, {user.email}")
        
        # Track registration
        background_tasks.add_task(
            analytics_service.track_event,
            "user_registration",
            {
                "user_id": created_user["_id"],
                "email": user.email,
                "username": user.username,
                "ip_address": request.client.host,
                "user_agent": request.headers.get("user-agent")
            }
        )
        
        return created_user
        
    except HTTPException as he:
        logger.warning(f"Registration failed: {str(he.detail)} for {user.username}, {user.email}")
        raise
    except Exception as e:
        logger.error(f"Error registering user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error registering user: {str(e)}"
        )

@router.post("/token", response_model=TokenResponse)
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    try:
        logger.info(f"Login attempt (OAuth2) for username: {form_data.username}")
        
        # Authenticate user
        user = auth_service.authenticate_user(
            form_data.username,
            form_data.password,
            ip_address=request.client.host
        )
        
        # Create session
        session = session_manager.create_session(
            user["_id"],
            user["username"],
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent")
        )
        
        # Set session cookie if using form login
        expires = None
        if getattr(form_data, "remember_me", False):
            # Set long-lived cookie for "remember me"
            expires = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        
        # Set cookie for web clients
        response.set_cookie(
            key="session",
            value=session["access_token"],  # Store just the token, not the whole object
            httponly=True,
            secure=not settings.DEBUG,  # Secure in production
            samesite="lax",
            max_age=expires
        )
        
        logger.info(f"Login successful for username: {form_data.username}")
        
        # Track login
        background_tasks.add_task(
            analytics_service.track_event,
            "user_login",
            {
                "user_id": user["_id"],
                "username": user["username"],
                "ip_address": request.client.host,
                "user_agent": request.headers.get("user-agent"),
                "session_id": session["session_id"]
            }
        )
        
        return session
        
    except HTTPException as he:
        logger.warning(f"Login failed: {str(he.detail)} for {form_data.username}")
        raise
    except Exception as e:
        logger.error(f"Error during login: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during login: {str(e)}"
        )

@router.post("/login", response_model=TokenResponse)
async def client_login(
    request: Request,
    response: Response,
    login_data: UserLogin,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Client login for web/mobile apps
    """
    try:
        logger.info(f"Login attempt (client) for username: {login_data.username}")
        
        # Authenticate user
        user = auth_service.authenticate_user(
            login_data.username,
            login_data.password,
            ip_address=request.client.host
        )
        
        # Create session
        session = session_manager.create_session(
            user["_id"],
            user["username"],
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent")
        )
        
        # Set cookie for web clients
        expires = None
        if login_data.remember_me:
            # Set long-lived cookie for "remember me"
            expires = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        
        # Set the access token directly in the cookie (not as JSON)
        response.set_cookie(
            key="session",
            value=session["access_token"],
            httponly=True,
            secure=not settings.DEBUG,  # Secure in production
            samesite="lax",
            max_age=expires
        )
        
        # Log the token details for debugging
        logger.info(f"Login successful - Token type: {session['token_type']}")
        logger.info(f"Login successful - Cookie set with access token")
        
        # Track login
        background_tasks.add_task(
            analytics_service.track_event,
            "user_login",
            {
                "user_id": user["_id"],
                "username": user["username"],
                "ip_address": request.client.host,
                "user_agent": request.headers.get("user-agent"),
                "session_id": session["session_id"]
            }
        )
        
        return session
        
    except HTTPException as he:
        logger.warning(f"Login failed: {str(he.detail)} for {login_data.username}")
        raise
    except Exception as e:
        logger.error(f"Error during login: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during login: {str(e)}"
        )

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request_data: RefreshTokenRequest,
    request: Request,
    response: Response
):
    """
    Refresh access token
    """
    try:
        logger.debug(f"Token refresh request received")
        
        # Refresh token
        token_data = session_manager.refresh_access_token(
            request_data.refresh_token,
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent")
        )
        
        # Update session cookie
        response.set_cookie(
            key="session",
            value=token_data["access_token"],
            httponly=True,
            secure=not settings.DEBUG,  # Secure in production
            samesite="lax"
        )
        
        logger.debug(f"Token refreshed successfully for user: {token_data['username']}")
        
        return token_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error refreshing token: {str(e)}"
        )

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session_id: Optional[str] = None,
    session: Optional[str] = Cookie(None)
):
    """
    Logout and invalidate session
    """
    try:
        logger.debug(f"Logout request received, session_id: {session_id}")
        
        # Revoke session if session_id provided
        if session_id:
            logger.debug(f"Revoking session by ID: {session_id}")
            session_manager.revoke_session(session_id)
        
        # If not, try to get session from cookie
        elif session:
            try:
                # Decode token to get session ID
                logger.debug("Attempting to revoke session from cookie")
                payload = session_manager.validate_token(session)
                if payload and "session_id" in payload:
                    session_id = payload["session_id"]
                    logger.debug(f"Revoking session from cookie: {session_id}")
                    session_manager.revoke_session(session_id)
            except Exception as e:
                logger.error(f"Error decoding session cookie during logout: {str(e)}")
        
        # Clear session cookie
        response.delete_cookie(
            key="session",
            secure=not settings.DEBUG,
            httponly=True,
            samesite="lax"
        )
        
        logger.debug("Logout completed successfully")
        
    except Exception as e:
        logger.error(f"Error during logout: {str(e)}")
        # Continue with logout even if there's an error

@router.post("/password-reset/request")
async def request_password_reset(
    request_data: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    request: Request
):
    """
    Request a password reset
    """
    try:
        logger.info(f"Password reset requested for email: {request_data.email}")
        
        # Create password reset token
        token = auth_service.create_password_reset_token(request_data.email)
        
        # In a real application, send this token via email
        # For now, just return it (not secure for production)
        
        # Track password reset request
        background_tasks.add_task(
            analytics_service.track_event,
            "password_reset_request",
            {
                "email": request_data.email,
                "ip_address": request.client.host,
                "user_agent": request.headers.get("user-agent")
            }
        )
        
        if settings.DEBUG:
            # Return token directly in debug mode
            logger.debug(f"Password reset token generated (DEBUG): {token}")
            return {"reset_token": token}
        else:
            # In production, don't return the token
            logger.info(f"Password reset token generated (would be emailed in production)")
            return {"message": "Password reset instructions sent if email exists"}
        
    except HTTPException as he:
        # Don't reveal if email exists
        logger.warning(f"Password reset request failed: {str(he.detail)}")
        if settings.DEBUG:
            raise
        return {"message": "Password reset instructions sent if email exists"}
    except Exception as e:
        logger.error(f"Error requesting password reset: {str(e)}")
        return {"message": "Password reset instructions sent if email exists"}

@router.post("/password-reset/confirm")
async def confirm_password_reset(
    reset_data: PasswordResetConfirm,
    background_tasks: BackgroundTasks,
    request: Request
):
    """
    Confirm password reset with token
    """
    try:
        logger.info("Password reset confirmation attempt")
        
        # Reset password
        auth_service.reset_password(reset_data.token, reset_data.password)
        
        logger.info("Password reset successful")
        
        # Track password reset
        background_tasks.add_task(
            analytics_service.track_event,
            "password_reset_confirm",
            {
                "ip_address": request.client.host,
                "user_agent": request.headers.get("user-agent")
            }
        )
        
        return {"message": "Password reset successful"}
        
    except HTTPException as he:
        logger.warning(f"Password reset confirmation failed: {str(he.detail)}")
        raise
    except Exception as e:
        logger.error(f"Error confirming password reset: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error confirming password reset: {str(e)}"
        )

@router.post("/password-change")
async def change_password(
    password_data: PasswordChangeRequest,
    request: Request,
    current_user = Depends(session_manager.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Change user password
    """
    try:
        user_id = current_user["_id"]
        logger.info(f"Password change attempt for user: {current_user.get('username', user_id)}")
        
        # Change password
        auth_service.change_password(
            user_id,
            password_data.current_password,
            password_data.new_password
        )
        
        logger.info(f"Password changed successfully for user: {current_user.get('username', user_id)}")
        
        # Track password change
        background_tasks.add_task(
            analytics_service.track_event,
            "password_change",
            {
                "user_id": user_id,
                "ip_address": request.client.host,
                "user_agent": request.headers.get("user-agent")
            }
        )
        
        return {"message": "Password changed successfully"}
        
    except HTTPException as he:
        logger.warning(f"Password change failed: {str(he.detail)}")
        raise
    except Exception as e:
        logger.error(f"Error changing password: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error changing password: {str(e)}"
        )

@router.get("/me")
async def get_current_user(
    request: Request,
    session: Optional[str] = Cookie(None),
    current_user = Depends(session_manager.get_current_user)
):
    """
    Get current user info
    """
    # Log detailed information about the request
    logger.info(f"GET /me request received")
    logger.info(f"Auth header: {request.headers.get('authorization')}")
    logger.info(f"Session cookie: {session}")
    
    if current_user:
        logger.info(f"User authenticated: {current_user.get('username', current_user.get('_id'))}")
    else:
        logger.warning("User not authenticated")
    
    return current_user

@router.get("/sessions")
async def get_user_sessions(
    current_user = Depends(session_manager.get_current_user)
):
    """
    Get all active sessions for the current user
    """
    try:
        user_id = current_user["_id"]
        logger.debug(f"Sessions requested for user: {current_user.get('username', user_id)}")
        
        # Get sessions
        sessions = session_manager.get_user_sessions(user_id)
        
        return sessions
        
    except Exception as e:
        logger.error(f"Error getting user sessions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting user sessions: {str(e)}"
        )

@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: str,
    current_user = Depends(session_manager.get_current_user)
):
    """
    Revoke a specific session
    """
    try:
        user_id = current_user["_id"]
        logger.debug(f"Session revoke requested for session: {session_id} by user: {current_user.get('username', user_id)}")
        
        # Get session info
        sessions = session_manager.get_user_sessions(user_id)
        
        # Check if session belongs to user
        session_belongs_to_user = False
        for session in sessions:
            if session.get("session_id") == session_id:
                session_belongs_to_user = True
                break
        
        if not session_belongs_to_user:
            logger.warning(f"Unauthorized session revoke attempt: {session_id} by user: {current_user.get('username', user_id)}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Session not found or doesn't belong to user"
            )
        
        # Revoke session
        session_manager.revoke_session(session_id)
        logger.debug(f"Session revoked successfully: {session_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error revoking session: {str(e)}"
        )