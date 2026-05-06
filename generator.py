from groq import Groq
import os


def generate_caption(theme: dict, formato: str, client_name: str, client_context: dict, guia: str) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY não encontrada. Verifique o arquivo .env")

    client = Groq(api_key=api_key)

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

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
        temperature=0.7,
    )

    return response.choices[0].message.content
