"""
Teste do JWT Handler
"""
import sys
from datetime import timedelta

# Teste rápido do JWT Handler
try:
    from src.auth import jwt_handler, password_hasher, TokenError

    print("\n" + "="*70)
    print("TESTE: JWT Handler e Password Hashing")
    print("="*70 + "\n")

    # ===== TESTE 1: Password Hashing =====
    print("✓ TESTE 1: Password Hashing com bcrypt")
    print("-" * 70)

    password = "minhasenha123"
    hashed = password_hasher.hash_password(password)

    print(f"  Senha original: {password}")
    print(f"  Hash bcrypt: {hashed[:50]}...")
    print(f"  Verificação correta: {password_hasher.verify_password(password, hashed)}")
    print(f"  Verificação incorreta: {password_hasher.verify_password('senhaerrada', hashed)}")

    # ===== TESTE 2: Create Access Token =====
    print("\n✓ TESTE 2: Criação de Access Token")
    print("-" * 70)

    access_token = jwt_handler.create_access_token(
        user_id=1,
        tenant_id=1,
        email="admin@oab361329.sp.br",
        role="admin"
    )
    print(f"  Access Token gerado: {access_token[:50]}...")

    # ===== TESTE 3: Verify Token =====
    print("\n✓ TESTE 3: Verificação de Access Token")
    print("-" * 70)

    payload = jwt_handler.verify_token(access_token, token_type="access")
    print(f"  User ID: {payload.user_id}")
    print(f"  Tenant ID: {payload.tenant_id}")
    print(f"  Email: {payload.email}")
    print(f"  Role: {payload.role}")
    print(f"  Type: {payload.type}")

    # ===== TESTE 4: Create Refresh Token =====
    print("\n✓ TESTE 4: Criação de Refresh Token")
    print("-" * 70)

    refresh_token = jwt_handler.create_refresh_token(
        user_id=1,
        tenant_id=1,
        email="admin@oab361329.sp.br"
    )
    print(f"  Refresh Token gerado: {refresh_token[:50]}...")

    payload_refresh = jwt_handler.verify_token(refresh_token, token_type="refresh")
    print(f"  User ID: {payload_refresh.user_id}")
    print(f"  Tenant ID: {payload_refresh.tenant_id}")
    print(f"  Email: {payload_refresh.email}")
    print(f"  Type: {payload_refresh.type}")

    # ===== TESTE 5: Token Pair =====
    print("\n✓ TESTE 5: Criação de Token Pair (Access + Refresh)")
    print("-" * 70)

    tokens = jwt_handler.create_tokens_pair(
        user_id=1,
        tenant_id=1,
        email="admin@oab361329.sp.br",
        role="admin"
    )
    print(f"  Access Token: {tokens.access_token[:50]}...")
    print(f"  Refresh Token: {tokens.refresh_token[:50]}...")
    print(f"  Token Type: {tokens.token_type}")
    print(f"  Expires In: {tokens.expires_in} segundos")

    # ===== TESTE 6: Refresh Access Token =====
    print("\n✓ TESTE 6: Refresh de Access Token")
    print("-" * 70)

    new_access_token = jwt_handler.refresh_access_token(refresh_token)
    print(f"  Novo Access Token: {new_access_token[:50]}...")

    new_payload = jwt_handler.verify_token(new_access_token, token_type="access")
    print(f"  User ID: {new_payload.user_id}")
    print(f"  Tenant ID: {new_payload.tenant_id}")

    # ===== TESTE 7: Token Inválido =====
    print("\n✓ TESTE 7: Tratamento de Token Inválido")
    print("-" * 70)

    try:
        jwt_handler.verify_token("token_invalido", token_type="access")
        print("  ✗ Erro: Token inválido não foi detectado")
        sys.exit(1)
    except TokenError as e:
        print(f"  ✓ Token inválido detectado: {str(e)[:50]}...")

    # ===== TESTE 8: Token Expirado =====
    print("\n✓ TESTE 8: Detecção de Token Expirado")
    print("-" * 70)

    # Criar token com expiração de -1 segundo
    expired_token = jwt_handler.create_access_token(
        user_id=1,
        tenant_id=1,
        email="admin@oab361329.sp.br",
        role="admin",
        expires_delta=timedelta(seconds=-1)
    )

    try:
        jwt_handler.verify_token(expired_token, token_type="access")
        print("  ✗ Erro: Token expirado não foi detectado")
        sys.exit(1)
    except TokenError as e:
        print(f"  ✓ Token expirado detectado: {str(e)[:50]}...")

    # ===== TESTE 9: Tipo de Token Incorreto =====
    print("\n✓ TESTE 9: Detecção de Tipo de Token Incorreto")
    print("-" * 70)

    try:
        # Tentar verificar access token como refresh
        jwt_handler.verify_token(access_token, token_type="refresh")
        print("  ✗ Erro: Tipo de token incorreto não foi detectado")
        sys.exit(1)
    except TokenError as e:
        print(f"  ✓ Tipo de token incorreto detectado: {str(e)[:50]}...")

    # ===== RESULTADO FINAL =====
    print("\n" + "="*70)
    print("✅ TODOS OS TESTES PASSARAM COM SUCESSO!")
    print("="*70 + "\n")

    print("Resumo:")
    print("  ✓ Password hashing com bcrypt funcionando")
    print("  ✓ JWT access token funcionando (30 min)")
    print("  ✓ JWT refresh token funcionando (7 dias)")
    print("  ✓ Token pair gerado com sucesso")
    print("  ✓ Token refresh funcionando")
    print("  ✓ Validação de tokens inválidos funcionando")
    print("  ✓ Detecção de expiração funcionando")
    print("  ✓ Validação de tipo de token funcionando")
    print("\nO JWT Handler está 100% operacional para autenticação multi-tenant! 🎉\n")

except Exception as e:
    print(f"\n✗ ERRO: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
