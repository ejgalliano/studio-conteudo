GITHUB_REPO    = "ejgalliano/studio-conteudo"
DELETED_FILE   = "_outputs/_deleted.txt"

MODEL_PRIMARY   = "llama-3.3-70b-versatile"
MODEL_FALLBACKS = ["llama-3.1-8b-instant", "gemma2-9b-it"]

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

# Arquivos de cada cliente no GitHub
CLIENT_FILES = [
    "00-contexto.md",
    "00-objetivos.md",
    "01-mapa-empatia.md",
    "02-proposta-valor.md",
    "03-personas.md",
    "04-lista-temas.md",
]
