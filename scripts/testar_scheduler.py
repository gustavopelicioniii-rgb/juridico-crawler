#!/usr/bin/env python
"""
Script de teste: Executa scheduler manualmente uma vez

Uso:
    python scripts/testar_scheduler.py

Resultado:
    ✓ Carrega processos monitorados
    ✓ Re-executa crawlers
    ✓ Detecta novas movimentações
    ✓ Cria notificações
    ✓ Atualiza timestamps
"""
import asyncio
import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Adiciona src ao path (funciona no Windows e Linux)
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


async def teste_scheduler():
    """Executa o scheduler uma vez."""
    try:
        from src.scheduler.jobs import atualizar_processos_monitorados

        logger.info("=" * 70)
        logger.info("TESTE DO SCHEDULER")
        logger.info("=" * 70)
        logger.info(f"Horário da execução: {datetime.now().isoformat()}")
        logger.info("Iniciando atualização de processos monitorados...\n")

        # Executa o job uma vez
        await atualizar_processos_monitorados()

        logger.info("\n" + "=" * 70)
        logger.info("✓ TESTE CONCLUÍDO COM SUCESSO")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"\n✗ ERRO NO TESTE: {str(e)}", exc_info=True)
        return False

    return True


async def teste_scheduler_com_intervalo(intervalo_segundos: int = 60):
    """
    Executa o scheduler repetidamente com intervalo.

    Uso:
        python scripts/testar_scheduler.py --interval 3600

    Args:
        intervalo_segundos: Intervalo entre execuções (padrão: 60s)
    """
    from src.scheduler.jobs import atualizar_processos_monitorados

    contador = 0

    try:
        while True:
            contador += 1
            logger.info("\n" + "=" * 70)
            logger.info(f"EXECUÇÃO #{contador}")
            logger.info("=" * 70)
            logger.info(f"Horário: {datetime.now().isoformat()}")

            try:
                await atualizar_processos_monitorados()
            except Exception as e:
                logger.error(f"✗ Erro na execução: {str(e)}", exc_info=True)

            logger.info(f"✓ Aguardando {intervalo_segundos}s para próxima execução...")
            await asyncio.sleep(intervalo_segundos)

    except KeyboardInterrupt:
        logger.info("\n✓ Teste interrompido pelo usuário")


async def teste_com_apscheduler():
    """Teste com APScheduler rodando continuamente."""
    from src.scheduler.jobs import criar_scheduler

    logger.info("=" * 70)
    logger.info("TESTE: APScheduler em Modo Contínuo")
    logger.info("=" * 70)

    scheduler = criar_scheduler()
    scheduler.start()

    logger.info("✓ Scheduler iniciado")
    logger.info("✓ Rodando continuamente. Pressione Ctrl+C para parar.")

    try:
        await asyncio.sleep(float("inf"))
    except KeyboardInterrupt:
        logger.info("\n✓ Parando scheduler...")
        scheduler.shutdown()
        logger.info("✓ Scheduler parado")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Testa o scheduler de monitoramento de processos"
    )
    parser.add_argument(
        "--mode",
        choices=["once", "interval", "continuous"],
        default="once",
        help="Modo de execução",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Intervalo em segundos (para --mode interval)",
    )

    args = parser.parse_args()

    try:
        if args.mode == "once":
            sucesso = asyncio.run(teste_scheduler())
            sys.exit(0 if sucesso else 1)

        elif args.mode == "interval":
            asyncio.run(teste_scheduler_com_intervalo(args.interval))

        elif args.mode == "continuous":
            asyncio.run(teste_com_apscheduler())

    except KeyboardInterrupt:
        logger.info("\n✓ Teste interrompido")
        sys.exit(0)

    except Exception as e:
        logger.error(f"\n✗ ERRO: {str(e)}", exc_info=True)
        sys.exit(1)
