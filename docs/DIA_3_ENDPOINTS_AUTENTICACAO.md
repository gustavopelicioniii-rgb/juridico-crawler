# 🔐 Dia 3: Endpoints de Autenticação + Middleware - IMPLEMENTAÇÃO

## 📊 Status

```
████████████████████ 100% CONCLUÍDO

Dia 3: Endpoints de Autenticação  ✅ COMPLETO
  ✓ POST /api/auth/login implementado
  ✓ POST /api/auth/refresh implementado
  ✓ POST /api/auth/register implementado
  ✓ GET /api/auth/me implementado
  ✓ POST /api/auth/change-password implementado
  ✓ get_current_user dependency criada
  ✓ Tratamento de erros 401/403 configurado
```

---

## 🎯 Endpoints Implementados

### 1️⃣ POST /api/auth/login

**Autentica um usuário e retorna tokens JWT**

**Request:**
```json
{
  "email": "admin@example.com",
  "password": "minhasenha123",
  "tenant_numero_oab": "361329SP"
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": 1,
    "email": "admin@example.com",
    "nome": "Admin User",
    "role": "admin",
    "ativo": true,
    "tenant_id": 1
  }
}
```

**Erros:**
- `401 UNAUTHORIZED` — Email/senha incorretos ou tenant inativo
- `500 INTERNAL_SERVER_ERROR` — Erro ao processar

**Lógica:**
1. Valida request (email, password, tenant_numero_oab)
2. Busca tenant por numero_oab
3. Valida se tenant está ativo
4. Autentica usuário (email + password + tenant_id)
5. Atualiza ultimo_login
6. Gera tokens (access + refresh)
7. Retorna TokenResponse

---

### 2️⃣ POST /api/auth/refresh

**Gera novo access token usando refresh token**

**Request:**
```json
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

**Erros:**
- `401 UNAUTHORIZED` — Refresh token inválido ou expirado

**Lógica:**
1. Valida refresh_token
2. Extrai claims (user_id, tenant_id, email)
3. Gera novo access_token
4. Retorna novo token

---

### 3️⃣ POST /api/auth/register

**Cria novo usuário no tenant (requer admin)**

**Requer:** `Authorization: Bearer {access_token}` com role=admin

**Request:**
```json
{
  "email": "novo_user@example.com",
  "password": "minhasenha123",
  "name": "Novo Usuário",
  "role": "user"
}
```

**Response (201 CREATED):**
```json
{
  "id": 2,
  "email": "novo_user@example.com",
  "nome": "Novo Usuário",
  "role": "user",
  "ativo": true,
  "tenant_id": 1
}
```

**Erros:**
- `401 UNAUTHORIZED` — Token ausente ou inválido
- `403 FORBIDDEN` — Usuário não é admin
- `400 BAD_REQUEST` — Email já existe ou dados inválidos
- `500 INTERNAL_SERVER_ERROR` — Erro ao criar usuário

**Lógica:**
1. Extrai current_user do token
2. Valida se é admin
3. Valida dados (email, password, name)
4. Cria novo usuário via UserService
5. Faz commit no banco
6. Retorna UserResponse

---

### 4️⃣ GET /api/auth/me

**Retorna dados do usuário autenticado**

**Requer:** `Authorization: Bearer {access_token}`

**Request:**
```bash
curl -H "Authorization: Bearer {access_token}" \
  http://localhost:8000/api/auth/me
```

**Response (200 OK):**
```json
{
  "id": 1,
  "email": "admin@example.com",
  "nome": "Admin User",
  "role": "admin",
  "ativo": true,
  "tenant_id": 1
}
```

**Erros:**
- `401 UNAUTHORIZED` — Token ausente ou inválido
- `404 NOT_FOUND` — Usuário não encontrado
- `500 INTERNAL_SERVER_ERROR` — Erro ao buscar

---

### 5️⃣ POST /api/auth/change-password

**Altera a senha do usuário autenticado**

**Requer:** `Authorization: Bearer {access_token}`

**Request:**
```json
{
  "old_password": "senhaantiga123",
  "new_password": "senhanova123"
}
```

**Response (200 OK):**
```json
{
  "status": "ok",
  "message": "Senha alterada com sucesso"
}
```

**Erros:**
- `401 UNAUTHORIZED` — Token ausente ou inválido
- `400 BAD_REQUEST` — Senha antiga incorreta ou nova senha inválida
- `500 INTERNAL_SERVER_ERROR` — Erro ao alterar

**Lógica:**
1. Extrai current_user do token
2. Valida senha antiga
3. Valida nova senha (min 6 chars)
4. Atualiza senha via UserService
5. Faz commit no banco
6. Retorna status ok

---

## 🔐 Middleware & Dependency Injection

### get_current_user Dependency

**Uso:**
```python
@app.get("/api/protected")
async def protected_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """Endpoint que requer autenticação"""
    return {
        "user_id": current_user["user_id"],
        "tenant_id": current_user["tenant_id"],
        "role": current_user["role"],
    }
```

**O que faz:**
1. Extrai Authorization header
2. Valida formato: "Bearer <token>"
3. Decodifica JWT
4. Valida token (expirado?, tipo?)
5. Retorna dict com user_id, tenant_id, email, role
6. Lança HTTPException(401) se inválido

**Exemplos de uso:**

```python
# 1. Endpoint público
@app.get("/health")
async def health():
    return {"status": "ok"}

# 2. Endpoint autenticado (qualquer role)
@app.get("/api/processos")
async def listar_processos(
    current_user: dict = Depends(get_current_user)
):
    # Usa current_user["tenant_id"] para filtrar dados
    pass

# 3. Endpoint apenas para admins (futura implementação)
@app.post("/api/admin/users")
async def criar_usuario_admin(
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Não autorizado")
    pass
```

---

## 📋 Fluxo Completo de Autenticação

```
┌─────────────────────────────────────────────────────┐
│ 1. USUÁRIO FAZ LOGIN                                │
└─────────────────────────────────────────────────────┘
  |
  v
POST /api/auth/login
  Content-Type: application/json
  {
    "email": "admin@example.com",
    "password": "minhasenha123",
    "tenant_numero_oab": "361329SP"
  }
  |
  v
┌─────────────────────────────────────────────────────┐
│ 2. SERVIDOR VALIDA CREDENCIAIS                      │
└─────────────────────────────────────────────────────┘
  ├─ Busca tenant por numero_oab
  ├─ Verifica se tenant está ativo
  ├─ Autentica usuário (UserService.authenticate_user)
  │  ├─ email + password + tenant_id
  │  └─ Verifica senha com bcrypt
  └─ Atualiza ultimo_login
  |
  v
┌─────────────────────────────────────────────────────┐
│ 3. SERVIDOR GERA TOKENS                             │
└─────────────────────────────────────────────────────┘
  ├─ Access Token (30 min)
  │  └─ Claims: user_id, tenant_id, email, role, type
  ├─ Refresh Token (7 dias)
  │  └─ Claims: user_id, tenant_id, email, type
  └─ Retorna TokenResponse
  |
  v
┌─────────────────────────────────────────────────────┐
│ 4. CLIENTE RECEBE TOKENS                            │
└─────────────────────────────────────────────────────┘
  {
    "access_token": "...",
    "refresh_token": "...",
    "expires_in": 1800
  }
  |
  v
┌─────────────────────────────────────────────────────┐
│ 5. CLIENTE USA ACCESS TOKEN NAS REQUISIÇÕES         │
└─────────────────────────────────────────────────────┘
  Authorization: Bearer {access_token}
  GET /api/processos
  GET /api/notificacoes
  POST /api/prazos/1/cumprido
  |
  v
┌─────────────────────────────────────────────────────┐
│ 6. MIDDLEWARE VALIDA TOKEN                          │
└─────────────────────────────────────────────────────┘
  ├─ Extrai Authorization header
  ├─ Valida JWT (assinatura, expiração)
  ├─ Extrai claims
  └─ Define contexto (user_id, tenant_id, role)
  |
  v
┌─────────────────────────────────────────────────────┐
│ 7. ENDPOINT PROCESSA COM CONTEXTO DO USUÁRIO        │
└─────────────────────────────────────────────────────┘
  ├─ Usa tenant_id para Row-Level Security
  ├─ Verifica role para autorização
  └─ Retorna dados do tenant
  |
  v
SE TOKEN EXPIRAR:
  |
  v
POST /api/auth/refresh
  Content-Type: application/json
  {
    "refresh_token": "..."
  }
  |
  v
RECEBE NOVO ACCESS TOKEN
  {
    "access_token": "...",
    "expires_in": 1800
  }
  |
  v
CONTINUA COM NOVO TOKEN
```

---

## 🔄 Integração com Endpoints Existentes

### Row-Level Security (RLS) com tenant_id

**Antes (Bloco 1, sem autenticação):**
```python
@app.get("/api/processos")
async def listar_processos(
    skip: int = 0,
    limit: int = 10,
    session: AsyncSession = Depends(get_db)
):
    # Retorna TODOS os processos de TODOS os tenants
    # ❌ Perigoso! Sem isolamento!
    query = select(Processo).offset(skip).limit(limit)
    result = await session.execute(query)
    return result.scalars().all()
```

**Depois (Dia 3, com autenticação):**
```python
@app.get("/api/processos")
async def listar_processos(
    skip: int = 0,
    limit: int = 10,
    current_user: dict = Depends(get_current_user),  # ← Novo!
    session: AsyncSession = Depends(get_db)
):
    tenant_id = current_user["tenant_id"]  # ← Usa tenant do token
    
    # Retorna APENAS processos deste tenant
    # ✅ Seguro! Row-Level Security ativo
    query = (
        select(Processo)
        .where(Processo.tenant_id == tenant_id)  # ← Filtro!
        .offset(skip)
        .limit(limit)
    )
    result = await session.execute(query)
    return result.scalars().all()
```

---

## 📚 Exemplos de Uso com CURL

### 1. Login
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "minhasenha123",
    "tenant_numero_oab": "361329SP"
  }'
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": 1,
    "email": "admin@example.com",
    "nome": "Admin",
    "role": "admin",
    "ativo": true,
    "tenant_id": 1
  }
}
```

### 2. Usar Token para Acessar Endpoint
```bash
TOKEN="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."

curl -X GET http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

### 3. Refresh de Token
```bash
REFRESH_TOKEN="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."

curl -X POST http://localhost:8000/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"$REFRESH_TOKEN\"}"
```

### 4. Criar Novo Usuário (admin only)
```bash
TOKEN="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."

curl -X POST http://localhost:8000/api/auth/register \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "novo@example.com",
    "password": "novausuario123",
    "name": "Novo Usuário",
    "role": "user"
  }'
```

### 5. Mudar Senha
```bash
TOKEN="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."

curl -X POST http://localhost:8000/api/auth/change-password \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "old_password": "minhasenha123",
    "new_password": "novasenh123"
  }'
```

---

## 🚀 Próximos Passos (Dia 4)

### Dia 4: Integração de Middleware em Todos Endpoints

**O que fazer:**
1. Adicionar `current_user: dict = Depends(get_current_user)` em todos endpoints de dados
2. Filtrar resultados por `tenant_id`
3. Verificar roles para endpoints admin

**Endpoints a proteger:**
```python
# Já protegidos (requerem auth):
POST /api/auth/register         # requer admin
GET  /api/auth/me               # requer qualquer role
POST /api/auth/change-password  # requer qualquer role

# A proteger (adicionar auth):
GET  /api/processos             # adicionar filtro tenant_id
GET  /api/processos/{id}        # verificar tenant_id
POST /api/processos/{id}/monitorar
GET  /api/processos/{id}/movimentacoes
GET  /api/notificacoes          # filtrar por tenant
GET  /api/notificacoes/nao-lidas
POST /api/notificacoes/{id}/lida
GET  /api/prazos                # filtrar por tenant
GET  /api/prazos/vencendo
GET  /api/prazos/vencidos
POST /api/prazos/{id}/cumprido
POST /api/scheduler/execute     # requer admin
GET  /api/scheduler/status
```

---

## ✅ Checklist Dia 3

- [x] POST /api/auth/login implementado
- [x] POST /api/auth/refresh implementado
- [x] POST /api/auth/register implementado
- [x] GET /api/auth/me implementado
- [x] POST /api/auth/change-password implementado
- [x] get_current_user dependency criada
- [x] Tratamento de erros 401/403 configurado
- [x] UserService integrado
- [x] JWT validation integrado
- [x] Password hashing verificado

---

## 📁 Arquivos Criados/Modificados

| Arquivo | Status | Descrição |
|---------|--------|-----------|
| `src/api/auth.py` | ✅ NOVO | Router com endpoints de autenticação |
| `src/schemas/auth_schemas.py` | ✅ NOVO | Schemas para request/response |
| `DIA_3_ENDPOINTS_AUTENTICACAO.md` | ✅ NOVO | Este documento |

---

## 🎊 Conclusão Dia 3

✅ **Endpoints de Autenticação 100% implementados**

Sistema de autenticação está completo e pronto para integração com todos os endpoints. Com Dia 3 concluído, podemos agora:

- ✓ Autenticar usuários com segurança
- ✓ Gerar e validar JWT tokens
- ✓ Implementar Row-Level Security
- ✓ Verificar roles e autorização
- ✓ Proteger endpoints sensíveis

Próximo: **Dia 4 - Integração de Middleware em Todos Endpoints** 🚀

---

**Data:** 2026-04-08  
**Status:** ✅ PRONTO PARA PRÓXIMO BLOCO

