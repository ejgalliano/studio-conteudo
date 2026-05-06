from groq import Groq
import os


def _groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY não encontrada. Verifique o arquivo .env")
    return Groq(api_key=api_key)


def generate_themes(client_name: str, mapa_empatia: str, proposta_valor: str, personas: str, objetivos: str) -> str:
    client = _groq_client()

    prompt = f"""Você é um estrategista de marketing digital sênior. Com base nos documentos estratégicos do cliente abaixo, gere uma lista de 350 temas de conteúdo para redes sociais.

## CLIENTE: {client_name}

## OBJETIVOS:
{objetivos}

## MAPA DE EMPATIA:
{mapa_empatia}

## PROPOSTA DE VALOR:
{proposta_valor}

## PERSONAS:
{personas}

## INSTRUÇÕES:
Gere exatamente 350 temas distribuídos assim:
- 🔴 COMERCIAL (30% = ~105 temas): venda direta, produtos, ofertas, captação, depoimentos, provas sociais
- 🔵 INSTITUCIONAL (30% = ~105 temas): história, bastidores, valores, equipe, credibilidade, posicionamento
- 🟢 EDUCATIVO (40% = ~140 temas): dicas práticas, dúvidas frequentes, mitos e verdades, tutoriais, tendências

## FORMATO OBRIGATÓRIO (tabela markdown):
Retorne APENAS a tabela, sem texto antes ou depois. Use exatamente este formato:

| Nº | Pilar | Tema | Formato Sugerido | Persona-Alvo |
|---|---|---|---|---|
| 001 | 🔴 Comercial | [tema] | [Card único / Carrossel / Reels / Stories / Tráfego Pago] | [persona] |
| 002 | 🔵 Institucional | [tema] | [formato] | [persona] |
| 003 | 🟢 Educativo | [tema] | [formato] | [persona] |

Regras:
- Temas concretos, específicos e acionáveis — não genéricos
- Varie os formatos sugeridos entre os 5 tipos
- Persona-alvo baseada nas personas fornecidas
- Numere de 001 até 350
- Escreva em português brasileiro"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=8000,
        temperature=0.8,
    )

    return response.choices[0].message.content


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

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
        temperature=0.7,
    )

    return response.choices[0].message.content
