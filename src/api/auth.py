"""
API Routes para Autenticação Multi-Tenant
- POST /api/auth/login - Autentica usuário e retorna tokens
- POST /api/auth/refresh - Refresh de access token
- POST /api/auth/register - Cria novo usuário
- GET /api/auth/me - Dados do usuário autenticado
- POST /api/auth/change-password - Altera senha
"""
import structlog
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.rate_limit import limiter

logger = structlog.get_logger(__name__)

from src.auth import jwt_handler, password_hasher, TokenError
from src.database.connection import get_db
from src.database.models import TenantUser, TenantAccount
from src.schemas.auth_schemas import (
    LoginRequest,
    RefreshTokenRequest,
    CreateUserRequest,
    ChangePasswordRequest,
    TokenResponse,
    UserResponse,
)
from src.services.user_service import UserService
from sqlalchemy import select

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ============================================================================
# DEPENDENCY: Current User
# ============================================================================

async def get_current_user(
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    Extrai e valida o JWT token do header Authorization

    Returns:
        Dict com user_id, tenant_id, email, role
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header ausente",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Esperado: "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Formato de Authorization inválido. Use: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]

    try:
        payload = jwt_handler.verify_token(token, token_type="access")
        return {
            "user_id": payload.user_id,
            "tenant_id": payload.tenant_id,
            "email": payload.email,
            "role": payload.role or "user",
        }
    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def login(
    request: Request,
    payload: LoginRequest,
    session: AsyncSession = Depends(get_db),
):
    """Autentica um usuário e retorna access + refresh tokens."""
    try:
        # Buscar tenant por número OAB
        query = select(TenantAccount).where(
            TenantAccount.numero_oab == payload.tenant_numero_oab
        )
        result = await session.execute(query)
        tenant = result.scalar_one_or_none()

        if not tenant or tenant.status != "ativo":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tenant não encontrado ou inativo",
            )

        # Autenticar usuário
        user = await UserService.authenticate_user(
            session=session,
            email=payload.email,
            password=payload.password,
            tenant_id=tenant.id,
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email ou senha incorretos",
            )

        # Atualizar último login
        user.ultimo_login = datetime.now()
        await session.flush()

        # Gerar tokens
        tokens = jwt_handler.create_tokens_pair(
            user_id=user.id,
            tenant_id=tenant.id,
            email=user.email,
            role=user.role,
        )

        return TokenResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in=tokens.expires_in,
            user=UserResponse(
                id=user.id,
                email=user.email,
                nome=user.nome,
                role=user.role,
                ativo=user.ativo,
                tenant_id=tenant.id,
            ),
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Erro ao fazer login")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao processar login",
        )


@router.post("/refresh", response_model=dict, status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def refresh_token(request: Request, payload: RefreshTokenRequest):
    """Gera um novo access token usando o refresh token."""
    try:
        access_token = jwt_handler.refresh_access_token(payload.refresh_token)

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": 30 * 60,  # 30 minutos em segundos
        }

    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Refresh token inválido: {str(e)}",
        )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def register(
    request: Request,
    payload: CreateUserRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Cria um novo usuário no tenant (requer admin)."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem criar usuários",
        )

    try:
        user = await UserService.create_user(
            session=session,
            email=payload.email,
            password=payload.password,
            name=payload.name,
            tenant_id=current_user["tenant_id"],
            role=payload.role or "user",
        )

        await session.commit()

        return UserResponse(
            id=user.id,
            email=user.email,
            nome=user.nome,
            role=user.role,
            ativo=user.ativo,
            tenant_id=user.tenant_id,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception:
        await session.rollback()
        logger.exception("Erro ao criar usuário")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar usuário",
        )


@router.get("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Retorna dados do usuário autenticado

    Returns:
        UserResponse com dados do usuário
    """
    try:
        user = await UserService.get_user_by_id(
            session=session,
            user_id=current_user["user_id"],
            tenant_id=current_user["tenant_id"],
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado",
            )

        return UserResponse(
            id=user.id,
            email=user.email,
            nome=user.nome,
            role=user.role,
            ativo=user.ativo,
            tenant_id=user.tenant_id,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Erro ao buscar usuário")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao buscar usuário",
        )


@router.post("/change-password", response_model=dict, status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Altera a senha do usuário autenticado."""
    try:
        await UserService.change_password(
            session=session,
            user_id=current_user["user_id"],
            tenant_id=current_user["tenant_id"],
            old_password=payload.old_password,
            new_password=payload.new_password,
        )

        await session.commit()

        return {
            "status": "ok",
            "message": "Senha alterada com sucesso",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception:
        await session.rollback()
        logger.exception("Erro ao alterar senha")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao alterar senha",
        )
