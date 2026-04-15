"""
Bloco 2: Scheduler Diário

Executa a cada 24 horas:
1. Carrega processos em monitoramento
2. Re-executa crawlers para atualizar dados
3. Detecta novas movimentações via ProcessoService
4. Cria notificações quando há mudanças
5. Atualiza timestamps de verificação

Fluxo:
    Scheduler (diário)
        ↓
    obter_processos_em_monitoramento()
        ↓
    Para cada processo:
        ├─ Executa DataJud (buscar_processo por CNJ)
        ├─ ProcessoService.salvar_processo() → detecção de novas movs
        ├─ Se hashes_novos: NotificacaoService.criar_notificacao()
        └─ Atualiza ultima_verificacao e proxima_verificacao
"""
from datetime import datetime, timedelta
import asyncio
import logging
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import AsyncSessionLocal
from src.database.models import Processo, Monitoramento
from src.services.processo_service import ProcessoService
from src.services.notificacao_service import NotificacaoService

logger = logging.getLogger(__name__)

# Semáforo para limitar concorrência ao monitorar processos em paralelo
_SEMAFORO_MONITORAMENTO = asyncio.Semaphore(5)


class SchedulerJob:
    """Job principal do scheduler diário."""

    def __init__(self):
        """Inicializa o job."""
        self.db: Optional[AsyncSession] = None
        self.processo_service: Optional[ProcessoService] = None
        self.notificacao_service: Optional[NotificacaoService] = None

    async def _inicializar(self) -> None:
        """Inicializa conexão com banco e serviços."""
        self.db = AsyncSessionLocal()
        self.processo_service = ProcessoService(self.db)
        self.notificacao_service = NotificacaoService(self.db)

    async def _finalizar(self) -> None:
        """Finaliza conexão com banco."""
        if self.db:
            await self.db.close()

    async def obter_processos_monitorados(self) -> list[Processo]:
        """
        Obtém processos marcados para monitoramento ativo.

        Returns:
            Lista de processos com monitoramento ativo
        """
        query = (
            select(Processo)
            .join(Monitoramento)
            .where(Monitoramento.ativo == True)
        )

        result = await self.db.execute(query)
        return result.scalars().all()

    async def _buscar_atualizacao_processo(self, numero_cnj: str, tribunal: str) -> Optional[object]:
        """
        Busca dados atualizados de um processo via DataJud.

        Args:
            numero_cnj: Número CNJ do processo
            tribunal: Sigla do tribunal

        Returns:
            ProcessoCompleto atualizado ou None se falhar
        """
        try:
            from src.crawlers.datajud import DataJudCrawler
            async with DataJudCrawler() as crawler:
                resultado = await crawler.buscar_processo(numero_cnj, tribunal=tribunal)
                return resultado
        except Exception as e:
            logger.warning(f"DataJud falhou para {numero_cnj}: {e}. Tentando sem filtro de tribunal.")

        # Fallback: tenta sem especificar tribunal
        try:
            from src.crawlers.datajud import DataJudCrawler
            async with DataJudCrawler() as crawler:
                resultado = await crawler.buscar_processo(numero_cnj)
                return resultado
        except Exception as e:
            logger.error(f"Falha total ao buscar {numero_cnj}: {e}")
            return None

    async def _processar_processo(self, processo: Processo, stats: dict) -> None:
        """
        Processa a atualização de um único processo monitorado.
        Usa semáforo para limitar concorrência.
        """
        async with _SEMAFORO_MONITORAMENTO:
            try:
                logger.info(f"\n├─ Verificando: {processo.numero_cnj} ({processo.tribunal})")

                # 1. Buscar dados atualizados via crawler
                processo_atualizado = await self._buscar_atualizacao_processo(
                    processo.numero_cnj, processo.tribunal
                )

                if processo_atualizado:
                    # 2. Salvar e detectar novas movimentações
                    _, hashes_novos = await self.processo_service.salvar_processo(processo_atualizado)

                    if hashes_novos:
                        stats["processos_com_atualizacoes"] += 1
                        stats["movimentacoes_novas_total"] += len(hashes_novos)
                        logger.info(f"   ✓ {len(hashes_novos)} nova(s) movimentação(ões)")

                        # 3. Criar notificações
                        for hash_mov in hashes_novos:
                            try:
                                await self.notificacao_service.criar_notificacao(
                                    processo_id=processo.id,
                                    tipo="NOVA_MOVIMENTACAO",
                                    resumo=f"Nova movimentação em {processo.numero_cnj}",
                                    dados={"hash": hash_mov},
                                )
                                stats["notificacoes_criadas"] += 1
                            except Exception as e:
                                logger.warning(f"   Erro ao criar notificação: {e}")
                    else:
                        logger.info(f"   ✓ Sem novas movimentações")
                else:
                    logger.warning(f"   ✗ Não foi possível obter dados atualizados")

                # 4. Atualizar timestamp de verificação (busca correta pelo processo_id)
                query = select(Monitoramento).where(
                    Monitoramento.processo_id == processo.id
                )
                result = await self.db.execute(query)
                monitoramento = result.scalar_one_or_none()

                if monitoramento:
                    monitoramento.ultima_verificacao = datetime.now()
                    monitoramento.proxima_verificacao = datetime.now() + timedelta(hours=24)

                stats["processos_verificados"] += 1

            except Exception as e:
                erro_msg = f"Erro ao processar {processo.numero_cnj}: {str(e)}"
                logger.error(f"   ✗ {erro_msg}")
                stats["erros"].append(erro_msg)

    async def processar_uma_execucao(self) -> dict:
        """
        Executa uma iteração completa do scheduler.

        Returns:
            {
                'inicio': datetime,
                'fim': datetime,
                'duracao_segundos': float,
                'processos_verificados': int,
                'processos_com_atualizacoes': int,
                'movimentacoes_novas_total': int,
                'notificacoes_criadas': int,
                'erros': list[str],
            }
        """
        inicio = datetime.now()
        logger.info("=" * 70)
        logger.info("SCHEDULER DIÁRIO - INICIANDO EXECUÇÃO")
        logger.info("=" * 70)

        stats = {
            "inicio": inicio,
            "fim": None,
            "duracao_segundos": 0,
            "processos_verificados": 0,
            "processos_com_atualizacoes": 0,
            "movimentacoes_novas_total": 0,
            "notificacoes_criadas": 0,
            "erros": [],
        }

        try:
            await self._inicializar()

            # 1. Obter processos monitorados
            processos_monitorados = await self.obter_processos_monitorados()
            logger.info(f"✓ {len(processos_monitorados)} processo(s) em monitoramento")

            if not processos_monitorados:
                logger.info("Nenhum processo para verificar. Encerrando.")
                stats["fim"] = datetime.now()
                stats["duracao_segundos"] = (stats["fim"] - inicio).total_seconds()
                return stats

            # 2. Processar todos em paralelo (limitado por semáforo)
            tarefas = [
                self._processar_processo(processo, stats)
                for processo in processos_monitorados
            ]
            await asyncio.gather(*tarefas, return_exceptions=True)

            # 3. Commit de todas as mudanças
            await self.db.commit()

            stats["fim"] = datetime.now()
            stats["duracao_segundos"] = (stats["fim"] - inicio).total_seconds()

            logger.info("\n" + "=" * 70)
            logger.info("RESUMO DA EXECUÇÃO")
            logger.info("=" * 70)
            logger.info(f"✓ Processos verificados:       {stats['processos_verificados']}")
            logger.info(f"✓ Com atualizações:            {stats['processos_com_atualizacoes']}")
            logger.info(f"✓ Movimentações novas:         {stats['movimentacoes_novas_total']}")
            logger.info(f"✓ Notificações criadas:        {stats['notificacoes_criadas']}")
            if stats["erros"]:
                logger.warning(f"✗ Erros encontrados:           {len(stats['erros'])}")
                for erro in stats["erros"]:
                    logger.warning(f"  - {erro}")
            logger.info(f"✓ Duração:                     {stats['duracao_segundos']:.2f}s")
            logger.info("=" * 70 + "\n")

            return stats

        except Exception as e:
            logger.error(f"✗ Erro fatal no scheduler: {str(e)}")
            stats["fim"] = datetime.now()
            stats["duracao_segundos"] = (stats["fim"] - inicio).total_seconds()
            stats["erros"].append(str(e))
            try:
                await self.db.rollback()
            except Exception:
                pass
            return stats

        finally:
            await self._finalizar()

    async def executar(self) -> dict:
        """
        Ponto de entrada principal para execução do scheduler.

        Pode ser chamado por:
        1. APScheduler (automaticamente a cada 24h)
        2. CLI manual: python -m src.scheduler.cli execute
        3. API: POST /api/scheduler/execute

        Returns:
            Estatísticas da execução
        """
        return await self.processar_uma_execucao()


# Função wrapper para ser usada com APScheduler
async def job_scheduler_diario():
    """
    Job que será agendado pelo APScheduler.

    Chamado automaticamente a cada 24 horas (configurável).
    """
    job = SchedulerJob()
    resultado = await job.executar()
    return resultado


def job_scheduler_diario_sync():
    """
    Wrapper síncrono para APScheduler (que não suporta async nativamente).

    APScheduler executará isto em uma thread e o asyncio.run() rodará
    a coroutine de forma síncrona.
    """
    return asyncio.run(job_scheduler_diario())
