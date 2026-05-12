GITHUB_REPO    = "ejgalliano/studio-conteudo"
DELETED_FILE   = "_outputs/_deleted.txt"

MODEL_PRIMARY   = "gemini-2.0-flash"
MODEL_FALLBACKS = ["gemini-1.5-flash-latest", "gemini-1.5-flash-8b-latest"]

# Máximo de temas por chamada à API (cabe em max_tokens=4000)
SUB_BATCH_SIZE = 35

FORMATS = [
    "📱 Card Único",
    "🎠 Carrossel",
    "🎬 Reels",
    "📖 Stories",
    "💰 Tráfego Pago",
]

PILARES = ["Comercial", "Institucional", "Informativo"]
PILAR_EMOJI = {
    "Comercial":     "🔴",
    "Institucional": "🔵",
    "Informativo":   "🟢",
}

# ── Tom de voz ────────────────────────────────────────────────────────────────
TONS = {
    "Profissional":          "Credibilidade, autoridade e clareza. Ideal para negócios, serviços técnicos, consultoria e anúncios de resultados.",
    "Conversacional":        "Proximidade, naturalidade e humanização. Ideal para Stories, bastidores e dia a dia.",
    "Inspiracional":         "Motivar e engajar emocionalmente. Ideal para posts de mentalidade, posicionamento e narrativa pessoal.",
    "Educativo":             "Ensinar, explicar e gerar valor. Ideal para tutoriais, awareness e Reels educativos.",
    "Humorístico":           "Viralizar, entreter e gerar identificação. Ideal para nichos mais leves, tendências e memes.",
    "Direto":                "Conversões e CTAs claros. Ideal para anúncios, ofertas e captação de leads.",
    "Emocional":             "Conexão profunda e storytelling. Ideal para campanhas de awareness, marca pessoal e cases.",
    "Analítico/Estratégico": "Reforçar inteligência e tomada de decisão. Ideal para conteúdo avançado, marketing e gestão.",
    "Energético/Motivador":  "Gerar hype e estimular ação. Ideal para lançamentos, anúncios e trends aceleradas.",
}

# ── Estilo de estrutura ───────────────────────────────────────────────────────
ESTILOS = {
    "Storytelling":          "Narrativa, jornada e transformação. Ex: 'Há alguns anos, um cliente me procurou porque...'",
    "Bullet Points":         "Conteúdo escaneável, listas e dicas rápidas em tópicos curtos.",
    "Microtexto":            "Short caption para Reels dinâmicos e impacto imediato. Máximo 2-3 linhas.",
    "Long Form":             "Legenda longa com storytelling profundo, educação ou bastidores.",
    "Memeável":              "Humor, identificação e trends. Tom leve e descontraído.",
    "Pergunta Inicial":      "Abre com pergunta para gerar engajamento e reflexão.",
    "Call to Action (CTA)":  "Foco total em conversão e direcionamento. Ex: 'Comente X que envio o link.'",
    "Valor Direto":          "Conteúdo objetivo sem rodeios. Ex: '5 erros comuns e como evitar.'",
    "Autoridade":            "Prova social e expertise. Destaca resultados, números e experiência.",
    "Motivacional + Dados":  "Mistura inspiração com inteligência e dados concretos.",
}

# ── Formato visual ────────────────────────────────────────────────────────────
FORMATOS_VISUAIS = [
    "Frases de impacto",
    "Quebra de linhas com respiro",
    "Emojis estratégicos",
    "Estilo carrossel (legenda complementa os slides)",
    "Mini copywriting com gatilhos (prova, urgência, benefício)",
    "Formato FAQ",
    "Checklist",
    "Mito vs. Verdade",
    "Antes e Depois",
    "Guia passo a passo",
]

# Arquivos de cada cliente no GitHub
CLIENT_FILES = [
    "00-contexto.md",
    "00-objetivos.md",
    "01-mapa-empatia.md",
    "02-proposta-valor.md",
    "03-personas.md",
    "04-lista-temas.md",
]
