#!/bin/bash
# ============================================================
# juridico-crawler - Setup Oracle Cloud Free Tier
# ============================================================
#
# PASSO A PASSO:
# 1. Criar conta em: https://www.oracle.com/cloud/free/
# 2. Escolher "Always Free" (não o paid)
# 3. Criar uma VM:
#    - Imagem: Oracle Linux 8 (ou Ubuntu 22.04)
#    - Shape: Ampere (ARM) - 4 cores, 24GB RAM (Always Free!)
#    - Localidade: São Paulo (oracle.com/cloud-regan)
#    - Chave SSH: gerar uma nova ou usar existente
#
# DEPOIS DE CRIAR A VM, RODE ESTE SCRIPT:
# ssh -i sua_chave.pem opc@IP_DA_VM
# curl -fsSL https://raw.githubusercontent.com/gustavopelicioniii-rgb/juridico-crawler/main/setup_oracle_cloud.sh | bash
#
# ============================================================

set -e

echo "========================================" 
echo "  juridico-crawler - Setup Oracle Cloud"
echo "========================================"
echo ""

# Atualizar sistema
echo "[1/6] Atualizando sistema..."
sudo dnf update -y || sudo apt update -y

# Instalar dependências
echo "[2/6] Instalando Python e dependências..."
sudo dnf install -y python3 python3-pip git docker docker-compose || \
sudo apt install -y python3 python3-pip git docker docker-compose

# Clonar projeto (ou pull se já existir)
echo "[3/6] Baixando projeto..."
if [ -d "/opt/juridico-crawler" ]; then
    echo "Projeto já existe, fazendo pull..."
    cd /opt/juridico-crawler
    git pull
else
    sudo git clone https://github.com/gustavopelicioniii-rgb/juridico-crawler.git /opt/juridico-crawler
    cd /opt/juridico-crawler
fi

# Instalar dependências Python
echo "[4/6] Instalando dependências Python..."
pip3 install -r requirements.txt --break-system-packages

# Configurar ambiente
echo "[5/6] Configurando ambiente..."
cp .env.example .env 2>/dev/null || true
echo ""
echo "⚠️  EDITE O ARQUIVO .env ANTES DE CONTINUAR:"
echo "   nano /opt/juridico-crawler/.env"
echo "   Configure pelo menos:"
echo "   - ANTHROPIC_API_KEY (se quiser IA)"
echo "   - DATABASE_URL (PostgreSQL)"
echo ""

# Iniciar PostgreSQL e API
echo "[6/6] Iniciando serviços..."
docker-compose up -d db
sleep 5
echo ""
echo "========================================" 
echo "  Setup concluído!"
echo "========================================" 
echo ""
echo "PRÓXIMOS PASSOS:"
echo "1. Edite o .env: nano /opt/juridico-crawler/.env"
echo "2. Configure a API Key do Claude (ANTHROPIC_API_KEY)"
echo "3. (Opcional) Configure proxy brasileiro se tribunais bloquearem"
echo "4. Inicie a API: uvicorn src.main:app --host 0.0.0.0 --port 8000"
echo ""
echo "TESTE:"
echo "   curl http://localhost:8000/health"
echo ""
