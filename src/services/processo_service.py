"""
Serviço de persistência de processos em PostgreSQL.

Responsabilidades:
  1. Salvar ProcessoCompleto do crawler em processo + partes + movimentações
  2. Detectar novas movimentações via hash (data + descricao)
  3. Atualizar ultima_movimentacao_data automaticamente
  4. Manter histórico limpo (deduplicação)
"""

import hashlib
import structlog
from datetime import datetime, date
from typing import Optional

from sqlalchemy import select, and_, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Processo, Parte, Movimentacao, AdvogadoCatalog
from src.parsers.estruturas import ProcessoCompleto, MovimentacaoProcesso

logger = structlog.get_logger(__name__)


def _hash_movimentacao(mov: MovimentacaoProcesso) -> str:
    """Calcula hash único de (data, descricao) para deduplicação."""
    s = f"{mov.data_movimentacao}|{mov.descricao}".encode("utf-8")
    return hashlib.sha256(s).hexdigest()[:16]


class ProcessoService:
    """Serviço de persistência e monitoramento de processos."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def salvar_processo(
        self,
        processo: ProcessoCompleto,
        criar_monitoramento: bool = False,
        notificar_email: Optional[str] = None,
    ) -> tuple[Processo, list[str]]:
        """
        Salva/atualiza um processo com suas partes e movimentações.

        Retorna:
            (processo_db, lista_de_hashes_das_movimentacoes_novas)
        """
        # ─ 1. Upsert Processo ────────────────────────────────────────────────
        stmt = select(Processo).where(Processo.numero_cnj == processo.numero_cnj)
        resultado = await self.db.execute(stmt)
        processo_db = resultado.scalar_one_or_none()

        if processo_db is None:
            processo_db = Processo(
                numero_cnj=processo.numero_cnj,
                tribunal=processo.tribunal,
                grau=processo.grau,
                vara=processo.vara,
                comarca=processo.comarca,
                classe_processual=processo.classe_processual,
                assunto=processo.assunto,
                valor_causa=processo.valor_causa,
                data_distribuicao=processo.data_distribuicao,
                situacao=processo.situacao,
                segredo_justica=processo.segredo_justica,
                observacoes=processo.observacoes,
                score_auditoria=processo.score_auditoria,
                notas_auditoria=processo.notas_auditoria or [],
            )
            self.db.add(processo_db)
            await self.db.flush()  # Obtém o ID gerado
            logger.info(f"[NOVO] {processo.numero_cnj} ({processo.tribunal})")
        else:
            # Atualiza campos existentes
            processo_db.grau = processo.grau or processo_db.grau
            processo_db.vara = processo.vara or processo_db.vara
            processo_db.comarca = processo.comarca or processo_db.comarca
            processo_db.classe_processual = processo.classe_processual or processo_db.classe_processual
            processo_db.assunto = processo.assunto or processo_db.assunto
            processo_db.valor_causa = processo.valor_causa or processo_db.valor_causa
            processo_db.situacao = processo.situacao if processo.situacao is not None else processo_db.situacao
            if processo.observacoes:
                processo_db.observacoes = processo.observacoes
            if processo.score_auditoria is not None:
                processo_db.score_auditoria = processo.score_auditoria
                processo_db.notas_auditoria = processo.notas_auditoria or []
            logger.debug(f"[ATUALIZA] {processo.numero_cnj}")

        # ─ 2. Partes ─────────────────────────────────────────────────────────
        # Remove partes antigas e reinsere (estratégia simples)
        await self.db.execute(
            delete(Parte).where(Parte.processo_id == processo_db.id)
        )

        # Adiciona todas as partes primeiro
        partes_advogados = []  # Guarda OAB dos advogados para catalogar depois
        for parte in processo.partes:
            parte_db = Parte(
                processo_id=processo_db.id,
                tipo_parte=parte.tipo_parte,
                nome=parte.nome,
                documento=parte.documento,
                oab=parte.oab,
                polo=parte.polo,
            )
            self.db.add(parte_db)
            if parte.tipo_parte.upper() == "ADVOGADO" and parte.oab:
                partes_advogados.append((parte.oab, parte.nome))

        await self.db.flush()  # Flush todas para obter IDs

        # Popula AdvogadoCatalog com advogados encontrados
        for oab, nome in partes_advogados:
            await self.registrar_advogado(
                numero_oab=oab,
                uf=self._extrair_uf_da_oab(oab),
                nome_completo=nome,
            )

        # ─ 2b. Cross-reference advogados com clientes ──────────────────────────
        # Liga cada advogado à parte que ele representa (polo ativo ou passivo)
        await self._vincular_advogados_a_clientes(processo_db.id)

        await self.db.flush()  # Persiste os vínculos

    async def _extrair_uf_da_oab(self, oab: str) -> str:
        """Extrai a UF de uma OAB (ex: '361329SP' -> 'SP')."""
        if not oab:
            return ""
        # OAB pode ser 123456SP ou 123456/SP
        import re
        match = re.search(r'([A-Z]{2})$', oab.upper())
        if match:
            return match.group(1)
        return ""

    async def _vincular_advogados_a_clientes(self, processo_id: int) -> None:
        """
        Vincula advogados às partes que representam usando oAB e proximidade.
        Estratégia: advogado no mesmo 'bloco' de HTML que a parte.
        """
        try:
            # Busca advogado e cliente no mesmo processo
            advogado_result = await self.db.execute(
                select(Parte).where(
                    and_(
                        Parte.processo_id == processo_id,
                        Parte.tipo_parte.ilike("%ADVOGADO%")
                    )
                )
            )
            advogados = advogado_result.scalars().all()

            cliente_result = await self.db.execute(
                select(Parte).where(
                    and_(
                        Parte.processo_id == processo_id,
                        Parte.tipo_parte.ilike("%REQUERENTE%"),
                        Parte.advogado_de_id.is_(None)
                    )
                )
            )
            clientes = cliente_result.scalars().all()

            for advogado in advogados:
                if advogado.oab and clientes:
                    # Vincula ao primeiro cliente sem advogado
                    cliente_sem_adv = next(
                        (c for c in clientes if c.advogado_de_id is None), 
                        None
                    )
                    if cliente_sem_adv:
                        advogado.advogado_de_id = cliente_sem_adv.id
                        logger.debug(
                            f"[VINCULO] Adv {advogado.oab} -> Cliente {cliente_sem_adv.nome[:30]}"
                        )
        except Exception as e:
            logger.warning(f"[VINCULO] Erro ao vincular advogados: {e}")

        # ─ 3. Movimentações (detecta novas via hash) ──────────────────────────
        movs_existentes = await self.db.execute(
            select(Movimentacao).where(Movimentacao.processo_id == processo_db.id)
        )
        movs_db = {_hash_movimentacao(mov): mov for mov in movs_existentes.scalars()}

        hashes_novos = []
        for mov in processo.movimentacoes:
            hash_mov = _hash_movimentacao(mov)
            if hash_mov not in movs_db:
                mov_db = Movimentacao(
                    processo_id=processo_db.id,
                    data_movimentacao=mov.data_movimentacao,
                    tipo=mov.tipo,
                    descricao=mov.descricao,
                    complemento=mov.complemento,
                    codigo_nacional=mov.codigo_nacional,
                    categoria=mov.categoria,
                    impacto=mov.impacto,
                )
                self.db.add(mov_db)
                hashes_novos.append(hash_mov)

        await self.db.flush()

        # ─ 4. Atualiza data da última movimentação ───────────────────────────
        if processo.movimentacoes:
            data_ultima = max(m.data_movimentacao for m in processo.movimentacoes)
            processo_db.ultima_movimentacao_data = data_ultima

        await self.db.flush()

        if hashes_novos:
            logger.info(f"  → {len(hashes_novos)} nova(s) movimentação(ões)")

        # ─ 5. Monitoramento (opcional) ───────────────────────────────────────
        if criar_monitoramento:
            from src.database.models import Monitoramento

            stmt_mon = select(Monitoramento).where(
                Monitoramento.processo_id == processo_db.id
            )
            resultado_mon = await self.db.execute(stmt_mon)
            mon_db = resultado_mon.scalar_one_or_none()

            if mon_db is None:
                mon_db = Monitoramento(
                    processo_id=processo_db.id,
                    ativo=True,
                    notificar_email=notificar_email,
                )
                self.db.add(mon_db)
                await self.db.flush()

        return processo_db, hashes_novos

    async def salvar_processos(
        self,
        processos: list[ProcessoCompleto],
        criar_monitoramento: bool = False,
        notificar_email: Optional[str] = None,
    ) -> dict:
        """
        Salva uma lista de processos (batch).

        Retorna:
            {
                "total": int,
                "novos": int,
                "atualizados": int,
                "movimentacoes_novas_total": int,
                "erros": list[str],
            }
        """
        stats = {
            "total": len(processos),
            "novos": 0,
            "atualizados": 0,
            "movimentacoes_novas_total": 0,
            "erros": [],
        }

        for processo in processos:
            try:
                processo_db, hashes_novos = await self.salvar_processo(
                    processo,
                    criar_monitoramento=criar_monitoramento,
                    notificar_email=notificar_email,
                )
                stats["movimentacoes_novas_total"] += len(hashes_novos)

                # Heurística: se acaba de inserir 1o processo == novo
                if not await self._processo_existe_antes(processo.numero_cnj):
                    stats["novos"] += 1
                else:
                    stats["atualizados"] += 1

            except IntegrityError as e:
                msg = f"Erro integridade {processo.numero_cnj}: {e}"
                logger.error(msg)
                stats["erros"].append(msg)
                await self.db.rollback()
            except Exception as e:
                msg = f"Erro geral {processo.numero_cnj}: {type(e).__name__}: {e}"
                logger.error(msg)
                stats["erros"].append(msg)
                await self.db.rollback()

        # Commit final
        try:
            await self.db.commit()
            logger.info(
                f"✓ Salvos: {stats['novos']} novo(s), "
                f"{stats['atualizados']} atualizado(s), "
                f"{stats['movimentacoes_novas_total']} movimentação(ões) nova(s)"
            )
        except Exception as e:
            logger.error(f"Erro no commit final: {e}")
            await self.db.rollback()
            stats["erros"].append(f"Commit final: {e}")

        return stats

    async def _processo_existe_antes(self, numero_cnj: str) -> bool:
        """Verifica se processo já existia (heurística simplificada)."""
        # Em prod, isso seria um flag no modelo ou uma query à tabela de auditoria
        stmt = select(Processo).where(Processo.numero_cnj == numero_cnj)
        resultado = await self.db.execute(stmt)
        return resultado.scalar_one_or_none() is not None

    async def obter_processos_por_tribunal(
        self, tribunal: str, limite: int = 100, offset: int = 0
    ) -> list[Processo]:
        """Query de exemplo: processos por tribunal."""
        stmt = (
            select(Processo)
            .where(Processo.tribunal == tribunal)
            .order_by(Processo.data_distribuicao.desc())
            .limit(limite)
            .offset(offset)
        )
        resultado = await self.db.execute(stmt)
        return resultado.scalars().all()

    async def obter_processos_em_monitoramento(
        self, ativo: bool = True
    ) -> list[Processo]:
        """Query de exemplo: processos com monitoramento ativo."""
        from src.database.models import Monitoramento

        stmt = (
            select(Processo)
            .join(Monitoramento)
            .where(Monitoramento.ativo == ativo)
            .order_by(Processo.ultima_movimentacao_data.desc())
        )
        resultado = await self.db.execute(stmt)
        return resultado.scalars().all()

    async def registrar_advogado_descoberto(
        self,
        numero_oab: str,
        uf: str,
        nome_completo: str,
        cpf: Optional[str] = None,
        total_processos: int = 0
    ) -> AdvogadoCatalog:
        """
        Registra ou atualiza um advogado no catálogo de inteligência global.
        (Mecânica de Auto-Alimentação)
        """
        try:
            stmt = select(AdvogadoCatalog).where(
                and_(
                    AdvogadoCatalog.numero_oab == numero_oab,
                    AdvogadoCatalog.uf == uf.upper()
                )
            )
            resultado = await self.db.execute(stmt)
            advogado_db = resultado.scalar_one_or_none()

            agora = datetime.now()

            if advogado_db is None:
                advogado_db = AdvogadoCatalog(
                    numero_oab=numero_oab,
                    uf=uf.upper(),
                    nome_completo=nome_completo.upper(),
                    cpf=cpf,
                    total_processos_encontrados=total_processos,
                    ultima_consulta_at=agora
                )
                self.db.add(advogado_db)
                logger.info(f"[CATALOGO] Novo advogado registrado: {nome_completo} ({numero_oab}/{uf})")
            else:
                advogado_db.nome_completo = nome_completo.upper()
                if cpf:
                    advogado_db.cpf = cpf
                advogado_db.total_processos_encontrados = total_processos
                advogado_db.ultima_consulta_at = agora
                logger.debug(f"[CATALOGO] Advogado atualizado: {numero_oab}/{uf}")

            await self.db.flush()
            return advogado_db
        except Exception as e:
            logger.error(f"[CATALOGO] Erro ao registrar advogado: {e}")
            return None
