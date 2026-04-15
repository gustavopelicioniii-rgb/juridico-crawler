"""
Schemas para endpoints de autenticação
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class LoginRequest(BaseModel):
    """Request para login"""
    email: EmailStr
    password: str = Field(..., min_length=6)
    tenant_numero_oab: str = Field(..., min_length=1, max_length=20)  # Ex: "361329SP"


class RefreshTokenRequest(BaseModel):
    """Request para refresh de token"""
    refresh_token: str


class CreateUserRequest(BaseModel):
    """Request para criar novo usuário"""
    email: EmailStr
    password: str = Field(..., min_length=6)
    name: str = Field(..., min_length=3)
    role: Optional[str] = "user"  # user, admin, viewer


class ChangePasswordRequest(BaseModel):
    """Request para mudar senha"""
    old_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=6)


class UserResponse(BaseModel):
    """Response com dados do usuário"""
    id: int
    email: str
    nome: str
    role: str
    ativo: bool
    tenant_id: int


class TokenResponse(BaseModel):
    """Response ao fazer login"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos
    user: UserResponse


class ErrorResponse(BaseModel):
    """Response de erro"""
    detail: str
    code: Optional[str] = None
