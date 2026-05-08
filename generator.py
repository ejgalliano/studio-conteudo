from groq import Groq
import os

MODELS_PRIMARY = "llama-3.3-70b-versatile"
MODELS_FALLBACK = ["llama-3.1-8b-instant", "gemma2-9b-it"]


def _groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY não encontrada. Verifique o arquivo .env")
    return Groq(api_key=api_key)


def _chat_with_fallback(client, messages, max_tokens=2000, temperature=0.7):
    """Try primary model, fall back to smaller models on rate limit (429)."""
    models = [MODELS_PRIMARY] + MODELS_FALLBACK
    last_error = None
    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate_limit" in err_str.lower() or "Rate limit" in err_str:
                last_error = e
                continue
            raise
    # All models exhausted
    raise RuntimeError(
        "⚠️ Limite diário de tokens atingido em todos os modelos.\n\n"
        "O plano gratuito do Groq permite 100.000 tokens por dia. "
        "O limite será resetado à meia-noite (horário de São Paulo).\n\n"
        "Tente novamente amanhã ou acesse groq.com para aumentar seu limite."
    ) from last_error


def extract_objectives(transcricao: str) -> str:
    client = _groq_client()
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

    return _chat_with_fallback(client, [{"role": "user", "content": prompt}], max_tokens=1500, temperature=0.3)


def _build_context(client_name: str, mapa_empatia: str, proposta_valor: str, personas: str, objetivos: str) -> str:
    # Truncate each doc to avoid token limit on free tier
    return f"""## CLIENTE: {client_name}
## OBJETIVOS:
{objetivos[:1500]}
## MAPA DE EMPATIA:
{mapa_empatia[:1500]}
## PROPOSTA DE VALOR:
{proposta_valor[:1500]}
## PERSONAS:
{personas[:1500]}"""


def _generate_themes_batch(client, context: str, pilar: str, emoji: str, quantidade: int, inicio: int) -> str:
    prompt = f"""Você é um estrategista de marketing digital sênior. Com base nos documentos abaixo, gere exatamente {quantidade} temas de conteúdo do pilar {pilar} para redes sociais.

{context}

## INSTRUÇÕES:
Gere exatamente {quantidade} temas do pilar {emoji} {pilar}.
Temas concretos, específicos e acionáveis — não genéricos.
Varie os formatos: Card único, Carrossel, Reels, Stories, Tráfego Pago.
Persona-alvo baseada nas personas fornecidas.
Numere de {str(inicio).zfill(3)} até {str(inicio + quantidade - 1).zfill(3)}.
Escreva em português brasileiro.

## FORMATO OBRIGATÓRIO — retorne APENAS a tabela, sem texto antes ou depois:
| Nº | Pilar | Tema | Formato Sugerido | Persona-Alvo |
|---|---|---|---|---|
| {str(inicio).zfill(3)} | {emoji} {pilar} | [tema específico] | [formato] | [persona] |"""

    return _chat_with_fallback(client, [{"role": "user", "content": prompt}], max_tokens=4000, temperature=0.8)


def generate_themes(client_name: str, mapa_empatia: str, proposta_valor: str, personas: str, objetivos: str, progress_callback=None) -> str:
    client = _groq_client()
    context = _build_context(client_name, mapa_empatia, proposta_valor, personas, objetivos)

    batches = [
        ("Comercial",     "🔴", 105,  1),
        ("Institucional", "🔵", 105, 106),
        ("Educativo",     "🟢", 140, 211),
    ]

    all_rows = []
    for pilar, emoji, qtd, inicio in batches:
        if progress_callback:
            progress_callback(pilar)
        result = _generate_themes_batch(client, context, pilar, emoji, qtd, inicio)
        # Extract only table rows
        for line in result.splitlines():
            if line.startswith("|") and not line.startswith("| Nº") and not line.startswith("|---"):
                all_rows.append(line)

    header = "| Nº | Pilar | Tema | Formato Sugerido | Persona-Alvo |\n|---|---|---|---|---|\n"
    return header + "\n".join(all_rows)


def generate_caption(theme: dict, formato: str, client_name: str, client_context: dict, guia: str) -> str:
    client = _groq_client()

    formato_clean = formato.split(" ", 1)[1] if " " in formato else formato

    context_parts = []
    if "02-proposta-valor.md" in client_context:
        context_parts.append(f"## PROPOSTA DE VALOR:\n{client_context['02-proposta-valor.md'][:2500]}")
    if "03-personas.md" in client_context:
        context_parts.append(f"## PERSONAS:\n{client_context['03-personas.md'][:2500]}")
    if "01-mapa-empatia.md" in client_context:
        context_parts.append(f"## MAPA DE EMPATIA:\n{client_context['01-mapa-empatia.md'][:1500]}")

    context_text = "\n\n".join(context_parts)

    prompt = f"""Você é um estrategista de marketing digital sênior especializado em conteúdo para redes sociais. \
Crie um conteúdo completo seguindo rigorosamente o guia e o contexto do cliente abaixo.

## GUIA DE CRIAÇÃO DE LEGENDAS:
{guia}

## CONTEXTO DO CLIENTE — {client_name}:
{context_text}

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
- Se Carrossel: descreva o conteúdo de cada card (Card 1 capa, Card 2..., Último card CTA)
- Se Reels: roteiro com cenas (Cena 1, Cena 2..., CTA final) e trilha sugerida
- Se Stories: sequência de 3 a 5 stories com recurso interativo de cada um
- Se Tráfego Pago: Texto primário (125 car.), Headline (40 car.), Descrição (30 car.), Botão CTA, Público sugerido

Escreva em português brasileiro. Tom: profissional, acessível, direto ao ponto. \
Reflita o tom de voz do cliente (confiante, experiente, próximo — nunca corporativo)."""

    return _chat_with_fallback(client, [{"role": "user", "content": prompt}], max_tokens=2000, temperature=0.7)


def refine_caption(caption: str, instrucoes: str) -> str:
    client = _groq_client()
    prompt = f"""Você é um especialista em copywriting para redes sociais.
Abaixo está um conteúdo já criado para um post. O cliente pediu os seguintes ajustes:

## AJUSTES SOLICITADOS:
{instrucoes}

## CONTEÚDO ATUAL:
{caption}

## INSTRUÇÕES:
- Aplique APENAS os ajustes solicitados. Não mude o que não foi pedido.
- Mantenha o mesmo formato e estrutura do conteúdo original.
- Escreva em português brasileiro.
- Retorne o conteúdo completo já corrigido, sem comentários adicionais."""

    return _chat_with_fallback(client, [{"role": "user", "content": prompt}], max_tokens=2000, temperature=0.5)
