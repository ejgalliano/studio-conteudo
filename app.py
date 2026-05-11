import io
import os
import streamlit as st
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from docx import Document as DocxDocument
import fitz  # pymupdf

from constants import FORMATS, PILAR_EMOJI, THEME_BATCHES
from generator import extract_objectives, generate_themes, generate_caption, refine_caption
from github_api import (
    get_deleted_clients, add_to_deleted, remove_from_deleted,
    save_client, delete_client as gh_delete_client,
    load_client_context, load_client_themes_raw,
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
  .block-container { padding-top: 1rem; }
  div[data-testid="stDataFrame"] { border-radius: 8px; }
  .status-pill {
    background: #1e1e2e; color: #cdd6f4;
    border-radius: 8px; padding: 8px 14px;
    font-family: monospace; font-size: 13px;
    text-align: center;
  }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def pilar_emoji(pilar: str) -> str:
    for key, emoji in PILAR_EMOJI.items():
        if key in pilar:
            return emoji
    return "⚪"


def extract_text(uploaded_file) -> str:
    if not uploaded_file:
        return ""
    raw = uploaded_file.read()
    name = uploaded_file.name.lower()
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
            "num":     parts[0],
            "pilar":   parts[1],
            "tema":    parts[2],
            "formato": parts[3],
            "persona": parts[4],
        })
    return themes


def load_guia() -> str:
    p = SISTEMA_PATH / "guia-legendas.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ── Cached GitHub calls ────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def _cached_deleted() -> frozenset:
    return frozenset(get_deleted_clients())


@st.cache_data(ttl=120)
def _cached_themes(client_name: str) -> str | None:
    return load_client_themes_raw(client_name)


@st.cache_data(ttl=120)
def _cached_context(client_name: str) -> dict:
    return load_client_context(client_name)


# ── Client list ────────────────────────────────────────────────────────────────

def get_clients() -> list[str]:
    clients: set[str] = set()

    # From disk (local or Streamlit Cloud repo mount)
    if OUTPUTS_PATH.exists():
        for d in OUTPUTS_PATH.iterdir():
            if d.is_dir() and not d.name.startswith("_"):
                clients.add(d.name)

    # From current session (just created)
    clients.update(st.session_state.session_clients.keys())

    # Remove deleted (session + GitHub)
    deleted = st.session_state.deleted_clients | _cached_deleted()
    clients -= deleted

    return sorted(clients)


def get_themes(client_name: str) -> list[dict]:
    # Session-first
    if client_name in st.session_state.session_clients:
        return st.session_state.session_clients[client_name]["themes"]
    # Disk
    path = OUTPUTS_PATH / client_name / "04-lista-temas.md"
    if path.exists():
        return parse_themes(path.read_text(encoding="utf-8"))
    # GitHub (cached)
    raw = _cached_themes(client_name)
    return parse_themes(raw) if raw else []


def get_context(client_name: str) -> dict:
    # Session-first
    if client_name in st.session_state.session_clients:
        return st.session_state.session_clients[client_name]["context"]
    # Disk
    base = OUTPUTS_PATH / client_name
    files = ["01-mapa-empatia.md", "02-proposta-valor.md", "03-personas.md"]
    ctx = {f: (base / f).read_text(encoding="utf-8") for f in files if (base / f).exists()}
    if ctx:
        return ctx
    # GitHub (cached)
    return _cached_context(client_name)


# ── Session state ──────────────────────────────────────────────────────────────

DEFAULTS = {
    # navigation
    "goto_novo_cliente": "",      # pré-preenche nome após reset

    # client data (same session)
    "session_clients": {},        # {name: {themes, context}}
    "deleted_clients": set(),

    # studio state
    "active_client":   "",
    "selected_theme":  None,
    "caption":         "",
    "caption_version": 0,         # incrementa para forçar re-render do text_area
    "pilar_filter":    "Todos",
    "active_format":   FORMATS[0],
    "document":        [],        # [{num, theme_num, tema, pilar, formato, conteudo}]
    "confirm_delete":  "",

    # novo cliente
    "novo_temas":      None,      # list[dict] após geração
    "novo_temas_raw":  "",
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("### 🎯 Studio de Conteúdo")
st.divider()

tab_studio, tab_novo = st.tabs(["📋 Gerar Conteúdo", "➕ Novo Cliente"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — STUDIO
# ══════════════════════════════════════════════════════════════════════════════

with tab_studio:

    clients = get_clients()

    if not clients:
        st.info("Nenhum cliente encontrado. Use a aba **➕ Novo Cliente** para cadastrar.")
        st.stop()

    # ── Top bar ──
    col_sel, col_reset, col_del, col_doc = st.columns([3, 3, 1, 2])

    with col_sel:
        client = st.selectbox(
            "cliente", clients,
            label_visibility="collapsed",
            key="client_select",
        )

    with col_reset:
        if st.button("🔄 Resetar temas", use_container_width=True,
                     help="Apaga os temas para gerar novas ideias"):
            # Remove temas da sessão
            if client in st.session_state.session_clients:
                del st.session_state.session_clients[client]
            # Remove do disco
            themes_path = OUTPUTS_PATH / client / "04-lista-temas.md"
            if themes_path.exists():
                themes_path.unlink(missing_ok=True)
            # Limpa cache
            _cached_themes.clear()
            # Reseta painel direito
            st.session_state.selected_theme = None
            st.session_state.caption = ""
            st.session_state.caption_version += 1
            # Redireciona para Novo Cliente com nome pré-preenchido
            st.session_state.goto_novo_cliente = client
            st.rerun()

    with col_del:
        if st.button("🗑️", use_container_width=True, help="Apagar cliente permanentemente"):
            st.session_state.confirm_delete = client
            st.rerun()

    with col_doc:
        doc_count = len(st.session_state.document)
        st.markdown(f"<div class='status-pill'>📄 {doc_count} no documento</div>",
                    unsafe_allow_html=True)

    # ── Delete confirmation ──
    if st.session_state.confirm_delete == client:
        st.warning(f"⚠️ Apagar **{client}** permanentemente? Isso remove os arquivos do GitHub também.")
        c_yes, c_no, _ = st.columns([2, 2, 4])
        with c_yes:
            if st.button("✅ Sim, apagar", type="primary", use_container_width=True):
                with st.spinner("Apagando..."):
                    gh_delete_client(client)
                st.session_state.deleted_clients.add(client)
                _cached_deleted.clear()
                st.session_state.confirm_delete = ""
                st.session_state.selected_theme = None
                st.session_state.caption = ""
                st.session_state.active_client = ""
                st.rerun()
        with c_no:
            if st.button("❌ Cancelar", use_container_width=True):
                st.session_state.confirm_delete = ""
                st.rerun()

    # Reset painel quando troca de cliente
    if client != st.session_state.active_client:
        st.session_state.active_client = client
        st.session_state.selected_theme = None
        st.session_state.caption = ""
        st.session_state.caption_version += 1

    themes  = get_themes(client)
    context = get_context(client)
    guia    = load_guia()

    if not themes:
        st.warning(f"Nenhum tema encontrado para **{client}**. Use **🔄 Resetar temas** para gerar.")
        st.stop()

    # ── Panels ──
    left, right = st.columns([2, 2.5], gap="large")

    # ── LEFT: theme list ──
    with left:
        st.markdown(
            f"**📋 {client}** &nbsp;"
            f"<span style='color:#888;font-size:13px'>{len(themes)} temas</span>",
            unsafe_allow_html=True,
        )

        search = st.text_input("🔍", placeholder="Buscar tema...", label_visibility="collapsed")

        f1, f2, f3, f4 = st.columns(4)
        if f1.button("Todos",      use_container_width=True): st.session_state.pilar_filter = "Todos"
        if f2.button("🔴 Com.",    use_container_width=True): st.session_state.pilar_filter = "Comercial"
        if f3.button("🔵 Inst.",   use_container_width=True): st.session_state.pilar_filter = "Institucional"
        if f4.button("🟢 Edu.",    use_container_width=True): st.session_state.pilar_filter = "Educativo"

        filtered = themes
        if search:
            filtered = [t for t in filtered if search.lower() in t["tema"].lower()]
        if st.session_state.pilar_filter != "Todos":
            filtered = [t for t in filtered if st.session_state.pilar_filter in t["pilar"]]

        st.caption(f"{len(filtered)} temas exibidos")

        # Marca temas já adicionados ao documento
        used_nums = {item["theme_num"] for item in st.session_state.document}

        df = pd.DataFrame([{
            "#":     t["num"],
            "Pilar": pilar_emoji(t["pilar"]),
            "Tema":  ("✅ " if t["num"] in used_nums else "") + t["tema"],
        } for t in filtered])

        event = st.dataframe(
            df,
            use_container_width=True,
            height=540,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            column_config={
                "#":     st.column_config.TextColumn(width=40),
                "Pilar": st.column_config.TextColumn(width=40),
                "Tema":  st.column_config.TextColumn(width="large"),
            },
        )

        if event.selection and event.selection.rows:
            chosen = filtered[event.selection.rows[0]]
            if chosen != st.session_state.selected_theme:
                st.session_state.selected_theme = chosen
                st.session_state.caption = ""
                st.session_state.caption_version += 1

    # ── RIGHT: caption panel ──
    with right:
        if not st.session_state.selected_theme:
            st.markdown("""
            <div style='text-align:center;padding:80px 0;color:#888'>
              <div style='font-size:48px'>👈</div>
              <div style='font-size:18px;margin-top:12px'>Clique em um tema para começar</div>
            </div>""", unsafe_allow_html=True)
        else:
            theme = st.session_state.selected_theme

            st.markdown(f"#### {pilar_emoji(theme['pilar'])} {theme['tema']}")

            m1, m2 = st.columns(2)
            m1.caption(f"**Pilar:** {theme['pilar']}")
            m1.caption(f"**Persona:** {theme['persona']}")
            m2.caption(f"**Formato sugerido:** {theme['formato']}")

            # ── Format selector ──
            st.markdown("**Formato do post:**")
            fmt_cols = st.columns(len(FORMATS))
            for i, fmt in enumerate(FORMATS):
                is_active = st.session_state.active_format == fmt
                if fmt_cols[i].button(
                    fmt, key=f"fmt_{i}", use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    if not is_active:
                        st.session_state.active_format = fmt
                        st.session_state.caption = ""
                        st.session_state.caption_version += 1
                        st.rerun()

            st.markdown("")

            # ── Generate button ──
            if st.button("⚡ Gerar Legenda", type="primary", use_container_width=True):
                with st.spinner("Gerando legenda..."):
                    try:
                        caption = generate_caption(
                            theme=theme,
                            formato=st.session_state.active_format,
                            client_name=client,
                            context=context,
                            guia=guia,
                        )
                        st.session_state.caption = caption
                        st.session_state.caption_version += 1
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            # ── Caption editor ──
            if st.session_state.caption:
                st.markdown("---")
                st.markdown("**📝 Legenda gerada — edite se necessário:**")

                # caption_version muda sempre que geramos/refinamos → widget recria do zero
                edited = st.text_area(
                    "legenda",
                    value=st.session_state.caption,
                    height=400,
                    label_visibility="collapsed",
                    key=f"caption_v{st.session_state.caption_version}",
                )

                # ── AI adjustment (st.form garante que o valor é capturado no submit) ──
                st.markdown("**✏️ Ajustar com IA:**")
                with st.form("form_ajuste", clear_on_submit=True):
                    instrucao = st.text_area(
                        "instrucao",
                        placeholder=(
                            'Descreva os ajustes desejados. Ex: "Deixe mais curto, '
                            'tom mais descontraído, troque o CTA por WhatsApp"...'
                        ),
                        height=90,
                        label_visibility="collapsed",
                    )
                    ajustar = st.form_submit_button(
                        "✏️ Ajustar com IA", use_container_width=True, type="secondary"
                    )

                if ajustar:
                    if instrucao.strip():
                        with st.spinner("Ajustando..."):
                            try:
                                refined = refine_caption(edited, instrucao.strip())
                                st.session_state.caption = refined
                                st.session_state.caption_version += 1
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))
                    else:
                        st.warning("Digite uma instrução antes de ajustar.")

                # ── Action buttons ──
                st.markdown("")
                b_add, b_regen, b_clear = st.columns([3, 2, 1])

                with b_add:
                    if st.button("✅ Adicionar ao documento", type="primary", use_container_width=True):
                        st.session_state.document.append({
                            "num":       len(st.session_state.document) + 1,
                            "theme_num": theme["num"],
                            "tema":      theme["tema"],
                            "pilar":     theme["pilar"],
                            "formato":   st.session_state.active_format,
                            "conteudo":  edited,
                        })
                        st.session_state.caption = ""
                        st.session_state.caption_version += 1
                        st.session_state.selected_theme = None
                        st.success(f"✅ Adicionado! {len(st.session_state.document)} conteúdo(s) no documento.")
                        st.rerun()

                with b_regen:
                    if st.button("🔄 Regerar", use_container_width=True):
                        st.session_state.caption = ""
                        st.session_state.caption_version += 1
                        st.rerun()

                with b_clear:
                    if st.button("🗑️", use_container_width=True, help="Descartar legenda"):
                        st.session_state.caption = ""
                        st.session_state.caption_version += 1
                        st.rerun()

    # ── Document section ──────────────────────────────────────────────────────
    st.divider()
    dh, de = st.columns([4, 1])
    dh.markdown(f"### 📄 Documento — {len(st.session_state.document)} conteúdo(s)")

    if st.session_state.document:
        with de:
            word_bytes = export_to_word(st.session_state.document, client)
            st.download_button(
                "⬇️ Exportar Word",
                data=word_bytes,
                file_name=f"conteudos-{client.lower()}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
                use_container_width=True,
            )

        for i, item in enumerate(st.session_state.document):
            with st.expander(
                f"#{item['num']} · {pilar_emoji(item['pilar'])} {item['pilar']} · "
                f"{item['tema']} · {item['formato']}",
                expanded=False,
            ):
                c_txt, c_del = st.columns([6, 1])
                c_txt.text(item["conteudo"])
                if c_del.button("🗑️", key=f"del_doc_{i}", use_container_width=True):
                    st.session_state.document.pop(i)
                    for j, d in enumerate(st.session_state.document):
                        d["num"] = j + 1
                    st.rerun()
    else:
        st.caption("Nenhum conteúdo aprovado ainda.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — NOVO CLIENTE
# ══════════════════════════════════════════════════════════════════════════════

with tab_novo:

    # Auto-switch via JS quando vem de "Resetar temas"
    goto = st.session_state.goto_novo_cliente
    if goto:
        st.markdown("""<script>
        setTimeout(function(){
            var tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
            if(tabs.length > 1) tabs[1].click();
        }, 200);
        </script>""", unsafe_allow_html=True)
        st.info(f"✅ Temas de **{goto}** resetados. Faça o upload dos documentos e clique em **⚡ Gerar Lista de Temas**.")

    st.markdown("### ➕ Novo Cliente")
    st.markdown("Faça upload da transcrição do briefing — a IA extrai os objetivos automaticamente. Depois, carregue os documentos estratégicos se já tiver.")
    st.divider()

    # ── Client name ──
    nome_raw = st.text_input(
        "Nome do cliente (sem espaços, ex: JOAO-PADARIA)",
        placeholder="NOME-DO-CLIENTE",
        value=goto,
    ).upper().strip().replace(" ", "-")
    nome_cliente = nome_raw

    # Limpa redirect depois de usar
    if goto:
        st.session_state.goto_novo_cliente = ""

    # ── Transcription ──
    st.markdown("#### 📝 Transcrição do Briefing")
    st.caption("Aceita **.txt**, **.docx** ou **.pdf**")

    transcricao_file = st.file_uploader(
        "Transcrição", type=["txt", "docx", "pdf"],
        key="up_transcricao", label_visibility="collapsed",
    )
    transcricao_texto = extract_text(transcricao_file) if transcricao_file else ""

    if transcricao_file and transcricao_texto:
        c_info, c_btn = st.columns([3, 1])
        c_info.success(f"✅ **{transcricao_file.name}** carregado ({len(transcricao_texto):,} caracteres)")
        with c_btn:
            if st.button("🤖 Extrair Objetivos", type="primary", use_container_width=True):
                with st.spinner("Lendo transcrição..."):
                    try:
                        resultado = extract_objectives(transcricao_texto)
                        st.session_state["objetivos_editor"] = resultado
                    except Exception as e:
                        st.error(str(e))

    # ── Objectives ──
    st.markdown("#### 🎯 Objetivos do Cliente")
    objetivos = st.text_area(
        "objetivos",
        placeholder="Clique em '🤖 Extrair Objetivos' ou escreva manualmente...",
        height=200,
        label_visibility="collapsed",
        key="objetivos_editor",
    )

    # ── Strategic docs ──
    st.markdown("#### 📂 Documentos Estratégicos *(opcional)*")
    st.caption("Aceita **.txt**, **.docx** ou **.pdf**")

    ca, cb = st.columns(2)
    with ca:
        mapa_file     = st.file_uploader("🧠 Mapa de Empatia",  type=["txt","docx","pdf"], key="up_mapa")
        proposta_file = st.file_uploader("💎 Proposta de Valor", type=["txt","docx","pdf"], key="up_prop")
    with cb:
        personas_file = st.file_uploader("👤 Personas",          type=["txt","docx","pdf"], key="up_pers")

    mapa_texto     = extract_text(mapa_file)
    proposta_texto = extract_text(proposta_file)
    personas_texto = extract_text(personas_file)

    # ── Extra instructions ──
    st.markdown("#### 💬 Instruções Adicionais *(opcional)*")
    instrucoes_extra = st.text_area(
        "instrucoes",
        placeholder="Ex: Focar em WhatsApp, evitar financiamento, priorizar maio...",
        height=80,
        label_visibility="collapsed",
    )

    st.divider()

    # ── Generate themes ──
    if st.button("⚡ Gerar Lista de Temas", type="primary", use_container_width=True):
        if not nome_cliente:
            st.error("Preencha o nome do cliente.")
        elif not any([objetivos, mapa_texto, proposta_texto, personas_texto, transcricao_texto]):
            st.error("Preencha pelo menos um campo estratégico.")
        elif not os.getenv("GROQ_API_KEY"):
            st.error("GROQ_API_KEY não configurada.")
        else:
            st.info(f"Gerando {len(THEME_BATCHES) * 35} temas em {len(THEME_BATCHES)} sub-lotes. Estimativa: 3–5 minutos. Não feche esta aba.")
            progress_bar  = st.progress(0, text="Iniciando...")
            status_text   = st.empty()

            pilar_labels  = {"Comercial": "🔴 Comercial", "Institucional": "🔵 Institucional", "Educativo": "🟢 Educativo"}

            def on_progress(pilar, batch_num, total):
                pct = int((batch_num - 1) / total * 100)
                progress_bar.progress(pct, text=f"Gerando {pilar_labels[pilar]} — sub-lote {batch_num}/{total}...")
                status_text.caption(f"⏳ Aguarde, chamando IA para gerar temas {pilar_labels[pilar]}...")

            try:
                obj_final = objetivos
                if instrucoes_extra:
                    obj_final += f"\n\n## INSTRUÇÕES ADICIONAIS:\n{instrucoes_extra}"

                raw = generate_themes(
                    client_name=nome_cliente,
                    objetivos=obj_final,
                    mapa=mapa_texto or transcricao_texto[:3000],
                    proposta=proposta_texto,
                    personas=personas_texto,
                    progress_callback=on_progress,
                )
                progress_bar.progress(100, text="Concluído! ✅")
                temas = parse_themes(raw)
                st.session_state.novo_temas     = temas
                st.session_state.novo_temas_raw = raw
            except Exception as e:
                st.error(str(e))

    # ── Preview & confirm ──
    if st.session_state.novo_temas:
        temas = st.session_state.novo_temas

        st.success(f"✅ {len(temas)} temas gerados para **{nome_cliente}**! Revise e confirme.")

        # Distribution metrics
        dist = {p: sum(1 for t in temas if p in t["pilar"]) for p in ["Comercial", "Institucional", "Educativo"]}
        d1, d2, d3 = st.columns(3)
        d1.metric("🔴 Comercial",     dist["Comercial"])
        d2.metric("🔵 Institucional", dist["Institucional"])
        d3.metric("🟢 Educativo",     dist["Educativo"])

        df_prev = pd.DataFrame([{
            "#": t["num"], "Pilar": t["pilar"], "Tema": t["tema"],
            "Formato": t["formato"], "Persona": t["persona"],
        } for t in temas])
        st.dataframe(df_prev, use_container_width=True, height=380, hide_index=True)

        st.divider()
        st.markdown("**Confirmar e usar este cliente?**")
        col_ok, col_re, col_gh = st.columns([2, 1, 1])

        with col_ok:
            if st.button("✅ Confirmar e usar no Studio", type="primary", use_container_width=True):
                if not nome_cliente:
                    st.error("Nome do cliente em branco.")
                else:
                    # Remove da lista negra se estava lá
                    remove_from_deleted(nome_cliente)
                    st.session_state.deleted_clients.discard(nome_cliente)
                    _cached_deleted.clear()

                    # Salva na sessão (disponível imediatamente)
                    st.session_state.session_clients[nome_cliente] = {
                        "themes":  temas,
                        "context": {
                            "01-mapa-empatia.md":  mapa_texto,
                            "02-proposta-valor.md": proposta_texto,
                            "03-personas.md":       personas_texto,
                        },
                    }

                    # Tenta salvar no disco
                    try:
                        folder = OUTPUTS_PATH / nome_cliente
                        folder.mkdir(parents=True, exist_ok=True)
                        (folder / "04-lista-temas.md").write_text(
                            st.session_state.novo_temas_raw, encoding="utf-8"
                        )
                    except Exception:
                        pass

                    st.session_state.novo_temas     = None
                    st.session_state.novo_temas_raw = ""
                    st.success(f"✅ **{nome_cliente}** pronto! Vá para **📋 Gerar Conteúdo** e selecione-o.")
                    st.balloons()
                    st.rerun()

        with col_re:
            if st.button("🔄 Gerar novamente", use_container_width=True):
                st.session_state.novo_temas     = None
                st.session_state.novo_temas_raw = ""
                st.rerun()

        with col_gh:
            if st.button("☁️ Salvar no GitHub", use_container_width=True,
                         help="Torna o cliente permanente (sobrevive a reinicializações)"):
                if not nome_cliente:
                    st.error("Nome do cliente em branco.")
                else:
                    with st.spinner("Salvando no GitHub..."):
                        files = {
                            "04-lista-temas.md":   st.session_state.novo_temas_raw,
                            "01-mapa-empatia.md":  mapa_texto,
                            "02-proposta-valor.md": proposta_texto,
                            "03-personas.md":       personas_texto,
                        }
                        ok, msg = save_client(nome_cliente, files)
                        _cached_themes.clear()
                    if ok:
                        st.success("✅ Salvo no GitHub! O cliente estará disponível permanentemente.")
                    else:
                        st.error(f"❌ {msg}")
