"""
UserService para gerenciar usuários multi-tenant
- Criação de usuários
- Autenticação
- Busca de usuários
- Gerencio de roles
"""
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import TenantUser, TenantAccount
from src.auth import password_hasher


class UserService:
    """Serviço de gerencimento de usuários multi-tenant"""

    @staticmethod
    async def authenticate_user(
        session: AsyncSession,
        email: str,
        password: str,
        tenant_id: int,
    ) -> Optional[TenantUser]:
        """
        Autentica um usuário verificando email, senha e tenant

        Args:
            session: Sessão do banco de dados
            email: Email do usuário
            password: Senha em texto plano
            tenant_id: ID do tenant (OAB)

        Returns:
            Usuário autenticado ou None se falhar
        """
        try:
            # Buscar usuário por email e tenant
            query = select(TenantUser).where(
                (TenantUser.email == email) & (TenantUser.tenant_id == tenant_id)
            )
            result = await session.execute(query)
            user = result.scalar_one_or_none()

            if not user or not user.ativo:
                return None

            # Verificar senha
            if not password_hasher.verify_password(password, user.senha_hash):
                return None

            return user

        except Exception:
            return None

    @staticmethod
    async def create_user(
        session: AsyncSession,
        email: str,
        password: str,
        name: str,
        tenant_id: int,
        role: str = "user",
    ) -> TenantUser:
        """
        Cria um novo usuário no tenant

        Args:
            session: Sessão do banco de dados
            email: Email do usuário
            password: Senha em texto plano
            name: Nome completo
            tenant_id: ID do tenant (OAB)
            role: Role do usuário (user, admin, viewer)

        Returns:
            Usuário criado

        Raises:
            ValueError: Se o email já existe no tenant ou se os dados forem inválidos
        """
        # Validar dados
        if not email or "@" not in email:
            raise ValueError("Email inválido")

        if not name or len(name.strip()) < 3:
            raise ValueError("Nome deve ter no mínimo 3 caracteres")

        if not password or len(password) < 6:
            raise ValueError("Senha deve ter no mínimo 6 caracteres")

        if role not in ["user", "admin", "viewer"]:
            raise ValueError(f"Role inválido: {role}")

        # Verificar se email já existe no tenant
        query = select(TenantUser).where(
            (TenantUser.email == email) & (TenantUser.tenant_id == tenant_id)
        )
        result = await session.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            raise ValueError(f"Email {email} já existe neste tenant")

        # Hash da senha
        hashed_password = password_hasher.hash_password(password)

        # Criar usuário
        user = TenantUser(
            tenant_id=tenant_id,
            email=email,
            senha_hash=hashed_password,
            nome=name,
            role=role,
            ativo=True,
        )

        session.add(user)
        await session.flush()  # Flush para obter o ID

        return user

    @staticmethod
    async def get_user_by_id(
        session: AsyncSession,
        user_id: int,
        tenant_id: int,
    ) -> Optional[TenantUser]:
        """
        Busca um usuário por ID (com verificação de tenant)

        Args:
            session: Sessão do banco de dados
            user_id: ID do usuário
            tenant_id: ID do tenant

        Returns:
            Usuário encontrado ou None
        """
        query = select(TenantUser).where(
            (TenantUser.id == user_id) & (TenantUser.tenant_id == tenant_id)
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_email(
        session: AsyncSession,
        email: str,
        tenant_id: int,
    ) -> Optional[TenantUser]:
        """
        Busca um usuário por email (com verificação de tenant)

        Args:
            session: Sessão do banco de dados
            email: Email do usuário
            tenant_id: ID do tenant

        Returns:
            Usuário encontrado ou None
        """
        query = select(TenantUser).where(
            (TenantUser.email == email) & (TenantUser.tenant_id == tenant_id)
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_users_by_tenant(
        session: AsyncSession,
        tenant_id: int,
        skip: int = 0,
        limit: int = 10,
    ) -> tuple[list[TenantUser], int]:
        """
        Lista usuários de um tenant

        Args:
            session: Sessão do banco de dados
            tenant_id: ID do tenant
            skip: Quantidade a pular
            limit: Quantidade máxima a retornar

        Returns:
            Tupla (lista de usuários, total de usuários)
        """
        # Contar total
        count_query = select(TenantUser).where(TenantUser.tenant_id == tenant_id)
        count_result = await session.execute(count_query)
        total = len(count_result.scalars().all())

        # Buscar com paginação
        query = (
            select(TenantUser)
            .where(TenantUser.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(query)
        users = result.scalars().all()

        return users, total

    @staticmethod
    async def update_user_role(
        session: AsyncSession,
        user_id: int,
        tenant_id: int,
        new_role: str,
    ) -> TenantUser:
        """
        Atualiza a role de um usuário

        Args:
            session: Sessão do banco de dados
            user_id: ID do usuário
            tenant_id: ID do tenant
            new_role: Nova role (user, admin, viewer)

        Returns:
            Usuário atualizado

        Raises:
            ValueError: Se role for inválido ou usuário não encontrado
        """
        if new_role not in ["user", "admin", "viewer"]:
            raise ValueError(f"Role inválido: {new_role}")

        user = await UserService.get_user_by_id(session, user_id, tenant_id)

        if not user:
            raise ValueError("Usuário não encontrado")

        user.role = new_role
        await session.flush()

        return user

    @staticmethod
    async def deactivate_user(
        session: AsyncSession,
        user_id: int,
        tenant_id: int,
    ) -> TenantUser:
        """
        Desativa um usuário

        Args:
            session: Sessão do banco de dados
            user_id: ID do usuário
            tenant_id: ID do tenant

        Returns:
            Usuário desativado

        Raises:
            ValueError: Se usuário não encontrado
        """
        user = await UserService.get_user_by_id(session, user_id, tenant_id)

        if not user:
            raise ValueError("Usuário não encontrado")

        user.ativo = False
        await session.flush()

        return user

    @staticmethod
    async def change_password(
        session: AsyncSession,
        user_id: int,
        tenant_id: int,
        old_password: str,
        new_password: str,
    ) -> bool:
        """
        Altera a senha de um usuário

        Args:
            session: Sessão do banco de dados
            user_id: ID do usuário
            tenant_id: ID do tenant
            old_password: Senha antiga (para verificação)
            new_password: Nova senha

        Returns:
            True se bem-sucedido

        Raises:
            ValueError: Se a senha antiga estiver incorreta ou new_password for inválida
        """
        user = await UserService.get_user_by_id(session, user_id, tenant_id)

        if not user:
            raise ValueError("Usuário não encontrado")

        # Verificar senha antiga
        if not password_hasher.verify_password(old_password, user.senha_hash):
            raise ValueError("Senha antiga incorreta")

        # Validar nova senha
        if not new_password or len(new_password) < 6:
            raise ValueError("Nova senha deve ter no mínimo 6 caracteres")

        # Hash da nova senha
        user.senha_hash = password_hasher.hash_password(new_password)
        await session.flush()

        return True
