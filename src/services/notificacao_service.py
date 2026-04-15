"""
Serviço de gerenciamento de notificações sobre movimentações processuais.

Responsabilidades:
- Criar notificações quando há novas movimentações
- Registrar notificações de prazos vencendo
- Enviar notificações via email ou webhook
"""
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import Notificacao, Monitoramento, Processo


class NotificacaoService:
    """Gerencia notificações sobre processos."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def criar_notificacao_movimento(
        self,
        processo_id: int,
        hashes_novos: list[str],
        resumo_movimentacoes: str,
    ) -> Notificacao:
        """
        Cria notificação de nova movimentação.

        Args:
            processo_id: ID do processo
            hashes_novos: Lista de hashes das novas movimentações
            resumo_movimentacoes: Resumo das movimentações detectadas

        Returns:
            Notificacao criada
        """
        notificacao = Notificacao(
            processo_id=processo_id,
            tipo="NOVA_MOVIMENTACAO",
            resumo=resumo_movimentacoes,
            dados={
                "hashes_novos": hashes_novos,
                "total_movimentacoes_novas": len(hashes_novos),
                "detectado_em": datetime.now().isoformat(),
            },
            lida=False,
        )

        self.db.add(notificacao)
        await self.db.flush()

        return notificacao

    async def criar_notificacao_prazo(
        self,
        processo_id: int,
        tipo_prazo: str,
        dias_ate_vencimento: int,
        resumo: str,
    ) -> Notificacao:
        """
        Cria notificação de prazo vencendo.

        Args:
            processo_id: ID do processo
            tipo_prazo: Tipo de prazo (CONTESTACAO, RECURSO, etc)
            dias_ate_vencimento: Dias até o vencimento
            resumo: Resumo do prazo

        Returns:
            Notificacao criada
        """
        notificacao = Notificacao(
            processo_id=processo_id,
            tipo="PRAZO_VENCENDO",
            resumo=resumo,
            dados={
                "tipo_prazo": tipo_prazo,
                "dias_ate_vencimento": dias_ate_vencimento,
                "detectado_em": datetime.now().isoformat(),
            },
            lida=False,
        )

        self.db.add(notificacao)
        await self.db.flush()

        return notificacao

    async def obter_nao_lidas(
        self, processo_id: Optional[int] = None
    ) -> list[Notificacao]:
        """
        Obtém notificações não lidas.

        Args:
            processo_id: Filtro opcional por processo

        Returns:
            Lista de notificações não lidas
        """
        query = select(Notificacao).where(Notificacao.lida == False)

        if processo_id:
            query = query.where(Notificacao.processo_id == processo_id)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def marcar_como_lida(self, notificacao_id: int) -> None:
        """Marca notificação como lida."""
        notificacao = await self.db.get(Notificacao, notificacao_id)
        if notificacao:
            notificacao.lida = True
            await self.db.flush()

    async def marcar_lidas_por_processo(self, processo_id: int) -> int:
        """
        Marca todas as notificações de um processo como lidas.

        Returns:
            Quantidade de notificações atualizadas
        """
        query = select(Notificacao).where(
            and_(
                Notificacao.processo_id == processo_id,
                Notificacao.lida == False,
            )
        )

        result = await self.db.execute(query)
        notificacoes = result.scalars().all()

        for notif in notificacoes:
            notif.lida = True

        return len(notificacoes)

    async def enviar_notificacoes_via_email(
        self, notificacoes: list[Notificacao]
    ) -> dict:
        """
        Simula envio de notificações via email.

        Em produção, seria integrado com SendGrid ou similar.

        Returns:
            {
                'enviadas': int,
                'falhadas': int,
                'detalhes': list
            }
        """
        resultado = {"enviadas": 0, "falhadas": 0, "detalhes": []}

        for notif in notificacoes:
            # Busca o processo e seu monitoramento
            processo = await self.db.get(Processo, notif.processo_id)
            if not processo:
                resultado["falhadas"] += 1
                resultado["detalhes"].append(
                    f"Processo {notif.processo_id} não encontrado"
                )
                continue

            # Busca o monitoramento
            query = select(Monitoramento).where(
                Monitoramento.processo_id == notif.processo_id
            )
            result = await self.db.execute(query)
            monitoramento = result.scalar_one_or_none()

            if not monitoramento or not monitoramento.notificar_email:
                resultado["falhadas"] += 1
                resultado["detalhes"].append(
                    f"Sem email configurado para processo {processo.numero_cnj}"
                )
                continue

            # Aqui seria implementado o envio real via SendGrid/SMTP
            # Por enquanto, apenas simula
            resultado["enviadas"] += 1
            resultado["detalhes"].append(
                f"✓ Email enviado para {monitoramento.notificar_email} "
                f"- Processo {processo.numero_cnj}: {notif.resumo}"
            )

        return resultado

    async def enviar_notificacoes_via_webhook(
        self, notificacoes: list[Notificacao]
    ) -> dict:
        """
        Envia notificações via webhook.

        Returns:
            {
                'enviadas': int,
                'falhadas': int,
                'detalhes': list
            }
        """
        resultado = {"enviadas": 0, "falhadas": 0, "detalhes": []}

        for notif in notificacoes:
            processo = await self.db.get(Processo, notif.processo_id)
            if not processo:
                resultado["falhadas"] += 1
                continue

            # Busca monitoramento
            query = select(Monitoramento).where(
                Monitoramento.processo_id == notif.processo_id
            )
            result = await self.db.execute(query)
            monitoramento = result.scalar_one_or_none()

            if not monitoramento or not monitoramento.webhook_url:
                resultado["falhadas"] += 1
                resultado["detalhes"].append(
                    f"Sem webhook configurado para processo {processo.numero_cnj}"
                )
                continue

            # Aqui seria implementado o envio real via requests/httpx
            # Por enquanto, apenas simula
            resultado["enviadas"] += 1
            resultado["detalhes"].append(
                f"✓ Webhook enviado para {monitoramento.webhook_url} "
                f"- Processo {processo.numero_cnj}"
            )

        return resultado
