"""
Todas as chamadas à API Groq (Llama 3.3 70B).
Saídas sem caracteres especiais markdown para facilitar cópia.
"""
from __future__ import annotations

import os
import re
import time
from groq import Groq

from constants import MODEL_PRIMARY, MODEL_FALLBACKS, SUB_BATCH_SIZE, TONS, ESTILOS

DAILY_LIMIT = 100_000  # tokens/dia no plano gratuito Groq

# Contador de tokens da sessão atual (acumula enquanto o servidor estiver rodando)
_session_tokens: int = 0
_session_requests: int = 0


def get_token_usage() -> dict:
    """Retorna uso de tokens da sessão atual."""
    return {
        "used":      _session_tokens,
        "limit":     DAILY_LIMIT,
        "remaining": max(0, DAILY_LIMIT - _session_tokens),
        "pct":       min(100, int(_session_tokens / DAILY_LIMIT * 100)),
        "requests":  _session_requests,
    }


# ── Chat ──────────────────────────────────────────────────────────────────────

def _chat(messages: list, max_tokens: int = 2000, temperature: float = 0.7) -> str:
    """Chama Groq; em rate-limit usa fallbacks automaticamente."""
    global _session_tokens, _session_requests

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY não encontrada. Verifique o arquivo .env")

    client = Groq(api_key=api_key)
    last_error = None

    for model_name in [MODEL_PRIMARY] + MODEL_FALLBACKS:
        for attempt in range(2):
            try:
                resp = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                # Acumula uso de tokens
                if hasattr(resp, "usage") and resp.usage:
                    _session_tokens   += resp.usage.total_tokens
                    _session_requests += 1
                return resp.choices[0].message.content
            except Exception as e:
                err_str = str(e).lower()
                if "decommissioned" in err_str or "model_decommissioned" in err_str:
                    last_error = e
                    break
                if "429" in str(e) or "rate_limit" in err_str:
                    wait = 15 if attempt == 0 else 30
                    last_error = e
                    time.sleep(wait)
                    continue
                raise
        continue

    raise RuntimeError(
        "Limite diário de tokens atingido em todos os modelos.\n\n"
        "O plano gratuito do Groq permite 100.000 tokens por dia. "
        "O limite reseta à meia-noite (horário de Brasília). "
        "Tente novamente mais tarde."
    ) from last_error


# ── Text cleaner ──────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Remove caracteres especiais Markdown para facilitar cópia e colagem."""
    # Negrito e itálico: **texto** ou *texto*
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
    # Headings: ## Título
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Linhas horizontais
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # Blockquotes
    text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)
    # Links: [texto](url) → texto
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Bullets com - ou *
    text = re.sub(r'^[\-\*]\s+', '', text, flags=re.MULTILINE)
    # Linhas em branco excessivas
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


_NO_MARKDOWN = (
    "IMPORTANTE: Escreva em texto limpo, sem nenhum caractere especial de formatação. "
    "Não use #, ##, **, *, >, - como marcadores, --- ou qualquer sintaxe Markdown. "
    "Para separar seções, use apenas linhas em branco e letras MAIÚSCULAS no título da seção. "
    "Emojis são permitidos."
)


# ── Context & Objectives ──────────────────────────────────────────────────────

def extract_context_and_objectives(transcricao: str) -> tuple[str, str]:
    """
    Lê a transcrição e retorna (contexto_IBA, objetivos_redes_sociais).
    contexto = relatório IBA estruturado (WSI Initial Business Assessment)
    objetivos = metas específicas de marketing digital / redes sociais
    """

    # ── Prompt 1: Relatório IBA ──
    prompt_iba = f"""Aja como um Consultor Sênior da WSI especializado em diagnósticos empresariais (IBA - Initial Business Assessment). Sua tarefa é analisar a transcrição de uma reunião anexada abaixo e extrair informações detalhadas para preencher um relatório de avaliação preliminar.

DIRETRIZES DE ANÁLISE:
1. PROFUNDIDADE: Extraia o máximo de detalhes possível, incluindo nuances da fala do cliente e citações diretas relevantes que demonstrem pontos de dor ou objetivos.
2. TOM DE VOZ: Utilize uma linguagem formal, consultiva e profissional (Estilo WSI).
3. ESTRUTURA: Organize a saída estritamente em tópicos (bullet points) seguindo as categorias do guia IBA.

CATEGORIAS PARA EXTRAÇÃO (Baseadas no Guia IBA):

1. Histórico e Visão Geral Organizacional
(Origem, tempo de mercado, estrutura atual)

2. Revisão de Negócios (Produtos e Serviços)
(O que oferecem, diferenciais competitivos, mix de produtos)

3. Mercado e Competição
(Público-alvo, posicionamento e principais concorrentes mencionados)

4. Saúde Financeira
(Desempenho geral, faturamento, margens ou desafios financeiros citados)

5. Operações
(Processos internos, eficiência operacional e gargalos)

6. Marketing e Vendas
(Estratégias atuais, canais utilizados e desempenho comercial)

7. Recursos Humanos
(Satisfação com a equipe, estrutura organizacional e cultura)

8. Desafios Estratégicos e Metas
(Principais obstáculos para o crescimento e objetivos de curto/médio prazo)

9. Insights Adicionais
(Qualquer informação crítica que não se encaixe nas categorias acima)

INSTRUÇÃO ADICIONAL:
Se alguma informação não tiver sido mencionada na transcrição, indique como "[Informação não abordada na reunião]". Ao final, destaque as 3 maiores oportunidades de crescimento identificadas com base na conversa.

TRANSCRIÇÃO:
{transcricao[:7000]}"""

    # ── Prompt 2: Objetivos e Metas (IBA Marketing & Vendas) ──
    prompt_obj = f"""Aja como um Estrategista de Marketing e Vendas focado em Metodologia IBA. Sua missão é analisar a transcrição da reunião e extrair/estruturar a seção de "Objetivos e Metas" com precisão técnica.

DIRETRIZES DE EXTRAÇÃO:
1. IDENTIFICAÇÃO DE INTENÇÃO: Diferencie o que é um "Desejo" (ex: "quero vender mais") de um "Objetivo Estratégico" (ex: "expandir a participação no mercado B2B").
2. QUANTIFICAÇÃO: Sempre que o cliente mencionar números, prazos ou porcentagens, extraia-os com exatidão.
3. CONTEXTO DE MARKETING/VENDAS: Relacione as metas aos pilares de: Aquisição (Tráfego/Leads), Conversão (Vendas/Eficiência) e Retenção (LTV/Fidelização).

ESTRUTURA DA RESPOSTA:

1. OBJETIVOS DE CURTO PRAZO (0-3 meses)
Extraia metas imediatas mencionadas, como resolução de problemas operacionais ou campanhas específicas.

2. OBJETIVOS DE MÉDIO/LONGO PRAZO (6-12 meses)
Extraia visões de crescimento, faturamento esperado e expansão.

3. METAS ESPECÍFICAS DE MARKETING E VENDAS
Liste metas de tráfego, geração de leads, ticket médio ou redução de churn, se citadas.

4. DESAFIOS E IMPEDIMENTOS (Gaps)
O que o cliente disse que o impede de atingir essas metas hoje?

5. CITAÇÕES CHAVE
Transcreva aqui frases literais do cliente que resumam sua maior ambição ou maior medo.

INSTRUÇÃO ADICIONAL:
Se o objetivo citado for vago, sugira uma métrica (KPI) que poderia ser usada para medir esse objetivo, marcando como [Sugestão do Consultor].
Se alguma informação não foi mencionada, indique como [Informação não abordada na reunião].

TRANSCRIÇÃO:
{transcricao[:5000]}"""

    contexto  = _chat([{"role": "user", "content": prompt_iba}], max_tokens=2500, temperature=0.2)
    time.sleep(5)  # pausa entre chamadas para não bater rate limit
    objetivos = _chat([{"role": "user", "content": prompt_obj}], max_tokens=1500, temperature=0.2)

    return contexto.strip(), objetivos.strip()


# ── Themes ────────────────────────────────────────────────────────────────────

def _build_batches(
    n_comercial: int,
    n_institucional: int,
    n_informativo: int,
    n_engajamento: int = 0,
    n_cases: int = 0,
) -> list[tuple[str, str, int, int]]:
    """Divide as quantidades em sub-lotes de SUB_BATCH_SIZE."""
    batches: list[tuple[str, str, int, int]] = []
    configs = [
        ("Comercial",     "🔴", n_comercial,     1),
        ("Institucional", "🔵", n_institucional, 1 + n_comercial),
        ("Informativo",   "🟢", n_informativo,   1 + n_comercial + n_institucional),
        ("Engajamento",   "🟡", n_engajamento,   1 + n_comercial + n_institucional + n_informativo),
        ("Cases",         "🟣", n_cases,          1 + n_comercial + n_institucional + n_informativo + n_engajamento),
    ]
    for pilar, emoji, total, start in configs:
        if total <= 0:
            continue
        remaining, current = total, start
        while remaining > 0:
            size = min(SUB_BATCH_SIZE, remaining)
            batches.append((pilar, emoji, size, current))
            current += size
            remaining -= size
    return batches


def _generate_batch(
    context: str,
    pilar: str,
    emoji: str,
    quantidade: int,
    inicio: int,
) -> str:
    prompt = f"""Você é um estrategista de marketing digital sênior. Com base nos documentos abaixo, gere exatamente {quantidade} temas de conteúdo do pilar {pilar} para redes sociais.

{context}

INSTRUÇÕES:
- Gere exatamente {quantidade} temas DIFERENTES e ÚNICOS do pilar {emoji} {pilar}.
- NUNCA repita o mesmo tema — cada um deve abordar um ângulo diferente.
- Explore: produto, dor do cliente, solução, resultado, bastidores, cases, comparações, datas sazonais.
- Temas concretos, específicos e acionáveis, não genéricos.
- Varie os formatos: Card unico, Carrossel, Reels, Stories, Trafego Pago.
- Numere de {str(inicio).zfill(3)} ate {str(inicio + quantidade - 1).zfill(3)}.
- Escreva em portugues brasileiro.

FORMATO OBRIGATORIO — retorne APENAS a tabela Markdown, sem texto antes ou depois:
| Nº | Pilar | Tema | Formato Sugerido | Persona-Alvo |
|---|---|---|---|---|
| {str(inicio).zfill(3)} | {emoji} {pilar} | [tema especifico] | [formato] | [persona] |"""

    return _chat([{"role": "user", "content": prompt}], max_tokens=4000, temperature=0.8)


def generate_themes(
    client_name: str,
    contexto: str,
    objetivos: str,
    mapa: str,
    proposta: str,
    personas: str,
    n_comercial: int,
    n_institucional: int,
    n_informativo: int,
    n_engajamento: int = 0,
    n_cases: int = 0,
    progress_callback=None,  # fn(pilar, batch_num, total_batches)
) -> str:
    context_block = f"""CLIENTE: {client_name}

CONTEXTO DO NEGOCIO:
{contexto[:3000]}

OBJETIVOS:
{objetivos[:2000]}

MAPA DE EMPATIA:
{mapa[:3000]}

PROPOSTA DE VALOR:
{proposta[:3000]}

PERSONAS:
{personas[:3000]}"""

    batches = _build_batches(n_comercial, n_institucional, n_informativo, n_engajamento, n_cases)
    total = len(batches)
    all_rows: list[str] = []
    seen: set[str] = set()

    for i, (pilar, emoji, qtd, inicio) in enumerate(batches):
        if progress_callback:
            progress_callback(pilar, i + 1, total)

        if i > 0:
            time.sleep(4)  # respeita limite de 15 req/min do plano gratuito Gemini

        raw = _generate_batch(context_block, pilar, emoji, qtd, inicio)

        for line in raw.splitlines():
            if not line.startswith("|") or line.startswith("| Nº") or line.startswith("|---"):
                continue
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) < 3:
                continue
            key = parts[2].lower().strip()
            if key and key not in seen:
                seen.add(key)
                all_rows.append(line)

    header = "| Nº | Pilar | Tema | Formato Sugerido | Persona-Alvo |\n|---|---|---|---|---|\n"
    return header + "\n".join(all_rows)


# ── Caption ───────────────────────────────────────────────────────────────────

def generate_caption(
    theme: dict,
    formato: str,
    client_name: str,
    contexto: str,
    objetivos: str,
    mapa: str,
    proposta: str,
    personas: str,
    guia: str,
    tom: str = "Profissional",
    estilo: str = "Lista de Dicas",
) -> str:
    fmt_clean = formato.split(" ", 1)[1] if " " in formato else formato

    ctx = ""
    if proposta: ctx += f"PROPOSTA DE VALOR:\n{proposta[:3000]}\n\n"
    if personas: ctx += f"PERSONAS:\n{personas[:3000]}\n\n"
    if mapa:     ctx += f"MAPA DE EMPATIA (dores e desejos):\n{mapa[:2000]}\n\n"
    if contexto: ctx += f"CONTEXTO DO CLIENTE:\n{contexto[:1500]}\n\n"
    if objetivos: ctx += f"OBJETIVOS:\n{objetivos[:1000]}\n\n"

    # ── Regras concretas de escrita por tom ──────────────────────────────────────
    REGRAS_TOM = {
        "Profissional": (
            "Use linguagem tecnica mas acessivel. Cite dados, resultados ou fatos concretos sempre que possivel. "
            "Frases curtas e diretas. Prefira 'voce' ao 'a gente'. Sem informalidade excessiva. "
            "O leitor deve sentir que esta lendo algo de uma fonte confiavel e experiente."
        ),
        "Conversacional": (
            "Escreva exatamente como falaria com um amigo em uma conversa. Use 'a gente', contrações naturais, "
            "expressoes do dia a dia. Sem palavras rebuscadas. Pode usar reticencias para criar pausa. "
            "Cada frase deve soar como algo que uma pessoa real diria em voz alta."
        ),
        "Inspiracional": (
            "Comece com uma verdade que provoca reflexao ou um insight inesperado. Use metaforas e imagens mentais. "
            "Frases com ritmo — alterne frases curtas com frases longas. "
            "O leitor deve terminar o post querendo agir ou mudar algo na vida dele."
        ),
        "Educativo": (
            "Cada paragrafo deve ensinar algo acionavel. Use construcoes como 'O motivo e...', 'Isso acontece porque...', "
            "'A diferenca entre X e Y e...'. Explique o 'por que' antes do 'como'. "
            "Termine com uma aplicacao pratica que o leitor pode usar hoje."
        ),
        "Direto": (
            "Sem introducao, sem contexto, sem aquecimento. A primeira palavra ja e impacto ou oferta. "
            "Use verbos no imperativo: 'Faz', 'Para', 'Descobre', 'Entra'. "
            "Cada linha deve empurrar o leitor para a proxima acao. Sem enrolacao."
        ),
        "Emocional": (
            "Crie uma cena concreta — o leitor deve se ver dentro da historia. Use detalhes sensoriais: "
            "o que a pessoa viu, sentiu, pensou naquele momento. Nao diga a emocao — mostre ela. "
            "A virada emocional deve vir perto do final, antes do CTA."
        ),
        "Humoristico": (
            "Use o formato: setup (situacao normal) + subversao (virada inesperada). "
            "O humor vem da identificacao — o leitor ri porque ja passou por isso. "
            "Nunca force a piada. Se nao vier naturalmente, prefira ironia leve. "
            "Tom leve do inicio ao fim, mas com mensagem real por tras."
        ),
    }

    # ── Formula estrutural por estilo ─────────────────────────────────────────
    FORMULA_ESTILO = {
        "Storytelling": (
            "ESTRUTURA OBRIGATORIA:\n"
            "Linha 1-2: Contexto (quando, onde, quem — situa o leitor)\n"
            "Linha 3-4: Conflito (o problema ou desafio real)\n"
            "Linha 5-8: Desenvolvimento (o que aconteceu, o que tentou)\n"
            "Ultima linha: Virada ou licao — a transformacao\n"
            "CTA integrado na virada ou logo apos."
        ),
        "Lista de Dicas": (
            "ESTRUTURA OBRIGATORIA:\n"
            "Linha 1: Promessa com numero — ex: '5 erros que estao te custando clientes:'\n"
            "Itens numerados — maximo 2 linhas por item\n"
            "Cada item: problema ou dica + consequencia ou beneficio\n"
            "Ultimo item: o mais surpreendente ou contraintuitivo\n"
            "CTA apos a lista."
        ),
        "Pergunta + Resposta": (
            "ESTRUTURA OBRIGATORIA:\n"
            "Linha 1: Pergunta que a persona ja se fez (nao responda ainda)\n"
            "Linha 2: Subverta a resposta obvia — 'A maioria diria X. Mas a resposta e outra.'\n"
            "Desenvolvimento: a resposta real com argumento\n"
            "Ultima linha: pergunta de volta para o leitor ou CTA."
        ),
        "Antes e Depois": (
            "ESTRUTURA OBRIGATORIA:\n"
            "Abertura: contraste direto — 'Antes: [situacao ruim]. Depois: [resultado real].'\n"
            "Desenvolvimento: o que mudou, como mudou, por que mudou\n"
            "Seja especifico: use numeros, prazos, situacoes reais\n"
            "CTA: convide o leitor a ter o mesmo resultado."
        ),
        "Passo a Passo": (
            "ESTRUTURA OBRIGATORIA:\n"
            "Linha 1: Resultado prometido ao seguir os passos\n"
            "Passos numerados (Passo 1, Passo 2...): cada um com acao clara e objetiva\n"
            "Maximo 5 passos — se precisar de mais, agrupe\n"
            "Ultimo passo: o mais contraintuitivo ou surpreendente\n"
            "CTA: proximo passo natural apos ler."
        ),
        "Dado + Insight": (
            "ESTRUTURA OBRIGATORIA:\n"
            "Linha 1: Estatistica, numero ou fato impactante (real ou verossimil)\n"
            "Linha 2: O que esse numero REALMENTE significa para a persona\n"
            "Desenvolvimento: implicacao pratica — o que fazer com essa informacao\n"
            "Ultima linha: insight ou provocacao que fica na cabeca\n"
            "CTA conectado ao insight."
        ),
        "CTA Direto": (
            "ESTRUTURA OBRIGATORIA:\n"
            "Linha 1: Verbo imperativo + beneficio claro — sem introducao\n"
            "Linha 2-3: Prova ou razao rapida (por que acreditar)\n"
            "Linha 4: CTA especifico e facil de executar\n"
            "Repita o CTA de forma diferente no final\n"
            "Sem paragrafo longo. Tudo curto e direto."
        ),
    }

    regras_tom   = REGRAS_TOM.get(tom, TONS.get(tom, ""))
    formula_est  = FORMULA_ESTILO.get(estilo, ESTILOS.get(estilo, ""))

    # ── Gatilho e CTA por pilar ───────────────────────────────────────────────
    pilar_lower = theme['pilar'].lower()
    if "comercial" in pilar_lower:
        gatilho      = "prova social, escassez ou urgencia — faca o leitor sentir que perder essa oportunidade e um erro"
        cta_sugerido = "direcione para WhatsApp, link na bio ou 'Comenta X que te mando o link'"
    elif "institucional" in pilar_lower:
        gatilho      = "pertencimento e autoridade — mostre os bastidores, os valores reais, as pessoas por tras da marca"
        cta_sugerido = "incentive curtir, seguir, compartilhar ou marcar alguem que precisa ver isso"
    elif "engajamento" in pilar_lower:
        gatilho      = "identificacao e provocacao — faca o leitor pensar 'isso e exatamente comigo' e querer responder"
        cta_sugerido = "faca uma pergunta direta e especifica no final — ex: 'E voce, ja passou por isso? Comenta aqui'"
    elif "cases" in pilar_lower:
        gatilho      = "prova social concreta — use numeros reais, situacao antes/depois, detalhe especifico que da credibilidade"
        cta_sugerido = "convide a conhecer mais ou entrar em contato — ex: 'Quer um resultado parecido? Chama a gente no link da bio'"
    else:
        gatilho      = "curiosidade e utilidade — entregue valor real que o leitor vai querer guardar e compartilhar"
        cta_sugerido = "incentive salvar o post ou compartilhar com alguem especifico — ex: 'Manda pra alguem que precisa ler isso'"

    # ── Exclusão de seções de outros formatos ────────────────────────────────
    _nao_usar = []
    if "Carrossel" not in fmt_clean: _nao_usar.append("Cards do Carrossel")
    if "Reels"     not in fmt_clean: _nao_usar.append("Roteiro de Reels")
    if "Stories"   not in fmt_clean: _nao_usar.append("Sequencia de Stories")
    if "Trafego" not in fmt_clean and "Pago" not in fmt_clean: _nao_usar.append("Anuncio Pago")
    exclusao = f"NAO inclua: {', '.join(_nao_usar)}." if _nao_usar else ""

    prompt = f"""Voce e um copywriter senior com profundo conhecimento do mercado brasileiro.
NAO escreva como uma IA generica. Escreva como um profissional que conhece este cliente de perto.
Crie exatamente UM conteudo. Apenas um.

{_NO_MARKDOWN}

FORMATO: {fmt_clean} — {exclusao}

════════════════════════════════
TOM DE VOZ: {tom.upper()}
════════════════════════════════
{regras_tom}

TESTE INTERNO: antes de entregar, releia e pergunte — "isso soa como tom {tom}?"
Se a resposta for nao, reescreva ate soar.

════════════════════════════════
ESTILO DE ESTRUTURA: {estilo.upper()}
════════════════════════════════
{formula_est}

════════════════════════════════
CLIENTE: {client_name}
════════════════════════════════
{ctx}

════════════════════════════════
SOLICITACAO
════════════════════════════════
Tema: {theme['tema']}
Pilar: {theme['pilar']}
Formato: {fmt_clean}
Persona-alvo: {theme['persona']}
Gatilho mental a usar: {gatilho}
CTA: {cta_sugerido}

════════════════════════════════
REGRAS ABSOLUTAS
════════════════════════════════
PROIBIDO usar estas palavras ou expressoes:
"solucoes inovadoras", "excelencia", "qualidade superior", "parceria estrategica",
"expertise", "compromisso", "dedicacao", "transforme sua vida", "nao perca essa oportunidade"

PROIBIDO estrutura generica: nao comece com "Voce sabia que..." nem com "Ola!" nem com o nome da empresa.

OBRIGATORIO:
- Hook: primeira linha para o scroll em menos de 3 segundos — maximo 10 palavras
- Legenda: maximo 750 caracteres
- Paragrafos: maximo 2 linhas cada — use linha em branco entre paragrafos
- Emojis: use com criterio, apenas onde reforcem a mensagem
- Soar como humano, nao como IA

════════════════════════════════
ENTREGUE NESTA ORDEM:
════════════════════════════════

HOOK
[uma unica linha — maximo 10 palavras — sem introducao — impacto imediato]

LEGENDA
[texto completo seguindo o estilo {estilo} — CTA no final — maximo 750 caracteres]

HASHTAGS
[3 a 5 hashtags especificas do nicho, nao genericas como #marketing ou #negocios]

INSTRUCOES PARA DESIGN
[orientacoes visuais concretas: o que mostrar na imagem, texto na arte, cor de destaque]

{"CARDS DO CARROSSEL" + chr(10) + "[Card 1 (capa): hook visual impactante | Cards 2 a N: um ponto por card, texto curto | Ultimo card: CTA visual]" if "Carrossel" in fmt_clean else ""}
{"ROTEIRO DO REELS" + chr(10) + "[0-3s: hook visual que prende | 4-15s: desenvolvimento rapido | Ultimos 3s: CTA falado + texto na tela | Trilha sugerida]" if "Reels" in fmt_clean else ""}
{"SEQUENCIA DE STORIES" + chr(10) + "[Story 1: gancho com pergunta ou afirmacao forte | Stories 2-4: desenvolvimento um por um | Story 5: CTA com recurso interativo (enquete, link, caixa de perguntas)]" if "Stories" in fmt_clean else ""}
{"ANUNCIO PAGO" + chr(10) + "[Texto primario: max 125 car. | Headline: max 40 car. | Descricao: max 30 car. | Botao CTA | Publico sugerido com interesses especificos]" if "Trafego" in fmt_clean or "Pago" in fmt_clean else ""}"""

    raw = _chat([{"role": "user", "content": prompt}], max_tokens=2000, temperature=0.75)
    return clean_text(raw)


# ── Refine ────────────────────────────────────────────────────────────────────

def refine_caption(caption: str, instructions: str) -> str:
    prompt = f"""Você é um especialista em copywriting para redes sociais.

{_NO_MARKDOWN}

Abaixo está um conteúdo já criado. Aplique os ajustes solicitados.

AJUSTES SOLICITADOS:
{instructions}

CONTEUDO ATUAL:
{caption}

INSTRUCOES:
- Aplique APENAS os ajustes pedidos. Nao altere o restante.
- Mantenha a mesma estrutura e secoes do conteudo original.
- Escreva em portugues brasileiro.
- Retorne o conteudo completo e corrigido, sem comentarios adicionais."""

    raw = _chat([{"role": "user", "content": prompt}], max_tokens=2000, temperature=0.5)
    return clean_text(raw)
