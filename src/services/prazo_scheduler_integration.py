"""
Integração do PrazoService com o Scheduler Diário

Esta integração é executada automaticamente a cada dia:
1. Quando novas movimentações são detectadas
2. Cria prazos automaticamente
3. Verifica prazos vencendo (3 dias antes)
4. Envia notificações automáticas
"""
import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    Movimentacao, Notificacao, Processo, Monitoramento, Prazo
)
from src.services.prazo_service import PrazoService
from src.services.notificacao_service import NotificacaoService

logger = logging.getLogger(__name__)


async def processar_prazos_para_movimento(
    db: AsyncSession,
    movimento: Movimentacao,
    processo: Processo,
) -> dict:
    """
    Processa um movimento para detectar e criar prazos.

    Called when a new movement is detected by the scheduler.

    Args:
        db: AsyncSession do banco
        movimento: Movimentação detectada
        processo: Processo associado

    Returns:
        {
            'prazos_criados': int,
            'detalhes': list[str],
        }
    """
    resultado = {"prazos_criados": 0, "detalhes": []}

    try:
        prazo_service = PrazoService(db)
        prazos = await prazo_service.detectar_prazos_por_movimentacao(movimento)

        if prazos:
            resultado["prazos_criados"] = len(prazos)

            for prazo in prazos:
                resumo = (
                    f"Prazo {prazo.tipo_prazo} criado: "
                    f"{prazo.descricao} (vence em {prazo.data_vencimento})"
                )
                logger.info(f"  ✓ {resumo}")
                resultado["detalhes"].append(resumo)

                # Cria notificação sobre o novo prazo
                notif_service = NotificacaoService(db)
                await notif_service.criar_notificacao_prazo(
                    processo_id=processo.id,
                    tipo_prazo=prazo.tipo_prazo,
                    dias_ate_vencimento=self._calcular_dias_ate_vencimento(
                        prazo.data_vencimento
                    ),
                    resumo=f"Novo prazo: {prazo.descricao}",
                )

        await db.flush()

    except Exception as e:
        logger.error(f"Erro ao processar prazos: {str(e)}")
        resultado["detalhes"].append(f"✗ Erro: {str(e)}")

    return resultado


async def verificar_e_notificar_prazos_vencendo(
    db: AsyncSession, dias_antecedencia: int = 3
) -> dict:
    """
    Verifica prazos que estão vencendo e envia notificações.

    Executado automaticamente pelo scheduler uma vez por dia.

    Args:
        db: AsyncSession do banco
        dias_antecedencia: Quantos dias antes avisar (padrão: 3)

    Returns:
        {
            'prazos_vencendo': int,
            'notificacoes_criadas': int,
            'detalhes': list[str],
        }
    """
    resultado = {
        "prazos_vencendo": 0,
        "notificacoes_criadas": 0,
        "detalhes": [],
    }

    try:
        prazo_service = PrazoService(db)
        notif_service = NotificacaoService(db)

        # Obtém prazos vencendo em breve
        prazos = await prazo_service.obter_prazos_vencendo(dias_antecedencia)

        logger.info(f"Verificando prazos vencendo ({dias_antecedencia} dias): "
                   f"{len(prazos)} encontrados")

        resultado["prazos_vencendo"] = len(prazos)

        for prazo in prazos:
            # Busca processo para detalhes
            processo = await db.get(Processo, prazo.processo_id)
            if not processo:
                continue

            # Calcula dias até vencimento
            from datetime import datetime as dt
            dias_faltam = (prazo.data_vencimento - dt.now().date()).days

            # Cria notificação
            await notif_service.criar_notificacao_prazo(
                processo_id=processo.id,
                tipo_prazo=prazo.tipo_prazo,
                dias_ate_vencimento=dias_faltam,
                resumo=f"Faltam {dias_faltam} dias para vencer: {prazo.descricao}",
            )

            resultado["notificacoes_criadas"] += 1

            resumo = (
                f"Notificação criada: {processo.numero_cnj} - "
                f"{prazo.tipo_prazo} (faltam {dias_faltam} dias)"
            )
            logger.info(f"  ✓ {resumo}")
            resultado["detalhes"].append(resumo)

        await db.flush()

    except Exception as e:
        logger.error(f"Erro ao verificar prazos vencendo: {str(e)}")
        resultado["detalhes"].append(f"✗ Erro: {str(e)}")

    return resultado


async def verificar_prazos_cumpridos(db: AsyncSession) -> dict:
    """
    Verifica se movimentações recentes cumprem algum prazo.

    Exemplo:
        - Prazo CONTESTACAO criado em 2026-04-08
        - Movimentação "Contestação" detectada em 2026-04-20
        - PrazoService detecta e marca como cumprido

    Returns:
        {
            'prazos_cumpridos': int,
            'detalhes': list[str],
        }
    """
    resultado = {"prazos_cumpridos": 0, "detalhes": []}

    try:
        prazo_service = PrazoService(db)

        # Obtém todos os prazos abertos
        query = select(Prazo).where(Prazo.cumprido == False)
        result = await db.execute(query)
        prazos_abertos = result.scalars().all()

        for prazo in prazos_abertos:
            # Busca movimentação que cumpre este prazo
            movimento_cumprimento = (
                await prazo_service.buscar_movimentacoes_que_cumprem_prazo(
                    prazo
                )
            )

            if movimento_cumprimento:
                # Marca como cumprido
                await prazo_service.marcar_como_cumprido(
                    prazo.id,
                    movimento_cumprimento_id=movimento_cumprimento.id,
                )

                resultado["prazos_cumpridos"] += 1

                processo = await db.get(Processo, prazo.processo_id)
                resumo = (
                    f"Prazo cumprido: {processo.numero_cnj} - "
                    f"{prazo.tipo_prazo}"
                )
                logger.info(f"  ✓ {resumo}")
                resultado["detalhes"].append(resumo)

        await db.flush()

    except Exception as e:
        logger.error(f"Erro ao verificar prazos cumpridos: {str(e)}")
        resultado["detalhes"].append(f"✗ Erro: {str(e)}")

    return resultado


def _calcular_dias_ate_vencimento(data_vencimento) -> int:
    """Calcula dias até a data de vencimento."""
    from datetime import datetime as dt
    dias = (data_vencimento - dt.now().date()).days
    return max(dias, 0)
