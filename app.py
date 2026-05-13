import io
import os
import streamlit as st
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from docx import Document as DocxDocument
import fitz  # pymupdf

from constants import FORMATS, PILAR_EMOJI, PILARES, CLIENT_FILES, TONS, ESTILOS, MODEL_PRIMARY, SUB_BATCH_SIZE
from generator import (
    extract_context_and_objectives,
    generate_themes,
    generate_caption,
    refine_caption,
    clean_text,
    get_token_usage,
)
from github_api import (
    get_deleted_clients,
    add_to_deleted,
    remove_from_deleted,
    save_client,
    delete_client as gh_delete_client,
    load_client,
)
from exporter import export_to_word

load_dotenv()

SISTEMA_PATH = Path(__file__).parent
OUTPUTS_PATH = SISTEMA_PATH / "_outputs"


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Studio de Conteúdo",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  .block-container { padding-top: 1.5rem; }
  .client-name { font-size: 2rem; font-weight: 700; margin: 0.5rem 0 1.5rem; }
  .section-title { font-size: 1.1rem; font-weight: 600;
                   border-left: 4px solid #e74c3c; padding-left: 10px; margin: 1.5rem 0 0.8rem; }
  .step-badge { display:inline-block; background:#e74c3c; color:white;
                border-radius:50%; width:24px; height:24px; line-height:24px;
                text-align:center; font-size:13px; font-weight:700; margin-right:8px; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def pilar_emoji(pilar: str) -> str:
    for k, e in PILAR_EMOJI.items():
        if k in pilar:
            return e
    return "⚪"


def extract_text(f) -> str:
    if not f:
        return ""
    raw = f.read()
    name = f.name.lower()
    if name.endswith(".pdf"):
        doc = fitz.open(stream=raw, filetype="pdf")
        return "\n".join(p.get_text() for p in doc)
    if name.endswith(".docx"):
        doc = DocxDocument(io.BytesIO(raw))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if name.endswith(".txt"):
        return raw.decode("utf-8", errors="ignore")
    return ""


def parse_themes(text: str) -> list[dict]:
    themes = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        themes.append({
            "num": parts[0], "pilar": parts[1],
            "tema": parts[2], "formato": parts[3], "persona": parts[4],
        })
    return themes


def load_guia() -> str:
    p = SISTEMA_PATH / "guia-legendas.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""




# ── Cached GitHub ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def _cached_deleted() -> frozenset:
    return frozenset(get_deleted_clients())


def get_existing_clients() -> list[str]:
    clients: set[str] = set()
    if OUTPUTS_PATH.exists():
        for d in OUTPUTS_PATH.iterdir():
            if d.is_dir() and not d.name.startswith("_"):
                clients.add(d.name)
    clients.update(st.session_state.session_clients.keys())
    deleted = st.session_state.deleted_clients | _cached_deleted()
    clients -= deleted
    return sorted(clients)


# ── Session state ─────────────────────────────────────────────────────────────

DEFAULTS = {
    # client
    "client_name":       "",
    "client_mode":       "novo",        # "novo" | "existente"

    # context
    "contexto":          "",
    "objetivos":         "",

    # uploads (text content)
    "transcricao":       "",
    "mapa":              "",
    "proposta":          "",
    "personas":          "",

    # themes
    "themes":            [],
    "themes_raw":        "",
    "theme_status":      {},   # {num: "rascunho" | "aprovado"}
    "theme_drafts":      {},   # {num: caption_text}

    # temas baixados (persistido no GitHub via 05-conteudos.md)
    "downloaded_themes":    set(),  # {theme_num} já baixados em Word

    # caption panel
    "selected_theme":       None,
    "active_format":        FORMATS[0],
    "active_tom":    list(TONS.keys())[0],
    "active_estilo": list(ESTILOS.keys())[0],
    "instrucoes_legenda":   "",   # instruções livres antes de gerar
    "max_chars_legenda":    750,  # limite de caracteres da legenda
    "caption_versions":     [],   # list of str (last 3)
    "caption_ver_idx":      0,    # index being shown
    "caption_key":          0,    # incrementa para forçar re-render

    # document
    "document":          [],   # [{num, theme_num, tema, pilar, formato, conteudo}]

    # ephemeral client data (same session)
    "session_clients":   {},
    "deleted_clients":   set(),

    # delete confirm
    "confirm_delete":    False,
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

S = st.session_state  # alias curto


# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════

col_title, col_model = st.columns([5, 3])
col_title.markdown("## 🎯 Studio de Conteúdo")
with col_model:
    key_ok = bool(os.getenv("GOOGLE_API_KEY"))
    usage  = get_token_usage()
    pct    = usage["pct"]
    cor    = "#27ae60" if pct < 60 else "#f39c12" if pct < 85 else "#e74c3c"
    emoji  = "🟢" if pct < 60 else "🟡" if pct < 85 else "🔴"
    st.markdown(
        f"<div style='text-align:right; padding-top:10px; font-size:0.78rem; line-height:1.6'>"
        f"{'✅' if key_ok else '❌'} <b>{MODEL_PRIMARY}</b> &nbsp;|&nbsp; limite: 1.500 req/dia<br>"
        f"<span style='color:{cor}'>{emoji} {usage['requests']} requisições nesta sessão"
        f" &nbsp;·&nbsp; {usage['used']:,} tokens</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 0 — CLIENTE
# ══════════════════════════════════════════════════════════════════════════════

st.markdown('<div class="section-title"><span class="step-badge">1</span>Cliente</div>',
            unsafe_allow_html=True)

existing = get_existing_clients()

mode_col, _ = st.columns([3, 5])
with mode_col:
    mode = st.radio(
        "modo",
        ["✨ Novo cliente", "📂 Carregar existente"],
        horizontal=True,
        label_visibility="collapsed",
        key="mode_radio",
    )

if mode == "📂 Carregar existente":
    S.client_mode = "existente"
    if not existing:
        st.info("Nenhum cliente salvo encontrado. Crie um novo.")
    else:
        sel_col, btn_col = st.columns([3, 1])
        with sel_col:
            chosen = st.selectbox("Selecione o cliente", existing,
                                  label_visibility="collapsed")
        with btn_col:
            load_btn = st.button("📂 Carregar", use_container_width=True, type="primary")

        if load_btn:
            with st.spinner("Carregando dados do cliente..."):
                data = load_client(chosen)
                # Tenta disco primeiro
                disk = OUTPUTS_PATH / chosen
                def read_disk(filename):
                    p = disk / filename
                    return p.read_text(encoding="utf-8") if p.exists() else data.get(filename, "")

                S.client_name   = chosen
                S.contexto      = read_disk("00-contexto.md")
                S.objetivos     = read_disk("00-objetivos.md")
                S.mapa          = read_disk("01-mapa-empatia.md")
                S.proposta      = read_disk("02-proposta-valor.md")
                S.personas      = read_disk("03-personas.md")
                themes_raw      = read_disk("04-lista-temas.md")
                S.themes        = parse_themes(themes_raw)
                S.themes_raw    = themes_raw
                S.selected_theme   = None
                S.caption_versions = []
                S.theme_status     = {}
                # Carrega temas já baixados em Word
                conteudos_raw = read_disk("05-conteudos.md")
                S.downloaded_themes = set(
                    n.strip() for n in conteudos_raw.splitlines() if n.strip()
                )
                st.rerun()

        # Delete button
        del_col, _ = st.columns([2, 6])
        with del_col:
            if st.button("🗑️ Apagar este cliente", use_container_width=True):
                S.confirm_delete = True

        if S.confirm_delete:
            st.warning(f"Apagar **{chosen}** permanentemente do GitHub?")
            y, n, _ = st.columns([2, 2, 4])
            if y.button("✅ Sim, apagar", type="primary", use_container_width=True):
                with st.spinner("Apagando..."):
                    gh_delete_client(chosen)
                S.deleted_clients.add(chosen)
                _cached_deleted.clear()
                S.confirm_delete = False
                S.client_name = ""
                st.rerun()
            if n.button("❌ Cancelar", use_container_width=True):
                S.confirm_delete = False
                st.rerun()
else:
    S.client_mode = "novo"
    name_input = st.text_input(
        "Nome do cliente (sem espaços, ex: JOAO-PADARIA)",
        value=S.client_name,
        placeholder="NOME-DO-CLIENTE",
    ).upper().strip().replace(" ", "-")
    if name_input:
        S.client_name = name_input

# ── Client name in big display ──
if S.client_name:
    st.markdown(f'<div class="client-name">👤 {S.client_name}</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 1 — UPLOADS
# ══════════════════════════════════════════════════════════════════════════════

if not S.client_name:
    st.stop()

st.markdown('<div class="section-title"><span class="step-badge">2</span>Documentos</div>',
            unsafe_allow_html=True)
st.caption("Aceita .txt, .docx ou .pdf · Todos os campos são opcionais mas quanto mais conteúdo, melhores os temas")

u1, u2, u3, u4 = st.columns(4)
with u1:
    tr_file = st.file_uploader("📄 Transcrição do Briefing", type=["txt","docx","pdf"], key="up_trans")
with u2:
    ma_file = st.file_uploader("🧠 Mapa de Empatia",  type=["txt","docx","pdf"], key="up_mapa")
with u3:
    pr_file = st.file_uploader("💎 Proposta de Valor", type=["txt","docx","pdf"], key="up_prop")
with u4:
    pe_file = st.file_uploader("👤 Personas",          type=["txt","docx","pdf"], key="up_pers")

if tr_file: S.transcricao = extract_text(tr_file)
if ma_file: S.mapa        = extract_text(ma_file)
if pr_file: S.proposta    = extract_text(pr_file)
if pe_file: S.personas    = extract_text(pe_file)

uploaded_any = any([S.transcricao, S.mapa, S.proposta, S.personas, S.contexto, S.objetivos])


# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 2 — CONTEXTO E OBJETIVOS
# ══════════════════════════════════════════════════════════════════════════════

st.markdown('<div class="section-title"><span class="step-badge">3</span>Contexto e Objetivos</div>',
            unsafe_allow_html=True)

if S.transcricao:
    if st.button("🤖 Extrair contexto e objetivos da transcrição", type="primary"):
        with st.spinner("Lendo transcrição e extraindo informações..."):
            try:
                ctx, obj = extract_context_and_objectives(S.transcricao)
                st.session_state["ctx_editor"] = ctx
                st.session_state["obj_editor"] = obj
            except Exception as e:
                st.error(str(e))

ctx_col, obj_col = st.columns(2)
with ctx_col:
    st.markdown("**Contexto do Cliente**")
    st.caption("Mercado, produtos, diferenciais, tom de voz, público-alvo")
    S.contexto = st.text_area(
        "contexto", value=S.contexto,
        height=220, label_visibility="collapsed", key="ctx_editor",
        placeholder="Descreva o mercado de atuação, produtos/serviços, diferenciais e público-alvo...",
    )

with obj_col:
    st.markdown("**Objetivos**")
    st.caption("O que o cliente quer alcançar nas redes sociais")
    S.objetivos = st.text_area(
        "objetivos", value=S.objetivos,
        height=220, label_visibility="collapsed", key="obj_editor",
        placeholder="Descreva os objetivos, metas, restrições e preferências...",
    )

has_context = bool(S.contexto or S.objetivos or S.mapa or S.proposta or S.personas)


# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 3 — TEMAS
# ══════════════════════════════════════════════════════════════════════════════

st.markdown('<div class="section-title"><span class="step-badge">4</span>Lista de Temas</div>',
            unsafe_allow_html=True)

if not has_context:
    st.info("Preencha o contexto ou faça upload de pelo menos um documento para gerar os temas.")
else:
    q1, q2, q3, q4, q5 = st.columns(5)
    with q1:
        n_com  = st.number_input("🔴 Comercial",     min_value=0, max_value=200, value=20, step=5)
    with q2:
        n_ins  = st.number_input("🔵 Institucional", min_value=0, max_value=200, value=20, step=5)
    with q3:
        n_inf  = st.number_input("🟢 Informativo",   min_value=0, max_value=200, value=20, step=5)
    with q4:
        n_eng  = st.number_input("🟡 Engajamento",   min_value=0, max_value=200, value=10, step=5)
    with q5:
        n_cas  = st.number_input("🟣 Cases",         min_value=0, max_value=200, value=10, step=5)

    total_temas = n_com + n_ins + n_inf + n_eng + n_cas
    n_lotes = -(-total_temas // SUB_BATCH_SIZE)  # ceil division
    t_min = max(1, n_lotes * 20 // 60)
    t_max = max(2, n_lotes * 35 // 60 + 1)
    st.caption(f"Total: {total_temas} temas · {n_lotes} chamadas à IA · estimativa: {t_min}–{t_max} minutos")

    if st.button("⚡ Gerar Lista de Temas", type="primary", use_container_width=True,
                 disabled=total_temas == 0):
        if not os.getenv("GOOGLE_API_KEY"):
            st.error("GOOGLE_API_KEY não configurada. Obtenha gratuitamente em https://aistudio.google.com")
        else:
            pb = st.progress(0, text="Iniciando...")
            st_status = st.empty()

            def on_progress(pilar, batch_num, total):
                pct = int((batch_num - 1) / total * 100)
                pb.progress(pct, text=f"Gerando temas {PILAR_EMOJI.get(pilar,'')} {pilar} — lote {batch_num}/{total}...")
                st_status.caption(f"Aguarde... chamando IA para {pilar}")

            try:
                raw = generate_themes(
                    client_name=S.client_name,
                    contexto=S.contexto,
                    objetivos=S.objetivos,
                    mapa=S.mapa or S.transcricao[:3000],
                    proposta=S.proposta,
                    personas=S.personas,
                    n_comercial=n_com,
                    n_institucional=n_ins,
                    n_informativo=n_inf,
                    n_engajamento=n_eng,
                    n_cases=n_cas,
                    progress_callback=on_progress,
                )
                pb.progress(100, text="Concluído!")
                st_status.empty()
                S.themes     = parse_themes(raw)
                S.themes_raw = raw
                S.theme_status = {}
                S.theme_drafts = {}
                S.selected_theme = None
                st.rerun()
            except Exception as e:
                st.error(str(e))

# ── Theme table ──
if S.themes:
    st.caption(f"{len(S.themes)} temas gerados")

    # Filtros
    fc1, fc2, fc3, fc4, fc5, fc6, search_col = st.columns([1, 1, 1, 1, 1, 1, 3])
    if fc1.button("Todos",      use_container_width=True, key="f_all"):  S["pilar_filter"] = "Todos"
    if fc2.button("🔴 Com.",    use_container_width=True, key="f_com"):  S["pilar_filter"] = "Comercial"
    if fc3.button("🔵 Inst.",   use_container_width=True, key="f_ins"):  S["pilar_filter"] = "Institucional"
    if fc4.button("🟢 Info.",   use_container_width=True, key="f_inf"):  S["pilar_filter"] = "Informativo"
    if fc5.button("🟡 Eng.",    use_container_width=True, key="f_eng"):  S["pilar_filter"] = "Engajamento"
    if fc6.button("🟣 Cases",   use_container_width=True, key="f_cas"):  S["pilar_filter"] = "Cases"
    if "pilar_filter" not in S: S["pilar_filter"] = "Todos"

    with search_col:
        search = st.text_input("🔍", placeholder="Buscar tema...", label_visibility="collapsed")

    filtered = S.themes
    if search:
        filtered = [t for t in filtered if search.lower() in t["tema"].lower()]
    if S.get("pilar_filter", "Todos") != "Todos":
        filtered = [t for t in filtered if S["pilar_filter"] in t["pilar"]]

    def theme_status_icon(num):
        if num in S.downloaded_themes:  return "📄"
        s = S.theme_status.get(num, "")
        if s == "aprovado":             return "✅"
        if s == "rascunho":             return "📝"
        return ""

    df = pd.DataFrame([{
        "#":       t["num"],
        "Pilar":   pilar_emoji(t["pilar"]),
        "Tema":    theme_status_icon(t["num"]) + (" " if theme_status_icon(t["num"]) else "") + t["tema"],
        "Formato": t["formato"],
    } for t in filtered])

    event = st.dataframe(
        df,
        use_container_width=True,
        height=420,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        column_config={
            "#":      st.column_config.TextColumn(width=40),
            "Pilar":  st.column_config.TextColumn(width=45),
            "Tema":   st.column_config.TextColumn(width="large"),
            "Formato":st.column_config.TextColumn(width=120),
        },
    )

    if event.selection and event.selection.rows:
        chosen_theme = filtered[event.selection.rows[0]]
        if chosen_theme != S.selected_theme:
            S.selected_theme = chosen_theme
            # Carrega rascunho se existir
            draft = S.theme_drafts.get(chosen_theme["num"], "")
            S.caption_versions = [draft] if draft else []
            S.caption_ver_idx  = 0
            S.caption_key     += 1

    # Botão salvar temas
    sv1, sv2 = st.columns([2, 5])
    with sv1:
        if st.button("☁️ Salvar temas no GitHub", use_container_width=True):
            with st.spinner("Salvando..."):
                files = {
                    "04-lista-temas.md":   S.themes_raw,
                    "00-contexto.md":      S.contexto,
                    "00-objetivos.md":     S.objetivos,
                    "01-mapa-empatia.md":  S.mapa,
                    "02-proposta-valor.md":S.proposta,
                    "03-personas.md":      S.personas,
                }
                # Remove da lista negra se estava lá
                remove_from_deleted(S.client_name)
                S.deleted_clients.discard(S.client_name)
                _cached_deleted.clear()
                ok, msg = save_client(S.client_name, files)
            if ok:
                st.success("✅ Cliente salvo no GitHub. Disponível para toda a equipe.")
            else:
                st.error(f"❌ {msg}")


# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 4 — LEGENDA
# ══════════════════════════════════════════════════════════════════════════════

if S.selected_theme:
    theme = S.selected_theme
    st.divider()
    st.markdown(
        f'<div class="section-title"><span class="step-badge">5</span>'
        f'Legenda — {pilar_emoji(theme["pilar"])} {theme["tema"]}</div>',
        unsafe_allow_html=True,
    )

    guia = load_guia()
    m1, m2, m3 = st.columns(3)
    m1.caption(f"Pilar: {theme['pilar']}")
    m2.caption(f"Persona: {theme['persona']}")
    m3.caption(f"Formato sugerido: {theme['formato']}")

    # ── Format selector ──
    st.markdown("**Formato do post:**")
    fmt_cols = st.columns(len(FORMATS))
    for i, fmt in enumerate(FORMATS):
        active = S.active_format == fmt
        if fmt_cols[i].button(fmt, key=f"fmt_{i}", use_container_width=True,
                              type="primary" if active else "secondary"):
            if not active:
                S.active_format = fmt
                S.caption_key += 1
                st.rerun()

    # ── Tom / Estilo ──
    st.markdown("**Tom e estilo:**")
    tc, ec = st.columns(2)
    with tc:
        tom_idx = list(TONS.keys()).index(S.active_tom) if S.active_tom in TONS else 0
        S.active_tom = st.selectbox(
            "🔵 Tom de Voz",
            list(TONS.keys()),
            index=tom_idx,
            help=TONS.get(S.active_tom, ""),
        )
    with ec:
        estilo_idx = list(ESTILOS.keys()).index(S.active_estilo) if S.active_estilo in ESTILOS else 0
        S.active_estilo = st.selectbox(
            "🟣 Estilo de Estrutura",
            list(ESTILOS.keys()),
            index=estilo_idx,
            help=ESTILOS.get(S.active_estilo, ""),
        )

    # ── Instruções e limite de caracteres ──
    st.markdown("**Instruções adicionais e tamanho:**")
    ic, cc = st.columns([4, 1])
    with ic:
        S.instrucoes_legenda = st.text_area(
            "instrucoes_legenda",
            value=S.instrucoes_legenda,
            placeholder='Ex: "Mencione o prazo de entrega de 24h", "Use tom mais técnico", "Foque na dor de parada de produção"...',
            height=80,
            label_visibility="collapsed",
        )
    with cc:
        S.max_chars_legenda = st.number_input(
            "Máx. caracteres",
            min_value=100,
            max_value=2200,
            value=S.max_chars_legenda,
            step=50,
            help="Limite de caracteres da legenda (sem contar hashtags)",
        )

    # ── Generate ──
    if st.button("⚡ Gerar Legenda", type="primary", use_container_width=True):
        with st.spinner("Gerando legenda..."):
            try:
                cap = generate_caption(
                    theme=theme,
                    formato=S.active_format,
                    client_name=S.client_name,
                    contexto=S.contexto,
                    objetivos=S.objetivos,
                    mapa=S.mapa,
                    proposta=S.proposta,
                    personas=S.personas,
                    guia=guia,
                    tom=S.active_tom,
                    estilo=S.active_estilo,
                    instrucoes=S.instrucoes_legenda,
                    max_chars=S.max_chars_legenda,
                )
                # Adiciona ao histórico (máximo 3 versões)
                S.caption_versions = ([cap] + S.caption_versions)[:3]
                S.caption_ver_idx  = 0
                S.caption_key     += 1
                # Salva como rascunho
                S.theme_drafts[theme["num"]] = cap
                S.theme_status[theme["num"]] = "rascunho"
                st.rerun()
            except Exception as e:
                st.error(str(e))

    # ── Caption editor ──
    if S.caption_versions:
        current_caption = S.caption_versions[S.caption_ver_idx]

        # Version history buttons
        if len(S.caption_versions) > 1:
            st.caption("Versões:")
            v_cols = st.columns(len(S.caption_versions))
            for i, _ in enumerate(S.caption_versions):
                label = f"Versão {i+1}" + (" (atual)" if i == S.caption_ver_idx else "")
                if v_cols[i].button(label, key=f"ver_{i}",
                                    type="primary" if i == S.caption_ver_idx else "secondary",
                                    use_container_width=True):
                    S.caption_ver_idx = i
                    S.caption_key    += 1
                    st.rerun()

        st.markdown("**Legenda gerada — edite diretamente se quiser:**")
        edited = st.text_area(
            "legenda",
            value=current_caption,
            height=420,
            label_visibility="collapsed",
            key=f"cap_v{S.caption_key}",
        )

        # ── AI refinement ──
        st.markdown("**Ajustar com IA:**")
        with st.form("form_ajuste", clear_on_submit=True):
            instrucao = st.text_area(
                "instrucao",
                placeholder='Ex: "Deixe mais curto", "Tom mais descontraído", "Foque nos bairros X e Y", "Troque o CTA por WhatsApp"...',
                height=80,
                label_visibility="collapsed",
            )
            ajustar = st.form_submit_button("✏️ Ajustar com IA", use_container_width=True,
                                            type="secondary")

        if ajustar:
            if instrucao.strip():
                with st.spinner("Ajustando..."):
                    try:
                        refined = refine_caption(edited, instrucao.strip())
                        S.caption_versions = ([refined] + S.caption_versions)[:3]
                        S.caption_ver_idx  = 0
                        S.caption_key     += 1
                        S.theme_drafts[theme["num"]] = refined
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            else:
                st.warning("Digite uma instrução antes de ajustar.")

        # ── Action buttons ──
        b_add, b_regen, b_clear = st.columns([3, 2, 1])

        with b_add:
            if st.button("✅ Adicionar ao documento Word", type="primary", use_container_width=True):
                S.document.append({
                    "num":       len(S.document) + 1,
                    "theme_num": theme["num"],
                    "tema":      theme["tema"],
                    "pilar":     theme["pilar"],
                    "formato":   S.active_format,
                    "conteudo":  edited,
                })
                S.theme_status[theme["num"]] = "aprovado"
                S.caption_versions = []
                S.caption_key     += 1
                # Não limpa selected_theme — usuário vê mensagem e escolhe o próximo
                st.success(f"✅ Adicionado! {len(S.document)} conteúdo(s) no documento. Clique em outro tema na tabela acima para continuar.")
                st.rerun()

        with b_regen:
            if st.button("🔄 Gerar nova versão", use_container_width=True):
                with st.spinner("Gerando nova versão..."):
                    try:
                        cap2 = generate_caption(
                            theme=theme,
                            formato=S.active_format,
                            client_name=S.client_name,
                            contexto=S.contexto,
                            objetivos=S.objetivos,
                            mapa=S.mapa,
                            proposta=S.proposta,
                            personas=S.personas,
                            guia=guia,
                            tom=S.active_tom,
                            estilo=S.active_estilo,
                            instrucoes=S.instrucoes_legenda,
                            max_chars=S.max_chars_legenda,
                        )
                        S.caption_versions = ([cap2] + S.caption_versions)[:3]
                        S.caption_ver_idx  = 0
                        S.caption_key     += 1
                        S.theme_drafts[theme["num"]] = cap2
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

        with b_clear:
            if st.button("🗑️", use_container_width=True, help="Descartar legenda"):
                S.caption_versions = []
                S.caption_key     += 1
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 5 — DOCUMENTO WORD
# ══════════════════════════════════════════════════════════════════════════════

if S.document:
    st.divider()
    dh, de = st.columns([4, 1])
    dh.markdown(
        f'<div class="section-title"><span class="step-badge">6</span>'
        f'Documento Word — {len(S.document)} conteúdo(s)</div>',
        unsafe_allow_html=True,
    )
    with de:
        word_bytes = export_to_word(S.document, S.client_name)

        def _on_download():
            # Marca temas do documento como baixados e persiste no GitHub
            nums = {item["theme_num"] for item in S.document}
            S.downloaded_themes = S.downloaded_themes | nums
            content = "\n".join(sorted(S.downloaded_themes))
            save_client(S.client_name, {"05-conteudos.md": content})

        st.download_button(
            "⬇️ Exportar Word",
            data=word_bytes,
            file_name=f"conteudos-{S.client_name.lower()}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
            use_container_width=True,
            on_click=_on_download,
        )

    for i, item in enumerate(S.document):
        with st.expander(
            f"#{item['num']} · {pilar_emoji(item['pilar'])} {item['pilar']} · "
            f"{item['tema']} · {item['formato']}",
            expanded=False,
        ):
            c_txt, c_del = st.columns([6, 1])
            c_txt.text(item["conteudo"])
            if c_del.button("🗑️", key=f"del_{i}", use_container_width=True):
                S.document.pop(i)
                for j, d in enumerate(S.document):
                    d["num"] = j + 1
                st.rerun()
