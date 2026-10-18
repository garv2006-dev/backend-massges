from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.user import UserCreate, User, Token
from app.repositories.user import UserRepository
from app.security.password import verify_password, get_password_hash
from app.security.jwt import create_access_token
from app.core.deps import get_current_user, get_current_superuser
import uuid

router = APIRouter()

@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
async def register(user_create: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    user_repo = UserRepository(db)
    
    # Check if user already exists
    existing_user = await user_repo.get_by_email(user_create.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Hash password
    hashed_password = get_password_hash(user_create.password)
    
    # Create user
    user = await user_repo.create(user_create, hashed_password)
    return user

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Login with email and password."""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_email(form_data.username)
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    access_token = create_access_token(subject=str(user.id))
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "onboarding_completed": bool(getattr(user, "onboarding_completed", False)),
        "user": user,
    }

@router.get("/me", response_model=User)
async def get_current_user_info(current_user = Depends(get_current_user)):
    """Get current user information."""
    return current_user

@router.post("/complete-onboarding", response_model=User)
async def complete_onboarding(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark the current authenticated user's onboarding as completed."""
    current_user.onboarding_completed = True
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user

@router.post("/reset-onboarding", response_model=User)
async def reset_onboarding(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Reset the current authenticated user's onboarding status for testing."""
    current_user.onboarding_completed = False
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user
