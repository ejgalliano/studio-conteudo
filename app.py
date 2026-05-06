import streamlit as st
import pandas as pd
import os
import re
from pathlib import Path
from dotenv import load_dotenv

from generator import generate_caption
from exporter import export_to_word

load_dotenv()

SISTEMA_PATH = Path(__file__).parent

st.set_page_config(
    page_title="Studio de Conteúdo",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Remove top padding */
    .block-container { padding-top: 1rem; }

    /* Theme list buttons */
    div[data-testid="stDataFrame"] { border-radius: 8px; }

    /* Pill badges */
    .pill-red   { background:#fdecea; color:#c0392b; border-radius:12px; padding:2px 10px; font-size:12px; font-weight:600; }
    .pill-blue  { background:#e8f4fd; color:#216eab; border-radius:12px; padding:2px 10px; font-size:12px; font-weight:600; }
    .pill-green { background:#eafaf1; color:#27ae60; border-radius:12px; padding:2px 10px; font-size:12px; font-weight:600; }

    /* Document item */
    .doc-item { background:#f8f9fa; border-left:4px solid #4a90d9; border-radius:6px; padding:12px; margin:8px 0; }

    /* Status bar */
    .status-bar { background:#1e1e2e; color:#cdd6f4; border-radius:8px; padding:10px 16px; font-family:monospace; font-size:13px; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_clients() -> list[str]:
    outputs = SISTEMA_PATH / "_outputs"
    if not outputs.exists():
        return []
    return sorted(d.name for d in outputs.iterdir() if d.is_dir())


def parse_themes(client_name: str) -> list[dict]:
    path = SISTEMA_PATH / "_outputs" / client_name / "04-lista-temas.md"
    if not path.exists():
        return []

    themes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if len(parts) < 5:
            continue
        num = parts[0].strip()
        if not num.isdigit():
            continue
        themes.append({
            "num": num,
            "pilar": parts[1],
            "tema": parts[2],
            "formato": parts[3],
            "persona": parts[4],
        })
    return themes


def load_client_context(client_name: str) -> dict:
    base = SISTEMA_PATH / "_outputs" / client_name
    files = ["01-mapa-empatia.md", "02-proposta-valor.md", "03-personas.md"]
    return {f: (base / f).read_text(encoding="utf-8") for f in files if (base / f).exists()}


def load_guia() -> str:
    p = SISTEMA_PATH / "guia-legendas.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def pilar_emoji(pilar: str) -> str:
    if "Comercial" in pilar:
        return "🔴"
    if "Institucional" in pilar:
        return "🔵"
    if "Educativo" in pilar:
        return "🟢"
    return "⚪"


# ── Session state ─────────────────────────────────────────────────────────────

defaults = {
    "selected_theme": None,
    "generated_caption": "",
    "document_items": [],
    "last_client": "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Header ────────────────────────────────────────────────────────────────────

clients = get_clients()
if not clients:
    st.error("Nenhum cliente encontrado em `_outputs/`. Execute o fluxo completo primeiro.")
    st.stop()

top_left, top_mid, top_right = st.columns([3, 5, 2])
with top_left:
    st.markdown("### 🎯 Studio de Conteúdo")
with top_mid:
    client = st.selectbox(
        "Cliente",
        clients,
        label_visibility="collapsed",
        key="client_select",
    )
with top_right:
    doc_count = len(st.session_state.document_items)
    st.markdown(f"<div class='status-bar'>📄 {doc_count} no documento</div>", unsafe_allow_html=True)

# Reset state when client changes
if client != st.session_state.last_client:
    st.session_state.selected_theme = None
    st.session_state.generated_caption = ""
    st.session_state.last_client = client

st.divider()

# ── Load data ─────────────────────────────────────────────────────────────────

themes = parse_themes(client)
client_context = load_client_context(client)
guia = load_guia()

if not themes:
    st.warning(f"Nenhum tema encontrado para **{client}**. Verifique o arquivo `04-lista-temas.md`.")
    st.stop()

# ── Main layout ───────────────────────────────────────────────────────────────

left, right = st.columns([2, 3], gap="large")

# ════════════════════════════════════════════════════════════
# LEFT — Theme list
# ════════════════════════════════════════════════════════════
with left:
    st.markdown(f"**📋 Temas — {client}** &nbsp; <span style='color:#888;font-size:13px'>{len(themes)} temas</span>", unsafe_allow_html=True)

    # Filters
    search = st.text_input("🔍", placeholder="Buscar tema...", label_visibility="collapsed")

    f1, f2, f3, f4 = st.columns(4)
    filter_all = f1.button("Todos", use_container_width=True)
    filter_com = f2.button("🔴 Com.", use_container_width=True)
    filter_ins = f3.button("🔵 Inst.", use_container_width=True)
    filter_edu = f4.button("🟢 Edu.", use_container_width=True)

    if "pilar_filter" not in st.session_state:
        st.session_state.pilar_filter = "Todos"
    if filter_all:
        st.session_state.pilar_filter = "Todos"
    if filter_com:
        st.session_state.pilar_filter = "Comercial"
    if filter_ins:
        st.session_state.pilar_filter = "Institucional"
    if filter_edu:
        st.session_state.pilar_filter = "Educativo"

    # Apply filters
    filtered = themes
    if search:
        filtered = [t for t in filtered if search.lower() in t["tema"].lower()]
    if st.session_state.pilar_filter != "Todos":
        filtered = [t for t in filtered if st.session_state.pilar_filter in t["pilar"]]

    st.caption(f"{len(filtered)} temas exibidos")

    # Build dataframe for display
    df = pd.DataFrame([
        {
            "#": t["num"],
            "Tema": t["tema"],
            "Formato": t["formato"].split("+")[0].strip(),
            "Persona": t["persona"].split("/")[0].strip(),
        }
        for t in filtered
    ])

    event = st.dataframe(
        df,
        use_container_width=True,
        height=520,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        column_config={
            "#": st.column_config.TextColumn(width="small"),
            "Tema": st.column_config.TextColumn(width="large"),
            "Formato": st.column_config.TextColumn(width="medium"),
            "Persona": st.column_config.TextColumn(width="medium"),
        },
    )

    # Handle row selection
    if event.selection and event.selection.rows:
        row_idx = event.selection.rows[0]
        new_theme = filtered[row_idx]
        if st.session_state.selected_theme != new_theme:
            st.session_state.selected_theme = new_theme
            st.session_state.generated_caption = ""


# ════════════════════════════════════════════════════════════
# RIGHT — Caption generator
# ════════════════════════════════════════════════════════════
with right:
    if not st.session_state.selected_theme:
        st.markdown("""
        <div style='text-align:center; padding:80px 0; color:#888'>
            <div style='font-size:48px'>👈</div>
            <div style='font-size:18px; margin-top:12px'>Clique em um tema para gerar a legenda</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        theme = st.session_state.selected_theme
        emoji = pilar_emoji(theme["pilar"])

        st.markdown(f"#### {emoji} {theme['tema']}")

        meta1, meta2 = st.columns(2)
        with meta1:
            st.caption(f"**Pilar:** {theme['pilar']}")
            st.caption(f"**Persona:** {theme['persona']}")
        with meta2:
            st.caption(f"**Formato sugerido:** {theme['formato']}")

        # Format selector
        st.markdown("**Formato do post:**")
        fmt_cols = st.columns(5)
        formats = ["📱 Card Único", "🎠 Carrossel", "🎬 Reels", "📖 Stories", "💰 Tráfego Pago"]
        if "selected_format" not in st.session_state:
            st.session_state.selected_format = formats[0]

        for i, fmt in enumerate(formats):
            if fmt_cols[i].button(fmt, key=f"fmt_{i}", use_container_width=True,
                                  type="primary" if st.session_state.selected_format == fmt else "secondary"):
                st.session_state.selected_format = fmt
                st.session_state.generated_caption = ""

        st.markdown("")

        # Generate button
        if st.button("⚡ Gerar Legenda", type="primary", use_container_width=True):
            if not os.getenv("GROQ_API_KEY"):
                st.error("API Key não configurada. Crie um arquivo `.env` com `ANTHROPIC_API_KEY=sua_chave`.")
            else:
                with st.spinner(f"Gerando legenda para **{theme['tema']}** em formato **{st.session_state.selected_format}**..."):
                    try:
                        caption = generate_caption(
                            theme=theme,
                            formato=st.session_state.selected_format,
                            client_name=client,
                            client_context=client_context,
                            guia=guia,
                        )
                        st.session_state.generated_caption = caption
                    except Exception as e:
                        st.error(f"Erro ao gerar: {e}")

        # Caption display & editing
        if st.session_state.generated_caption:
            st.markdown("---")
            st.markdown("**📝 Legenda gerada — edite se necessário:**")

            edited = st.text_area(
                "legenda",
                value=st.session_state.generated_caption,
                height=420,
                label_visibility="collapsed",
                key="caption_editor",
            )

            btn_add, btn_regen, btn_clear = st.columns([3, 2, 1])

            with btn_add:
                if st.button("✅ Adicionar ao documento", type="primary", use_container_width=True):
                    item = {
                        "num": len(st.session_state.document_items) + 1,
                        "tema": theme["tema"],
                        "pilar": theme["pilar"],
                        "formato": st.session_state.selected_format,
                        "conteudo": edited,
                    }
                    st.session_state.document_items.append(item)
                    st.session_state.generated_caption = ""
                    st.session_state.selected_theme = None
                    st.success(f"✅ Adicionado! {len(st.session_state.document_items)} conteúdo(s) no documento.")
                    st.rerun()

            with btn_regen:
                if st.button("🔄 Regerar", use_container_width=True):
                    st.session_state.generated_caption = ""
                    st.rerun()

            with btn_clear:
                if st.button("🗑️", use_container_width=True, help="Limpar legenda"):
                    st.session_state.generated_caption = ""
                    st.rerun()


# ════════════════════════════════════════════════════════════
# BOTTOM — Document section
# ════════════════════════════════════════════════════════════
st.divider()
doc_header, doc_export = st.columns([4, 1])

with doc_header:
    st.markdown(f"### 📄 Documento — {len(st.session_state.document_items)} conteúdo(s) aprovado(s)")

with doc_export:
    if st.session_state.document_items:
        word_bytes = export_to_word(st.session_state.document_items, client)
        st.download_button(
            label="⬇️ Exportar Word",
            data=word_bytes,
            file_name=f"conteudos-{client.lower()}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
            use_container_width=True,
        )

if not st.session_state.document_items:
    st.caption("Nenhum conteúdo aprovado ainda. Gere e adicione conteúdos acima.")
else:
    for i, item in enumerate(st.session_state.document_items):
        with st.expander(
            f"#{item['num']} &nbsp;|&nbsp; {pilar_emoji(item['pilar'])} {item['pilar']} &nbsp;|&nbsp; {item['tema']} &nbsp;|&nbsp; {item['formato']}",
            expanded=False,
        ):
            col_content, col_remove = st.columns([6, 1])
            with col_content:
                st.text(item["conteudo"])
            with col_remove:
                if st.button("🗑️ Remover", key=f"remove_{i}", use_container_width=True):
                    st.session_state.document_items.pop(i)
                    # Renumber
                    for j, d in enumerate(st.session_state.document_items):
                        d["num"] = j + 1
                    st.rerun()
