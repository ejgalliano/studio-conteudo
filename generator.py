"""
Todas as chamadas à API Groq (geração de temas, legendas e objetivos).
"""
import os
from groq import Groq

from constants import MODEL_PRIMARY, MODEL_FALLBACKS, THEME_BATCHES


# ── Client ────────────────────────────────────────────────────────────────────

def _client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY não encontrada. Verifique o arquivo .env")
    return Groq(api_key=api_key)


def _chat(messages: list, max_tokens: int = 2000, temperature: float = 0.7) -> str:
    """Tenta o modelo principal; em caso de rate limit, usa fallbacks."""
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
        "⚠️ Limite diário de tokens atingido em todos os modelos.\n\n"
        "O plano gratuito do Groq permite 100.000 tokens/dia. "
        "O limite reseta à meia-noite (horário de Brasília).\n\n"
        "Tente novamente mais tarde ou amanhã."
    ) from last_error


# ── Objectives ────────────────────────────────────────────────────────────────

def extract_objectives(transcricao: str) -> str:
    prompt = f"""Você é um estrategista de marketing digital. Leia a transcrição de briefing abaixo e extraia um resumo estruturado dos objetivos do cliente.

## TRANSCRIÇÃO:
{transcricao[:6000]}

## RETORNE exatamente neste formato (em português brasileiro):

## Objetivo Principal
[objetivo central do cliente com as redes sociais]

## Objetivos Específicos
1. [objetivo]
2. [objetivo]
3. [objetivo]

## Público-Alvo
[descrição do público principal]

## Produtos e Serviços
[o que o cliente vende, ticket médio se mencionado]

## Tom de Voz
[como a marca deve soar: formal, descontraído, técnico, etc.]

## Restrições e Preferências
[o que NÃO fazer, preferências mencionadas]

## Diferenciais
[o que diferencia esse cliente da concorrência]

Seja específico e use informações reais da transcrição. Não invente dados."""

    return _chat([{"role": "user", "content": prompt}], max_tokens=1500, temperature=0.3)


# ── Themes ────────────────────────────────────────────────────────────────────

def _build_context(client_name: str, objetivos: str, mapa: str, proposta: str, personas: str) -> str:
    return f"""## CLIENTE: {client_name}
## OBJETIVOS:
{objetivos[:1500]}
## MAPA DE EMPATIA:
{mapa[:1500]}
## PROPOSTA DE VALOR:
{proposta[:1500]}
## PERSONAS:
{personas[:1500]}"""


def _generate_batch(context: str, pilar: str, emoji: str, quantidade: int, inicio: int) -> str:
    prompt = f"""Você é um estrategista de marketing digital sênior. Com base nos documentos abaixo, gere exatamente {quantidade} temas de conteúdo do pilar {pilar} para redes sociais.

{context}

## INSTRUÇÕES:
- Gere exatamente {quantidade} temas DIFERENTES e ÚNICOS do pilar {emoji} {pilar}.
- NUNCA repita o mesmo tema ou variação mínima — cada tema deve abordar um ângulo diferente.
- Explore: produto, dor do cliente, solução, resultado, bastidores, cases, comparações, datas.
- Temas concretos, específicos e acionáveis — não genéricos.
- Varie os formatos: Card único, Carrossel, Reels, Stories, Tráfego Pago.
- Numere de {str(inicio).zfill(3)} até {str(inicio + quantidade - 1).zfill(3)}.
- Escreva em português brasileiro.

## FORMATO OBRIGATÓRIO — retorne APENAS a tabela Markdown, sem texto antes ou depois:
| Nº | Pilar | Tema | Formato Sugerido | Persona-Alvo |
|---|---|---|---|---|
| {str(inicio).zfill(3)} | {emoji} {pilar} | [tema específico] | [formato] | [persona] |"""

    return _chat([{"role": "user", "content": prompt}], max_tokens=4000, temperature=0.8)


def generate_themes(
    client_name: str,
    objetivos: str,
    mapa: str,
    proposta: str,
    personas: str,
    progress_callback=None,   # fn(pilar, batch_num, total_batches)
) -> str:
    context = _build_context(client_name, objetivos, mapa, proposta, personas)
    all_rows: list[str] = []
    seen: set[str] = set()
    current_pilar = None
    total = len(THEME_BATCHES)

    for i, (pilar, emoji, qtd, inicio) in enumerate(THEME_BATCHES):
        if pilar != current_pilar:
            current_pilar = pilar

        if progress_callback:
            progress_callback(pilar, i + 1, total)

        raw = _generate_batch(context, pilar, emoji, qtd, inicio)

        for line in raw.splitlines():
            if not line.startswith("|"):
                continue
            if line.startswith("| Nº") or line.startswith("|---"):
                continue
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) < 3:
                continue
            tema_key = parts[2].lower().strip()
            if tema_key and tema_key not in seen:
                seen.add(tema_key)
                all_rows.append(line)

    header = "| Nº | Pilar | Tema | Formato Sugerido | Persona-Alvo |\n|---|---|---|---|---|\n"
    return header + "\n".join(all_rows)


# ── Caption ───────────────────────────────────────────────────────────────────

def generate_caption(
    theme: dict,
    formato: str,
    client_name: str,
    context: dict[str, str],
    guia: str,
) -> str:
    formato_clean = formato.split(" ", 1)[1] if " " in formato else formato

    ctx_parts = []
    if context.get("02-proposta-valor.md"):
        ctx_parts.append(f"## PROPOSTA DE VALOR:\n{context['02-proposta-valor.md'][:2500]}")
    if context.get("03-personas.md"):
        ctx_parts.append(f"## PERSONAS:\n{context['03-personas.md'][:2500]}")
    if context.get("01-mapa-empatia.md"):
        ctx_parts.append(f"## MAPA DE EMPATIA:\n{context['01-mapa-empatia.md'][:1500]}")

    prompt = f"""Você é um estrategista de marketing digital sênior especializado em conteúdo para redes sociais.
Crie um conteúdo completo seguindo rigorosamente o guia e o contexto do cliente abaixo.

## GUIA DE CRIAÇÃO DE LEGENDAS:
{guia}

## CONTEXTO DO CLIENTE — {client_name}:
{chr(10).join(ctx_parts)}

## SOLICITAÇÃO:
Crie um conteúdo completo para o tema abaixo:
- **Tema:** {theme['tema']}
- **Pilar:** {theme['pilar']}
- **Formato:** {formato_clean}
- **Persona-alvo:** {theme['persona']}

Siga EXATAMENTE a estrutura de entrega definida no guia para o formato "{formato_clean}".

Inclua obrigatoriamente:
- TEMA, PILAR, FORMATO, PERSONA-ALVO, OBJETIVO
- HOOK (frase de abertura impactante, máx. 10 palavras)
- TÍTULO DO POST
- LEGENDA completa (com emojis, CTA e máx. 750 caracteres)
- HASHTAGS (até 5)
- INSTRUÇÕES PARA DESIGN

Formatos especiais:
- Carrossel: descreva cada card (Card 1 capa, Card 2..., Último card CTA)
- Reels: roteiro com cenas e trilha sugerida
- Stories: sequência de 3 a 5 stories com recurso interativo de cada um
- Tráfego Pago: Texto primário (125 car.), Headline (40 car.), Descrição (30 car.), Botão CTA, Público sugerido

Escreva em português brasileiro. Tom: profissional, acessível, direto — nunca corporativo."""

    return _chat([{"role": "user", "content": prompt}], max_tokens=2000, temperature=0.7)


# ── Refine caption ────────────────────────────────────────────────────────────

def refine_caption(caption: str, instructions: str) -> str:
    prompt = f"""Você é um especialista em copywriting para redes sociais.
Abaixo está um conteúdo já criado. O cliente pediu os seguintes ajustes:

## AJUSTES SOLICITADOS:
{instructions}

## CONTEÚDO ATUAL:
{caption}

## INSTRUÇÕES:
- Aplique APENAS os ajustes solicitados. Não altere o que não foi pedido.
- Mantenha o mesmo formato e estrutura do conteúdo original.
- Escreva em português brasileiro.
- Retorne o conteúdo completo já corrigido, sem comentários adicionais."""

    return _chat([{"role": "user", "content": prompt}], max_tokens=2000, temperature=0.5)
