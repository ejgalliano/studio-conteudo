GITHUB_REPO    = "ejgalliano/studio-conteudo"
DELETED_FILE   = "_outputs/_deleted.txt"

MODEL_PRIMARY  = "llama-3.3-70b-versatile"
MODEL_FALLBACKS = ["llama-3.1-8b-instant", "gemma2-9b-it"]

FORMATS = ["📱 Card Único", "🎠 Carrossel", "🎬 Reels", "📖 Stories", "💰 Tráfego Pago"]

PILAR_EMOJI = {
    "Comercial":     "🔴",
    "Institucional": "🔵",
    "Educativo":     "🟢",
}

# 10 sub-lotes de 35 temas → 350 temas totais
# Cada lote cabe confortavelmente em max_tokens=4000
THEME_BATCHES = [
    ("Comercial",     "🔴", 35,   1),
    ("Comercial",     "🔴", 35,  36),
    ("Comercial",     "🔴", 35,  71),
    ("Institucional", "🔵", 35, 106),
    ("Institucional", "🔵", 35, 141),
    ("Institucional", "🔵", 35, 176),
    ("Educativo",     "🟢", 35, 211),
    ("Educativo",     "🟢", 35, 246),
    ("Educativo",     "🟢", 35, 281),
    ("Educativo",     "🟢", 35, 316),
]
