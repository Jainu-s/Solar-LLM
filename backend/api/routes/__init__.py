from fastapi import APIRouter
from backend.api.routes import auth, chat, files, admin

# Create main router
api_router = APIRouter()

# Include all route modules
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(files.router)
api_router.include_router(admin.router)