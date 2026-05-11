"""
Todas as chamadas à API Groq.
Saídas sem caracteres especiais markdown para facilitar cópia.
"""
import os
import re
from groq import Groq

from constants import MODEL_PRIMARY, MODEL_FALLBACKS, SUB_BATCH_SIZE


# ── Client & chat ─────────────────────────────────────────────────────────────

def _client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY não encontrada. Verifique o arquivo .env")
    return Groq(api_key=api_key)


def _chat(messages: list, max_tokens: int = 2000, temperature: float = 0.7) -> str:
    """Tenta modelo principal; em rate-limit usa fallbacks."""
    client = _client()
    last_error = None
    for model in [MODEL_PRIMARY] + MODEL_FALLBACKS:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return resp.choices[0].message.content
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                last_error = e
                continue
            raise
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
    Lê a transcrição e retorna (contexto, objetivos) como texto limpo.
    contexto = quem é o cliente (mercado, produtos, diferenciais, tom de voz)
    objetivos = o que quer alcançar nas redes sociais
    """
    prompt = f"""Você é um estrategista de marketing digital. Leia a transcrição abaixo e extraia duas coisas:

1. CONTEXTO DO CLIENTE: quem é, em qual mercado atua, o que vende, diferenciais, tom de voz, público-alvo.
2. OBJETIVOS: o que o cliente quer alcançar com as redes sociais, metas específicas, restrições e preferências.

{_NO_MARKDOWN}

TRANSCRIÇÃO:
{transcricao[:6000]}

Retorne EXATAMENTE neste formato:

CONTEXTO
[Texto corrido descrevendo quem é o cliente, mercado de atuação, produtos e serviços, diferenciais, público-alvo e tom de voz. Mínimo 5 linhas.]

OBJETIVOS
[Texto corrido com os objetivos nas redes sociais, metas, o que não fazer e preferências mencionadas. Mínimo 3 linhas.]

Seja específico. Use apenas informações da transcrição. Não invente dados."""

    raw = _chat([{"role": "user", "content": prompt}], max_tokens=1500, temperature=0.3)
    raw = clean_text(raw)

    contexto, objetivos = "", ""
    if "OBJETIVOS" in raw:
        partes = raw.split("OBJETIVOS", 1)
        contexto = partes[0].replace("CONTEXTO", "").strip()
        objetivos = partes[1].strip()
    else:
        contexto = raw

    return contexto, objetivos


# ── Themes ────────────────────────────────────────────────────────────────────

def _build_batches(
    n_comercial: int,
    n_institucional: int,
    n_informativo: int,
) -> list[tuple[str, str, int, int]]:
    """Divide as quantidades em sub-lotes de SUB_BATCH_SIZE."""
    batches: list[tuple[str, str, int, int]] = []
    configs = [
        ("Comercial",     "🔴", n_comercial,     1),
        ("Institucional", "🔵", n_institucional, 1 + n_comercial),
        ("Informativo",   "🟢", n_informativo,   1 + n_comercial + n_institucional),
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
    progress_callback=None,  # fn(pilar, batch_num, total_batches)
) -> str:
    context_block = f"""CLIENTE: {client_name}

CONTEXTO:
{contexto[:1500]}

OBJETIVOS:
{objetivos[:1000]}

MAPA DE EMPATIA:
{mapa[:1200]}

PROPOSTA DE VALOR:
{proposta[:1200]}

PERSONAS:
{personas[:1200]}"""

    batches = _build_batches(n_comercial, n_institucional, n_informativo)
    total = len(batches)
    all_rows: list[str] = []
    seen: set[str] = set()

    for i, (pilar, emoji, qtd, inicio) in enumerate(batches):
        if progress_callback:
            progress_callback(pilar, i + 1, total)

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
) -> str:
    fmt_clean = formato.split(" ", 1)[1] if " " in formato else formato

    ctx = ""
    if proposta: ctx += f"PROPOSTA DE VALOR:\n{proposta[:2000]}\n\n"
    if personas: ctx += f"PERSONAS:\n{personas[:2000]}\n\n"
    if mapa:     ctx += f"MAPA DE EMPATIA:\n{mapa[:1500]}\n\n"
    if contexto: ctx += f"CONTEXTO:\n{contexto[:1000]}\n\n"
    if objetivos: ctx += f"OBJETIVOS:\n{objetivos[:800]}\n\n"

    prompt = f"""Você é um especialista em marketing de conteúdo para redes sociais. Crie um conteúdo completo para o tema abaixo.

{_NO_MARKDOWN}

GUIA DE CRIAÇÃO:
{guia}

CLIENTE: {client_name}
{ctx}

SOLICITACAO:
Tema: {theme['tema']}
Pilar: {theme['pilar']}
Formato: {fmt_clean}
Persona-alvo: {theme['persona']}

Siga a estrutura do guia para o formato {fmt_clean}. Inclua obrigatoriamente:

TEMA
[nome do tema]

PILAR
[nome do pilar]

FORMATO
[nome do formato]

PERSONA-ALVO
[persona]

OBJETIVO
[objetivo do post]

HOOK
[frase de abertura impactante, maximo 10 palavras]

TITULO DO POST
[titulo chamativo]

LEGENDA
[legenda completa com emojis, CTA, maximo 750 caracteres]

HASHTAGS
[ate 5 hashtags]

INSTRUCOES PARA DESIGN
[orientacoes visuais]

{"CARDS DO CARROSSEL" + chr(10) + "[Card 1: capa — Card 2... — Ultimo card: CTA]" if "Carrossel" in fmt_clean else ""}
{"ROTEIRO DO REELS" + chr(10) + "[Cena 1, Cena 2... CTA final — Trilha sugerida]" if "Reels" in fmt_clean else ""}
{"SEQUENCIA DE STORIES" + chr(10) + "[Story 1 a 5 com recurso interativo de cada]" if "Stories" in fmt_clean else ""}
{"ANUNCIO PAGO" + chr(10) + "[Texto primario 125 car. — Headline 40 car. — Descricao 30 car. — Botao CTA — Publico sugerido]" if "Trafego" in fmt_clean or "Pago" in fmt_clean else ""}

Escreva em portugues brasileiro. Tom: profissional, acessivel, direto — nunca corporativo."""

    raw = _chat([{"role": "user", "content": prompt}], max_tokens=2000, temperature=0.7)
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
