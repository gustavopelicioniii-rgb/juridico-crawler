import asyncio
import sys
import os

sys.path.append(os.getcwd())

from src.crawlers.orquestrador import OrquestradorNativo
from src.parsers.estruturas import ProcessoCompleto

class AuditorRobo:
    def __init__(self):
        self.orquestrador = OrquestradorNativo()
        
    def analisar_completude(self, processo: ProcessoCompleto):
        """
        Analisa a estrutura dos dados capturados de um processo e retorna um score
        de confiabilidade (1-100) junto com uma lista de erros e avisos.
        """
        erros = []
        avisos = []
        pontos = 100
        
        # 1. Metadados básicos
        if not processo.numero_cnj:
            erros.append("Número CNJ ausente.")
            pontos -= 30
        if not processo.tribunal:
            erros.append("Tribunal de origem ausente.")
            pontos -= 10
            
        if not processo.classe_processual:
            avisos.append("Classe processual não identificada.")
            pontos -= 5
        if not processo.assunto:
            avisos.append("Assunto do processo em branco.")
            pontos -= 5
        if not processo.vara or not processo.comarca:
            avisos.append("Identificação de Vara ou Comarca ausentes.")
            pontos -= 5
            
        # 2. Segredo de Justiça
        if processo.segredo_justica:
            avisos.append("Processo tramita em Segredo de Justiça. Informações foram naturalmente omitidas pelo tribunal.")
            # Não penaliza as partes nem certas ausências, pois o tribunal esconde por lei
        else:
            # 3. Partes
            if not processo.partes:
                erros.append("Nenhuma parte (autor/réu) encontrada e o processo não é Segredo de Justiça.")
                pontos -= 20
            else:
                tipos = [p.tipo_parte.upper() for p in processo.partes if p.tipo_parte]
                tem_requerente = any("REQUERENTE" in t or "AUTOR" in t or "EXEQUENTE" in t or "REQTE" in t or "EXQTE" in t or "IMPTTE" in t or "EMBTE" in t for t in tipos)
                tem_requerido = any("REQUERIDO" in t or "REU" in t or "RÉU" in t or "EXECUTADO" in t or "REQDO" in t or "EXDO" in t or "IMPTDO" in t or "EMBDO" in t for t in tipos)
                
                if not (tem_requerente or tem_requerido):
                    avisos.append("Partes identificadas, mas com rótulos de autor/réu confusos ou genéricos.")
                    pontos -= 5
                
        # 4. Movimentações
        if not processo.movimentacoes:
            if processo.situacao and processo.situacao.upper() in ["CONCLUÍDO", "BAIXADO", "EXTINTO", "ARQUIVADO"]:
                erros.append("Processo dado como concluído/baixado, mas zero movimentações foram extraídas.")
                pontos -= 20
            else:
                avisos.append("Nenhuma movimentação processual extraída. Pode ser erro de raspagem ou processo recém-distribuído num feriado.")
                pontos -= 10
                
        # 5. Valores
        if processo.valor_causa is None:
            avisos.append("Valor da causa ausente.")
            pontos -= 5
            
        # Garantir limite de 0 a 100
        confiabilidade = max(0, min(100, pontos))
        
        return {
            "pontos": confiabilidade,
            "erros": erros,
            "avisos": avisos
        }


    async def auditar_oab(self, numero_oab: str, uf: str, limite: int = 10):
        print("="*60)
        print(f"=== INICIANDO AUDITORIA DO ROBO: OAB {numero_oab}/{uf} ===")
        print("="*60)
        print(f"O robô vai simular uma extração extraindo uma amostra de até {limite} processos...")
        
        # Puxa lote reduzido
        todas_ocorrencias = await self.orquestrador.buscar_por_oab(numero_oab, uf)
        amostra = todas_ocorrencias[:limite]
        
        if not amostra:
            print("[ERRO] O robô não encontrou nenhum processo para validar nesta consulta.")
            return

        print(f"\n[OK] {len(amostra)} processo(s) recuperados. Iniciando triagem de integridade:\n")
        
        media_pontos = 0
        for i, p in enumerate(amostra, 1):
            validacao = self.analisar_completude(p)
            media_pontos += validacao['pontos']
            
            print(f"[{i}/{len(amostra)}] [ITEM] CNJ: {p.numero_cnj}")
            print(f"     Status de Leitura: Nível de Confiança {validacao['pontos']}/100")
            print(f"     [INFO] Partes: {len(p.partes)} capturadas | Movimentaçóes: {len(p.movimentacoes)} capturadas - (Segredo: {'Sim' if p.segredo_justica else 'Não'})")
            
            if validacao["erros"]:
                print("     [ERRO] FALHAS CRÍTICAS:")
                for e in validacao["erros"]:
                     print(f"          - {e}")
            
            if validacao["avisos"]:
                print("     [AVISO] AVISOS OU ADVERTÊNCIAS (Pode ser normal do Tribunal):")
                for a in validacao["avisos"]:
                     print(f"          - {a}")
                     
            if not validacao["erros"] and not validacao["avisos"]:
                 print("     [OK] Extração validada com sucesso, 100% íntegra!")
            print("-" * 60)
            
        media = media_pontos / len(amostra)
        print("\n" + "="*60)
        print(f"--- RESULTADO DA AUDITORIA GERAL DO ROBO:")
        print(f"Confiança Média da Amostra: {media:.1f}/100")
        if media == 100:
             print("Conclusão: Pode confiar plenamente. Todos os dados críticos estão batendo perfeitamente.")
        elif media >= 85:
             print("Conclusão: O robô obteve dados extremamente sólidos. Faltam apenas alguns detalhes menores que os tribunais costumam não preencher (Ex: Valor da Causa / Assunto).")
        elif media >= 70:
             print("Conclusão: Atenção média. Alguns processos podem estar corrompidos no tribunal de origem, ou são os famosos 'Segredo de Justiça' sem informações vitais.")
        else:
             print("Conclusão: ALERTA CRÍTICO! Muitos erros vitais detetados na estrutura. É recomendado ajustar os leitores do crawler do robô.")
        print("="*60)
        
        
if __name__ == "__main__":
    auditor = AuditorRobo()
    # Pega os argumentos (OAB e UF) ou usa o padrão do cliente
    oab = sys.argv[1] if len(sys.argv) > 1 else "361329"
    uf = sys.argv[2] if len(sys.argv) > 2 else "SP"
    limite = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    
    asyncio.run(auditor.auditar_oab(oab, uf, limite))
