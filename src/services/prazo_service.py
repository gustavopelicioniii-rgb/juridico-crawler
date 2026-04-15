"""
Bloco 3: Motor de Prazos Processuais

Serviço para:
1. Detectar tipos de eventos (citação, sentença, apelação, etc)
2. Calcular datas de vencimento automaticamente
3. Gerenciar prazos processuais
4. Notificar quando prazos estão vencendo

Exemplos de Prazos:
  CITAÇÃO → CONTESTACAO (15 dias úteis)
  SENTENÇA → RECURSO (15 dias úteis)
  APELAÇÃO → CONTRARRAZÃO (15 dias úteis)
  INTIMACAO → CUMPRIMENTO (prazo variável)
"""
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Prazo, Movimentacao, Processo


class PrazoService:
    """Gerencia prazos processuais e calcula datas de vencimento."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # Mapa de tipos de movimentação para prazos
    EVENTOS_CRIADORES_DE_PRAZO = {
        # Chave: palavras-chave na descricao da movimentacao
        # Valor: (tipo_prazo, dias_uteis, descricao)
        "citação": ("CONTESTACAO", 15, "Contestação à ação"),
        "citado": ("CONTESTACAO", 15, "Contestação à ação"),
        "sentença": ("RECURSO", 15, "Recurso contra sentença"),
        "sentenciado": ("RECURSO", 15, "Recurso contra sentença"),
        "apelação": ("CONTRARRAZAO", 15, "Contrarrazão à apelação"),
        "apelado": ("CONTRARRAZAO", 15, "Contrarrazão à apelação"),
        "agravo": ("CONTRARRAZAO", 15, "Contrarrazão ao agravo"),
        "intimação": ("CUMPRIMENTO", 5, "Prazo para cumprimento de intimação"),
        "cumprimento de sentença": ("IMPUGNACAO", 15, "Impugnação ao cumprimento"),
        "execução": ("IMPUGNACAO", 15, "Defesa na execução"),
        "despacho": ("RECURSO", 10, "Recurso contra despacho"),
        "decisão interlocutória": ("AGRAVO", 10, "Agravo contra decisão interlocutória"),
        "mandado": ("CUMPRIMENTO", 30, "Cumprimento de mandado"),
    }

    async def detectar_prazos_por_movimentacao(
        self, movimentacao: Movimentacao
    ) -> List[Prazo]:
        """
        Detecta se uma movimentação cria prazos processuais.

        Args:
            movimentacao: Movimentação registrada

        Returns:
            Lista de Prazo criados (pode ser vazia se não há prazo)

        Exemplo:
            mov = Movimentacao(
                descricao="Citação do réu",
                data_movimentacao=datetime(2026, 4, 8)
            )
            prazos = await service.detectar_prazos(mov)
            # Retorna: [Prazo(tipo="CONTESTACAO", data_vencimento=2026-04-23)]
        """
        prazos_criados = []

        # Busca o processo associado
        processo = await self.db.get(Processo, movimentacao.processo_id)
        if not processo:
            return []

        # Normaliza descricao para busca
        descricao_lower = (movimentacao.descricao or "").lower()

        # Verifica cada tipo de evento
        for palavra_chave, (tipo_prazo, dias, descricao) in (
            self.EVENTOS_CRIADORES_DE_PRAZO.items()
        ):
            if palavra_chave in descricao_lower:
                # Calcula data de vencimento (somando dias úteis)
                data_vencimento = self._calcular_vencimento(
                    movimentacao.data_movimentacao, dias
                )

                # Verifica se já existe prazo deste tipo para este processo
                existing = await self.db.execute(
                    select(Prazo).where(
                        and_(
                            Prazo.processo_id == movimentacao.processo_id,
                            Prazo.tipo_prazo == tipo_prazo,
                            Prazo.cumprido == False,
                        )
                    )
                )
                prazo_existente = existing.scalar_one_or_none()

                if not prazo_existente:
                    # Cria novo prazo
                    prazo = Prazo(
                        processo_id=movimentacao.processo_id,
                        tipo_prazo=tipo_prazo,
                        descricao=descricao,
                        data_inicio=movimentacao.data_movimentacao,
                        data_vencimento=data_vencimento,
                        dias_uteis=dias,
                        cumprido=False,
                    )

                    self.db.add(prazo)
                    prazos_criados.append(prazo)

        await self.db.flush()
        return prazos_criados

    def _calcular_vencimento(
        self, data_inicial: datetime, dias_uteis: int
    ) -> datetime:
        """
        Calcula data de vencimento considerando apenas dias úteis (seg-sex).

        Args:
            data_inicial: Data de início do prazo
            dias_uteis: Quantidade de dias úteis

        Returns:
            Data de vencimento (considerando apenas dias úteis)

        Exemplo:
            data_inicial = 2026-04-08 (quarta)
            dias_uteis = 15
            resultado = 2026-04-30 (quinta, 15 dias úteis depois)
        """
        data_atual = data_inicial
        dias_contados = 0

        while dias_contados < dias_uteis:
            data_atual += timedelta(days=1)

            # Verifica se é dia útil (0=seg, 1=ter, ..., 6=dom)
            # Ignora sábado (5) e domingo (6)
            if data_atual.weekday() < 5:
                dias_contados += 1

        return data_atual

    async def obter_prazos_vencendo(
        self, dias_antecedencia: int = 3
    ) -> list[Prazo]:
        """
        Obtém prazos que vencem em breve.

        Args:
            dias_antecedencia: Quantos dias antes avisar (padrão: 3)

        Returns:
            Lista de prazos que vencem em X dias

        Exemplo:
            prazos = await service.obter_prazos_vencendo(dias_antecedencia=3)
            # Retorna prazos que vencem em até 3 dias
        """
        hoje = datetime.now().date()
        data_limite = hoje + timedelta(days=dias_antecedencia)

        query = select(Prazo).where(
            and_(
                Prazo.data_vencimento >= hoje,
                Prazo.data_vencimento <= data_limite,
                Prazo.cumprido == False,
            )
        )

        result = await self.db.execute(query)
        return result.scalars().all()

    async def obter_prazos_vencidos(self) -> list[Prazo]:
        """Obtém prazos que já venceram sem ser cumpridos."""
        hoje = datetime.now().date()

        query = select(Prazo).where(
            and_(
                Prazo.data_vencimento < hoje,
                Prazo.cumprido == False,
            )
        )

        result = await self.db.execute(query)
        return result.scalars().all()

    async def marcar_como_cumprido(
        self, prazo_id: int, movimentacao_cumprimento_id: Optional[int] = None
    ) -> None:
        """
        Marca um prazo como cumprido.

        Args:
            prazo_id: ID do prazo
            movimentacao_cumprimento_id: ID da movimentação que cumpriu o prazo
        """
        prazo = await self.db.get(Prazo, prazo_id)
        if prazo:
            prazo.cumprido = True
            prazo.data_cumprimento = datetime.now()
            prazo.movimentacao_cumprimento_id = movimentacao_cumprimento_id
            await self.db.flush()

    # notificado_em não existe no modelo, então removemos este método
    # As notificações são rastreadas na tabela Notificacao

    async def obter_prazos_por_processo(
        self, processo_id: int, apenas_abertos: bool = True
    ) -> list[Prazo]:
        """
        Obtém todos os prazos de um processo.

        Args:
            processo_id: ID do processo
            apenas_abertos: Se True, retorna apenas prazos não cumpridos

        Returns:
            Lista de prazos do processo
        """
        query = select(Prazo).where(Prazo.processo_id == processo_id)

        if apenas_abertos:
            query = query.where(Prazo.cumprido == False)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def buscar_movimentacoes_que_cumprem_prazo(
        self, prazo: Prazo
    ) -> Optional[Movimentacao]:
        """
        Busca uma movimentação que cumpre este prazo.

        Exemplos:
        - Se prazo é CONTESTACAO, busca por "contestação" na data
        - Se prazo é RECURSO, busca por "recurso" ou "apelação"

        Args:
            prazo: Prazo a verificar

        Returns:
            Movimentação que cumpre o prazo, ou None
        """
        # Mapa de tipos de prazo para palavras-chave de cumprimento
        palavras_cumprimento = {
            "CONTESTACAO": ["contestação", "contestada", "contestado"],
            "RECURSO": ["recurso", "apelação", "apelado"],
            "CONTRARRAZAO": ["contrarrazão", "contrarrazoada"],
            "IMPUGNACAO": ["impugnação", "impugnada"],
            "AGRAVO": ["agravo"],
            "CUMPRIMENTO": ["cumprimento", "cumprida", "cumpriu"],
        }

        palavras = palavras_cumprimento.get(prazo.tipo_prazo, [])
        if not palavras:
            return None

        # Busca movimentação após o início do prazo
        query = select(Movimentacao).where(
            and_(
                Movimentacao.processo_id == prazo.processo_id,
                Movimentacao.data_movimentacao >= prazo.data_inicio,
            )
        )

        result = await self.db.execute(query)
        movimentacoes = result.scalars().all()

        # Verifica qual cumpre o prazo
        for mov in movimentacoes:
            descricao_lower = (mov.descricao or "").lower()
            for palavra in palavras:
                if palavra in descricao_lower:
                    return mov

        return None

    def resumo_status_prazos(self, prazos: list[Prazo]) -> dict:
        """
        Retorna resumo do status dos prazos.

        Returns:
            {
                'total': int,
                'abertos': int,
                'cumpridos': int,
                'vencidos': int,
                'vencendo_em_3_dias': int,
            }
        """
        hoje = datetime.now().date()
        data_limite_3_dias = hoje + timedelta(days=3)

        abertos = [p for p in prazos if not p.cumprido]
        cumpridos = [p for p in prazos if p.cumprido]
        vencidos = [
            p for p in abertos if p.data_vencimento < hoje
        ]
        vencendo_3_dias = [
            p for p in abertos
            if hoje <= p.data_vencimento <= data_limite_3_dias
        ]

        return {
            "total": len(prazos),
            "abertos": len(abertos),
            "cumpridos": len(cumpridos),
            "vencidos": len(vencidos),
            "vencendo_em_3_dias": len(vencendo_3_dias),
        }
