GITHUB_REPO    = "ejgalliano/studio-conteudo"
DELETED_FILE   = "_outputs/_deleted.txt"

MODEL_PRIMARY   = "gemini-2.0-flash"
MODEL_FALLBACKS = ["gemini-2.0-flash-lite"]

# Máximo de temas por chamada à API (cabe em max_tokens=4000)
SUB_BATCH_SIZE = 35

FORMATS = [
    "📱 Card Único",
    "🎠 Carrossel",
    "🎬 Reels",
    "📖 Stories",
    "💰 Tráfego Pago",
]

PILARES = ["Comercial", "Institucional", "Informativo", "Engajamento", "Cases"]
PILAR_EMOJI = {
    "Comercial":     "🔴",
    "Institucional": "🔵",
    "Informativo":   "🟢",
    "Engajamento":   "🟡",
    "Cases":         "🟣",
}

# ── Tom de voz (7 principais) ─────────────────────────────────────────────────
TONS = {
    "Profissional":   "Autoridade, credibilidade e clareza. Ideal para B2B, consultoria, serviços técnicos e apresentação de resultados.",
    "Conversacional": "Próximo, natural e humano. Ideal para Stories, bastidores, dia a dia e humanização da marca.",
    "Inspiracional":  "Motivador e emocionante. Ideal para posicionamento, marca pessoal e conteúdo de mentalidade.",
    "Educativo":      "Ensina, explica e gera valor genuíno. Ideal para tutoriais, dicas e conteúdo de awareness.",
    "Direto":         "Objetivo, sem rodeios, foco em conversão. Ideal para anúncios, ofertas e CTAs de captação.",
    "Emocional":      "Conexão profunda via narrativa e storytelling. Ideal para campanhas, cases e marca pessoal.",
    "Humorístico":    "Leve, descontraído e com potencial viral. Ideal para trends, entretenimento e nichos mais jovens.",
}

# ── Estilo de estrutura (7 principais) ───────────────────────────────────────
ESTILOS = {
    "Storytelling":       "Narrativa com início, conflito e transformação. Ex: 'Há 3 anos um cliente me ligou às 23h porque...'",
    "Lista de Dicas":     "Conteúdo escaneável em tópicos numerados. Ex: '5 erros que todo empreendedor comete em...'",
    "Pergunta + Resposta": "Abre com pergunta provocativa e responde ao longo do post. Ex: 'Você sabia que 80% das empresas erram nisso?'",
    "Antes e Depois":     "Mostra transformação ou contraste de resultado. Ex: 'Antes: 10k/mês. Depois: 47k/mês. O que mudou?'",
    "Passo a Passo":      "Sequência de ações claras e acionáveis. Ex: 'Como fazer X em 4 passos simples:'",
    "Dado + Insight":     "Abre com estatística impactante e analisa o significado. Ex: '87% dos consumidores pesquisam online antes de comprar.'",
    "CTA Direto":         "Foco total em conversão desde a primeira linha. Ex: 'Quer dobrar seus leads esse mês? Faz isso agora:'",
}

# Arquivos de cada cliente no GitHub
CLIENT_FILES = [
    "00-contexto.md",
    "00-objetivos.md",
    "01-mapa-empatia.md",
    "02-proposta-valor.md",
    "03-personas.md",
    "04-lista-temas.md",
]
