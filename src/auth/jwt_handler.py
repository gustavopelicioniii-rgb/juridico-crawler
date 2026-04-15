"""
JWT Handler para Multi-Tenant Authentication
- Geração de Access Tokens (30 minutos)
- Geração de Refresh Tokens (7 dias)
- Hashing de senhas com bcrypt
- Validação de tokens
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import jwt
from bcrypt import hashpw, gensalt, checkpw
from pydantic import BaseModel

from src.config import settings


# ============================================================================
# CONSTANTS
# ============================================================================

# Expiração dos tokens
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7
ALGORITHM = "HS256"

# Erro de validação
class TokenError(Exception):
    """Erro ao validar token JWT"""
    pass


# ============================================================================
# SCHEMAS
# ============================================================================

class TokenResponse(BaseModel):
    """Response ao fazer login"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos
    user_id: int
    tenant_id: int
    email: str
    role: str


class TokenPayload(BaseModel):
    """Payload decodificado do JWT"""
    user_id: int
    tenant_id: int
    email: str
    role: Optional[str] = None  # Refresh tokens não têm role
    exp: datetime
    iat: datetime
    type: str  # "access" ou "refresh"


# ============================================================================
# PASSWORD HASHING
# ============================================================================

class PasswordHasher:
    """Hashing de senhas com bcrypt"""

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash de uma senha usando bcrypt

        Args:
            password: Senha em texto plano

        Returns:
            Hash bcrypt codificado em UTF-8
        """
        if not password or len(password) < 6:
            raise ValueError("Senha deve ter no mínimo 6 caracteres")

        salt = gensalt(rounds=12)
        hashed = hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """
        Verifica se uma senha corresponde ao hash

        Args:
            password: Senha em texto plano
            hashed: Hash bcrypt

        Returns:
            True se correspondem, False caso contrário
        """
        try:
            return checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False


# ============================================================================
# JWT HANDLER
# ============================================================================

class JWTHandler:
    """Gerenciador de JWT para multi-tenant"""

    def __init__(self, secret_key: str = None, algorithm: str = ALGORITHM):
        """
        Inicializa o JWTHandler

        Args:
            secret_key: Chave secreta para assinar JWT (default: settings.api_secret_key)
            algorithm: Algoritmo de assinatura (default: HS256)
        """
        self.secret_key = secret_key or settings.api_secret_key
        self.algorithm = algorithm

        if not self.secret_key or self.secret_key == "change-me-in-production":
            raise ValueError(
                "⚠️  AVISO: API_SECRET_KEY não está configurada corretamente!\n"
                "   Defina a variável de ambiente: export API_SECRET_KEY=seu-valor-secreto-muito-seguro"
            )

    def create_access_token(
        self,
        user_id: int,
        tenant_id: int,
        email: str,
        role: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """
        Cria um Access Token (30 minutos por padrão)

        Args:
            user_id: ID do usuário
            tenant_id: ID do tenant (OAB)
            email: Email do usuário
            role: Role do usuário (user, admin, viewer)
            expires_delta: Tempo até expiração (default: 30 minutos)

        Returns:
            Token JWT assinado
        """
        if expires_delta is None:
            expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

        return self._create_token(
            data={
                "user_id": user_id,
                "tenant_id": tenant_id,
                "email": email,
                "role": role,
                "type": "access",
            },
            expires_delta=expires_delta,
        )

    def create_refresh_token(
        self,
        user_id: int,
        tenant_id: int,
        email: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """
        Cria um Refresh Token (7 dias por padrão)

        Args:
            user_id: ID do usuário
            tenant_id: ID do tenant (OAB)
            email: Email do usuário
            expires_delta: Tempo até expiração (default: 7 dias)

        Returns:
            Token JWT assinado
        """
        if expires_delta is None:
            expires_delta = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

        return self._create_token(
            data={
                "user_id": user_id,
                "tenant_id": tenant_id,
                "email": email,
                "type": "refresh",
            },
            expires_delta=expires_delta,
        )

    def _create_token(self, data: Dict[str, Any], expires_delta: timedelta) -> str:
        """
        Cria um JWT assinado

        Args:
            data: Dados a incluir no token
            expires_delta: Tempo até expiração

        Returns:
            Token JWT
        """
        now = datetime.now(timezone.utc)
        expires = now + expires_delta

        payload = {
            **data,
            "iat": now,
            "exp": expires,
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token

    def verify_token(self, token: str, token_type: str = "access") -> TokenPayload:
        """
        Verifica e decodifica um JWT

        Args:
            token: Token JWT
            token_type: Tipo esperado ("access" ou "refresh")

        Returns:
            Payload decodificado do token

        Raises:
            TokenError: Se o token for inválido ou expirado
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            # Validar tipo de token
            if payload.get("type") != token_type:
                raise TokenError(
                    f"Tipo de token inválido. Esperado: {token_type}, Recebido: {payload.get('type')}"
                )

            # Validar campos obrigatórios
            required_fields = ["user_id", "tenant_id", "email"]
            for field in required_fields:
                if field not in payload:
                    raise TokenError(f"Campo obrigatório ausente: {field}")

            return TokenPayload(**payload)

        except jwt.ExpiredSignatureError:
            raise TokenError("Token expirado")
        except jwt.InvalidTokenError as e:
            raise TokenError(f"Token inválido: {str(e)}")
        except Exception as e:
            raise TokenError(f"Erro ao decodificar token: {str(e)}")

    def create_tokens_pair(
        self,
        user_id: int,
        tenant_id: int,
        email: str,
        role: str,
    ) -> TokenResponse:
        """
        Cria um par de Access e Refresh tokens

        Args:
            user_id: ID do usuário
            tenant_id: ID do tenant (OAB)
            email: Email do usuário
            role: Role do usuário

        Returns:
            TokenResponse com ambos os tokens
        """
        access_token = self.create_access_token(user_id, tenant_id, email, role)
        refresh_token = self.create_refresh_token(user_id, tenant_id, email)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # em segundos
            user_id=user_id,
            tenant_id=tenant_id,
            email=email,
            role=role,
        )

    def refresh_access_token(self, refresh_token: str) -> str:
        """
        Gera um novo Access Token usando um Refresh Token

        Args:
            refresh_token: Refresh Token válido

        Returns:
            Novo Access Token

        Raises:
            TokenError: Se o refresh token for inválido
        """
        try:
            payload = self.verify_token(refresh_token, token_type="refresh")

            # Gerar novo access token
            return self.create_access_token(
                user_id=payload.user_id,
                tenant_id=payload.tenant_id,
                email=payload.email,
                role=getattr(payload, "role", "user"),  # Refresh não tem role, usar default
            )

        except TokenError:
            raise


# ============================================================================
# INSTÂNCIA GLOBAL
# ============================================================================

jwt_handler = JWTHandler()
password_hasher = PasswordHasher()
