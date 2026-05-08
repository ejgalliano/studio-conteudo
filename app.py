import streamlit as st
import pandas as pd
import os
import io
import base64
import requests
from pathlib import Path
from dotenv import load_dotenv
from docx import Document as DocxDocument
import fitz  # pymupdf

from generator import generate_caption, generate_themes, extract_objectives, refine_caption
from exporter import export_to_word

load_dotenv()

SISTEMA_PATH = Path(__file__).parent

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
    .status-bar { background:#1e1e2e; color:#cdd6f4; border-radius:8px; padding:10px 16px; font-family:monospace; font-size:13px; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def _fetch_deleted_clients() -> frozenset:
    """Cache the deleted list for 60s to avoid hitting GitHub API on every rerun."""
    return frozenset(get_deleted_clients_github())


def get_clients() -> list[str]:
    clients = set()
    outputs = SISTEMA_PATH / "_outputs"
    if outputs.exists():
        for d in outputs.iterdir():
            if d.is_dir() and not d.name.startswith("_"):
                clients.add(d.name)
    # Clientes criados nesta sessão
    clients.update(st.session_state.get("session_clients", {}).keys())
    # Remove apagados: sessão atual + lista persistente do GitHub
    deleted = st.session_state.get("deleted_clients", set()) | _fetch_deleted_clients()
    clients -= deleted
    return sorted(clients)


def parse_themes(client_name: str) -> list[dict]:
    # Primeiro verifica sessão atual (cliente recém-criado)
    if client_name in st.session_state.get("session_clients", {}):
        return st.session_state["session_clients"][client_name]["themes"]
    # Depois verifica arquivo no disco
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


def parse_themes_from_text(text: str) -> list[dict]:
    themes = []
    for line in text.splitlines():
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
    # Verifica sessão primeiro
    session = st.session_state.get("session_clients", {})
    if client_name in session and session[client_name].get("context"):
        return session[client_name]["context"]
    # Depois verifica disco
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


def save_to_github(client_name: str, files: dict) -> tuple[bool, str]:
    token = os.getenv("GITHUB_TOKEN") or st.secrets.get("GITHUB_TOKEN", "")
    if not token:
        return False, "GITHUB_TOKEN não configurado nos secrets do Streamlit."

    repo = "ejgalliano/studio-conteudo"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    for path, content in files.items():
        if not content:
            continue
        url = f"https://api.github.com/repos/{repo}/contents/{path}"
        encoded = base64.b64encode(content.encode("utf-8")).decode()
        data = {
            "message": f"feat: adiciona cliente {client_name} via Studio",
            "content": encoded,
        }
        # Verifica se arquivo já existe (para pegar o sha)
        get_resp = requests.get(url, headers=headers)
        if get_resp.status_code == 200:
            data["sha"] = get_resp.json()["sha"]

        put_resp = requests.put(url, json=data, headers=headers)
        if not put_resp.ok:
            return False, f"Erro ao salvar `{path}`: {put_resp.json().get('message', 'desconhecido')}"

    return True, "ok"


def _github_headers() -> dict:
    token = os.getenv("GITHUB_TOKEN") or st.secrets.get("GITHUB_TOKEN", "")
    if not token:
        return {}
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

GITHUB_REPO = "ejgalliano/studio-conteudo"
DELETED_FILE = "_outputs/_deleted.txt"


def get_deleted_clients_github() -> set:
    """Fetch the persistent deleted-clients list from GitHub."""
    headers = _github_headers()
    if not headers:
        return set()
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{DELETED_FILE}"
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        content = base64.b64decode(resp.json()["content"]).decode("utf-8")
        return {line.strip() for line in content.splitlines() if line.strip()}
    return set()


def add_to_deleted_list_github(client_name: str):
    """Append client to the persistent deleted list in GitHub."""
    headers = _github_headers()
    if not headers:
        return
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{DELETED_FILE}"
    # Read existing list
    existing = set()
    sha = None
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        existing = {line.strip() for line in base64.b64decode(resp.json()["content"]).decode("utf-8").splitlines() if line.strip()}
        sha = resp.json()["sha"]
    existing.add(client_name)
    new_content = "\n".join(sorted(existing)) + "\n"
    data = {
        "message": f"chore: marca {client_name} como apagado",
        "content": base64.b64encode(new_content.encode("utf-8")).decode(),
    }
    if sha:
        data["sha"] = sha
    requests.put(url, json=data, headers=headers)


def remove_from_deleted_list_github(client_name: str):
    """Remove client from the persistent deleted list so it can be recreated."""
    headers = _github_headers()
    if not headers:
        return
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{DELETED_FILE}"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return
    existing = {line.strip() for line in base64.b64decode(resp.json()["content"]).decode("utf-8").splitlines() if line.strip()}
    sha = resp.json()["sha"]
    existing.discard(client_name)
    new_content = "\n".join(sorted(existing)) + "\n"
    data = {
        "message": f"chore: reativa cliente {client_name}",
        "content": base64.b64encode(new_content.encode("utf-8")).decode(),
        "sha": sha,
    }
    requests.put(url, json=data, headers=headers)


def delete_client(client_name: str) -> tuple[bool, str]:
    """Remove client from session, disk, GitHub files, and add to deleted list."""
    # Remove from session
    session = st.session_state.get("session_clients", {})
    if client_name in session:
        del st.session_state["session_clients"][client_name]

    # Remove from disk
    import shutil
    client_path = SISTEMA_PATH / "_outputs" / client_name
    if client_path.exists():
        try:
            shutil.rmtree(client_path)
        except Exception:
            pass  # Cloud filesystem pode ser read-only

    # Add to persistent deleted list in GitHub FIRST (garante que some mesmo se os arquivos ainda existirem)
    add_to_deleted_list_github(client_name)

    # Delete individual files from GitHub
    headers = _github_headers()
    if headers:
        files_to_delete = [
            f"_outputs/{client_name}/04-lista-temas.md",
            f"_outputs/{client_name}/01-mapa-empatia.md",
            f"_outputs/{client_name}/02-proposta-valor.md",
            f"_outputs/{client_name}/03-personas.md",
        ]
        for file_path in files_to_delete:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"
            get_resp = requests.get(url, headers=headers)
            if get_resp.status_code == 200:
                requests.delete(url, headers=headers, json={
                    "message": f"chore: remove cliente {client_name}",
                    "sha": get_resp.json()["sha"],
                })

    return True, "ok"


def save_themes(client_name: str, content: str):
    folder = SISTEMA_PATH / "_outputs" / client_name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "04-lista-temas.md").write_text(content, encoding="utf-8")


def extract_text(uploaded_file) -> str:
    if uploaded_file is None:
        return ""
    name = uploaded_file.name.lower()
    raw = uploaded_file.read()
    if name.endswith(".pdf"):
        doc = fitz.open(stream=raw, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    elif name.endswith(".docx"):
        doc = DocxDocument(io.BytesIO(raw))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    elif name.endswith(".txt"):
        return raw.decode("utf-8", errors="ignore")
    return ""


def save_context(client_name: str, mapa: str, proposta: str, personas: str):
    folder = SISTEMA_PATH / "_outputs" / client_name
    folder.mkdir(parents=True, exist_ok=True)
    if mapa:
        (folder / "01-mapa-empatia.md").write_text(mapa, encoding="utf-8")
    if proposta:
        (folder / "02-proposta-valor.md").write_text(proposta, encoding="utf-8")
    if personas:
        (folder / "03-personas.md").write_text(personas, encoding="utf-8")


# ── Session state ─────────────────────────────────────────────────────────────

defaults = {
    "selected_theme": None,
    "generated_caption": "",
    "document_items": [],
    "last_client": "",
    "pilar_filter": "Todos",
    "selected_format": "📱 Card Único",
    "novo_cliente_temas": None,
    "novo_cliente_temas_raw": "",
    "objetivos_extraidos": "",
    "session_clients": {},  # {nome: {"themes": [...], "context": {}}}
    "confirm_delete_client": "",
    "deleted_clients": set(),  # clientes apagados nesta sessão — ocultos imediatamente
    "goto_novo_cliente": "",   # pré-preenche o nome ao redirecionar para Novo Cliente
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("### 🎯 Studio de Conteúdo")
st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_studio, tab_novo = st.tabs(["📋 Gerar Conteúdo", "➕ Novo Cliente"])


# ════════════════════════════════════════════════════════════
# TAB 1 — STUDIO (tema + legenda)
# ════════════════════════════════════════════════════════════
with tab_studio:

    clients = get_clients()

    if not clients:
        st.info("Nenhum cliente encontrado. Use a aba **➕ Novo Cliente** para cadastrar.")
        st.stop()

    top_left, top_mid, top_del, top_right = st.columns([3, 3, 1, 2])
    with top_left:
        client = st.selectbox("Cliente", clients, label_visibility="collapsed", key="client_select")
    with top_mid:
        if st.button("🔄 Resetar temas", use_container_width=True, help="Apaga os temas atuais para gerar novas ideias"):
            if client in st.session_state.get("session_clients", {}):
                del st.session_state["session_clients"][client]
            themes_path = SISTEMA_PATH / "_outputs" / client / "04-lista-temas.md"
            if themes_path.exists():
                try:
                    themes_path.unlink()
                except Exception:
                    pass
            st.session_state.selected_theme = None
            st.session_state.generated_caption = ""
            st.session_state.confirm_delete_client = ""
            st.session_state.goto_novo_cliente = client   # pré-preenche e redireciona
            st.rerun()
    with top_del:
        if st.button("🗑️", use_container_width=True, help="Apagar este cliente permanentemente"):
            st.session_state.confirm_delete_client = client
            st.rerun()
    with top_right:
        doc_count = len(st.session_state.document_items)
        st.markdown(f"<div class='status-bar'>📄 {doc_count} no documento</div>", unsafe_allow_html=True)

    # Confirmation bar
    if st.session_state.confirm_delete_client == client:
        st.warning(f"⚠️ Tem certeza que deseja **apagar o cliente {client}** permanentemente? Isso remove os temas do GitHub também.")
        conf_yes, conf_no, _ = st.columns([2, 2, 4])
        with conf_yes:
            if st.button("✅ Sim, apagar", type="primary", use_container_width=True, key="confirm_del_yes"):
                with st.spinner("Apagando cliente..."):
                    ok, msg = delete_client(client)
                # Marca como apagado imediatamente na sessão e limpa cache
                st.session_state.deleted_clients.add(client)
                _fetch_deleted_clients.clear()
                st.session_state.confirm_delete_client = ""
                st.session_state.selected_theme = None
                st.session_state.generated_caption = ""
                st.session_state.last_client = ""
                if ok:
                    st.success(f"✅ Cliente **{client}** apagado com sucesso.")
                else:
                    st.error(f"❌ {msg}")
                st.rerun()
        with conf_no:
            if st.button("❌ Cancelar", use_container_width=True, key="confirm_del_no"):
                st.session_state.confirm_delete_client = ""
                st.rerun()

    if client != st.session_state.last_client:
        st.session_state.selected_theme = None
        st.session_state.generated_caption = ""
        st.session_state.last_client = client

    themes = parse_themes(client)
    client_context = load_client_context(client)
    guia = load_guia()

    if not themes:
        st.warning(f"Nenhum tema encontrado para **{client}**.")
        st.stop()

    left, right = st.columns([2, 2.5], gap="large")

    # ── LEFT: theme list ──
    with left:
        st.markdown(f"**📋 Temas — {client}** &nbsp; <span style='color:#888;font-size:13px'>{len(themes)} temas</span>", unsafe_allow_html=True)

        search = st.text_input("🔍", placeholder="Buscar tema...", label_visibility="collapsed")

        f1, f2, f3, f4 = st.columns(4)
        if f1.button("Todos", use_container_width=True):
            st.session_state.pilar_filter = "Todos"
        if f2.button("🔴 Com.", use_container_width=True):
            st.session_state.pilar_filter = "Comercial"
        if f3.button("🔵 Inst.", use_container_width=True):
            st.session_state.pilar_filter = "Institucional"
        if f4.button("🟢 Edu.", use_container_width=True):
            st.session_state.pilar_filter = "Educativo"

        filtered = themes
        if search:
            filtered = [t for t in filtered if search.lower() in t["tema"].lower()]
        if st.session_state.pilar_filter != "Todos":
            filtered = [t for t in filtered if st.session_state.pilar_filter in t["pilar"]]

        st.caption(f"{len(filtered)} temas exibidos")

        used_nums = {item.get("theme_num") for item in st.session_state.document_items}
        df = pd.DataFrame([{
            "#": t["num"],
            "Pilar": pilar_emoji(t["pilar"]),
            "Tema": ("✅ " if t["num"] in used_nums else "") + t["tema"],
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
            row_idx = event.selection.rows[0]
            new_theme = filtered[row_idx]
            if st.session_state.selected_theme != new_theme:
                st.session_state.selected_theme = new_theme
                st.session_state.generated_caption = ""

    # ── RIGHT: caption generator ──
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

            st.markdown("**Formato do post:**")
            fmt_cols = st.columns(5)
            formats = ["📱 Card Único", "🎠 Carrossel", "🎬 Reels", "📖 Stories", "💰 Tráfego Pago"]

            for i, fmt in enumerate(formats):
                if fmt_cols[i].button(fmt, key=f"fmt_{i}", use_container_width=True,
                                      type="primary" if st.session_state.selected_format == fmt else "secondary"):
                    st.session_state.selected_format = fmt
                    st.session_state.generated_caption = ""

            st.markdown("")

            if st.button("⚡ Gerar Legenda", type="primary", use_container_width=True):
                if not os.getenv("GROQ_API_KEY"):
                    st.error("GROQ_API_KEY não configurada.")
                else:
                    with st.spinner("Gerando legenda..."):
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

            if st.session_state.generated_caption:
                st.markdown("---")
                st.markdown("**📝 Legenda gerada — edite se necessário:**")

                # Se há uma atualização pendente (pós-refinamento), limpa a chave
                # ANTES do widget ser renderizado, para ele usar o novo value=
                if st.session_state.pop("_refresh_caption", False):
                    st.session_state.pop("caption_editor", None)

                edited = st.text_area(
                    "legenda",
                    value=st.session_state.generated_caption,
                    height=420,
                    label_visibility="collapsed",
                    key="caption_editor",
                )

                # ── Ajuste com IA ──
                st.markdown("**✏️ Ajustar com IA:**")
                adj_col, btn_col = st.columns([5, 1])
                with adj_col:
                    ajuste_texto = st.text_input(
                        "ajuste",
                        placeholder='Ex: "Deixe mais curto", "Tom mais descontraído", "Troque o CTA por WhatsApp"...',
                        label_visibility="collapsed",
                        key="ajuste_instrucao",
                    )
                with btn_col:
                    if st.button("Ajustar", use_container_width=True, type="secondary"):
                        if ajuste_texto.strip():
                            with st.spinner("Ajustando..."):
                                try:
                                    refinado = refine_caption(edited, ajuste_texto.strip())
                                    st.session_state.generated_caption = refinado
                                    st.session_state["ajuste_instrucao"] = ""
                                    st.session_state["_refresh_caption"] = True  # sinaliza para limpar key no próximo render
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erro ao ajustar: {e}")
                        else:
                            st.warning("Digite uma instrução de ajuste primeiro.")

                st.markdown("")
                btn_add, btn_regen, btn_clear = st.columns([3, 2, 1])

                with btn_add:
                    if st.button("✅ Adicionar ao documento", type="primary", use_container_width=True):
                        item = {
                            "num": len(st.session_state.document_items) + 1,
                            "theme_num": theme["num"],
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
                    if st.button("🗑️", use_container_width=True, help="Limpar"):
                        st.session_state.generated_caption = ""
                        st.rerun()

    # ── Document section ──
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
        st.caption("Nenhum conteúdo aprovado ainda.")
    else:
        for i, item in enumerate(st.session_state.document_items):
            with st.expander(
                f"#{item['num']} | {pilar_emoji(item['pilar'])} {item['pilar']} | {item['tema']} | {item['formato']}",
                expanded=False,
            ):
                col_content, col_remove = st.columns([6, 1])
                with col_content:
                    st.text(item["conteudo"])
                with col_remove:
                    if st.button("🗑️ Remover", key=f"remove_{i}", use_container_width=True):
                        st.session_state.document_items.pop(i)
                        for j, d in enumerate(st.session_state.document_items):
                            d["num"] = j + 1
                        st.rerun()


# ════════════════════════════════════════════════════════════
# TAB 2 — NOVO CLIENTE
# ════════════════════════════════════════════════════════════
with tab_novo:
    # Redireciona automaticamente para esta aba após "Resetar temas"
    _goto = st.session_state.get("goto_novo_cliente", "")
    if _goto:
        st.markdown(f"""
        <script>
        setTimeout(function() {{
            const tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
            if (tabs.length > 1) tabs[1].click();
        }}, 200);
        </script>
        """, unsafe_allow_html=True)
        st.info(f"✅ Temas de **{_goto}** resetados. Recarregue os documentos e clique em **⚡ Gerar Lista de Temas** para criar novas ideias.")

    st.markdown("### ➕ Cadastrar Novo Cliente")
    st.markdown("Faça upload da transcrição do briefing — a IA extrai os objetivos automaticamente. Complemente com os demais documentos se tiver.")
    st.divider()

    nome_cliente = st.text_input(
        "Nome do cliente (sem espaços, ex: JOAO-PADARIA)",
        placeholder="NOME-DO-CLIENTE",
        value=_goto,  # pré-preenche com o nome do cliente resetado
    ).upper().strip().replace(" ", "-")

    # Limpa o redirecionamento depois de exibir
    if _goto:
        st.session_state.goto_novo_cliente = ""

    st.markdown("#### 📝 Transcrição do Briefing")
    st.caption("Aceita **.txt**, **.docx** ou **.pdf** — o conteúdo é o que importa")
    transcricao_file = st.file_uploader("Transcrição / Briefing", type=["txt", "docx", "pdf"], key="up_transcricao", label_visibility="collapsed")

    transcricao_texto = extract_text(transcricao_file) if transcricao_file else ""

    if transcricao_file and transcricao_texto:
        col_info, col_btn = st.columns([3, 1])
        with col_info:
            st.success(f"✅ Transcrição carregada: **{transcricao_file.name}** ({len(transcricao_texto):,} caracteres)")
        with col_btn:
            if st.button("🤖 Extrair Objetivos", use_container_width=True, type="primary"):
                with st.spinner("Lendo a transcrição e extraindo objetivos..."):
                    try:
                        resultado = extract_objectives(transcricao_texto)
                        # Seta diretamente no key do widget para aparecer imediatamente
                        st.session_state["objetivos_editor"] = resultado
                    except Exception as e:
                        st.error(f"Erro ao extrair objetivos: {e}")

    st.markdown("#### 🎯 Objetivos do Cliente")
    objetivos = st.text_area(
        "objetivos",
        placeholder="Clique em 'Extrair Objetivos' após carregar a transcrição, ou escreva manualmente...",
        height=220,
        label_visibility="collapsed",
        key="objetivos_editor",
    )

    st.markdown("#### 📂 Documentos Estratégicos *(opcional — se já tiver prontos)*")
    st.caption("Aceita **.txt**, **.docx** ou **.pdf**")

    col_a, col_b = st.columns(2)
    with col_a:
        mapa_file    = st.file_uploader("🧠 Mapa de Empatia", type=["txt", "docx", "pdf"], key="up_mapa")
        proposta_file = st.file_uploader("💎 Proposta de Valor", type=["txt", "docx", "pdf"], key="up_prop")
    with col_b:
        personas_file = st.file_uploader("👤 Personas", type=["txt", "docx", "pdf"], key="up_pers")

    mapa_empatia   = extract_text(mapa_file)
    proposta_valor = extract_text(proposta_file)
    personas       = extract_text(personas_file)

    st.markdown("#### 💬 Instruções Adicionais *(opcional)*")
    instrucoes = st.text_area(
        "instrucoes",
        placeholder="Ex: Focar em conteúdo para WhatsApp, evitar temas sobre financiamento, priorizar datas comemorativas de maio...",
        height=100,
        label_visibility="collapsed",
    )

    st.divider()

    if st.button("⚡ Gerar Lista de Temas", type="primary", use_container_width=True):
        if not nome_cliente:
            st.error("Preencha o nome do cliente.")
        elif not any([objetivos, mapa_empatia, proposta_valor, personas, transcricao_texto]):
            st.error("Preencha pelo menos um dos campos estratégicos.")
        elif not os.getenv("GROQ_API_KEY"):
            st.error("GROQ_API_KEY não configurada.")
        else:
            st.info("Gerando temas em 3 etapas. Cada etapa leva ~20–30 segundos. Total estimado: 1–2 minutos.")
            progress = st.progress(0, text="Iniciando...")
            status = st.empty()

            try:
                etapas = {"Comercial": 33, "Institucional": 66, "Educativo": 100}
                labels = ["🔴", "🔵", "🟢"]
                descricoes = ["Comercial (etapa 1/3)", "Institucional (etapa 2/3)", "Educativo (etapa 3/3)"]

                def update_progress(pilar):
                    pct = list(etapas.keys()).index(pilar)
                    progress.progress(pct * 33, text=f"Gerando temas {labels[pct]} {descricoes[pct]} — aguarde...")
                    status.caption(f"⏳ Chamando IA para gerar temas {pilar}... isso pode levar até 30 segundos.")

                raw = generate_themes(
                    client_name=nome_cliente,
                    mapa_empatia=mapa_empatia or transcricao_texto[:3000],
                    proposta_valor=proposta_valor,
                    personas=personas,
                    objetivos=objetivos + ("\n\n## INSTRUÇÕES ADICIONAIS:\n" + instrucoes if instrucoes else ""),
                    progress_callback=update_progress,
                )
                progress.progress(100, text="Concluído!")
                temas_parsed = parse_themes_from_text(raw)
                st.session_state.novo_cliente_temas = temas_parsed
                st.session_state.novo_cliente_temas_raw = raw
            except Exception as e:
                st.error(f"Erro ao gerar temas: {e}")

    # Show generated themes for approval
    if st.session_state.novo_cliente_temas:
        temas = st.session_state.novo_cliente_temas
        st.success(f"✅ {len(temas)} temas gerados para **{nome_cliente}**! Revise abaixo e confirme.")

        df_preview = pd.DataFrame([{
            "#": t["num"],
            "Pilar": t["pilar"],
            "Tema": t["tema"],
            "Formato": t["formato"],
            "Persona": t["persona"],
        } for t in temas])

        st.dataframe(df_preview, use_container_width=True, height=400, hide_index=True)

        st.markdown("**Distribuição:**")
        comercial = sum(1 for t in temas if "Comercial" in t["pilar"])
        institucional = sum(1 for t in temas if "Institucional" in t["pilar"])
        educativo = sum(1 for t in temas if "Educativo" in t["pilar"])
        c1, c2, c3 = st.columns(3)
        c1.metric("🔴 Comercial", comercial)
        c2.metric("🔵 Institucional", institucional)
        c3.metric("🟢 Educativo", educativo)

        st.divider()
        st.markdown("**Confirmar e salvar este cliente?**")
        col_ok, col_cancel = st.columns([2, 1])

        with col_ok:
            if st.button("✅ Confirmar e usar no Studio", type="primary", use_container_width=True):
                if not nome_cliente:
                    st.error("Nome do cliente em branco.")
                else:
                    # Se o cliente estava na lista negra (apagado antes), remove de lá
                    if nome_cliente in st.session_state.get("deleted_clients", set()):
                        st.session_state["deleted_clients"].discard(nome_cliente)
                    remove_from_deleted_list_github(nome_cliente)
                    _fetch_deleted_clients.clear()

                    # Salva na sessão atual (disponível imediatamente)
                    st.session_state["session_clients"][nome_cliente] = {
                        "themes": temas,
                        "context": {
                            "01-mapa-empatia.md": mapa_empatia,
                            "02-proposta-valor.md": proposta_valor,
                            "03-personas.md": personas,
                        }
                    }
                    # Tenta salvar no disco também
                    try:
                        header = "| Nº | Pilar | Tema | Formato Sugerido | Persona-Alvo |\n|---|---|---|---|---|\n"
                        full_content = f"# LISTA DE TEMAS — {nome_cliente}\n\n" + header + "\n".join(
                            f"| {t['num']} | {t['pilar']} | {t['tema']} | {t['formato']} | {t['persona']} |"
                            for t in temas
                        )
                        save_themes(nome_cliente, full_content)
                        save_context(nome_cliente, mapa_empatia, proposta_valor, personas)
                    except Exception:
                        pass  # Disco pode ser read-only no cloud

                    st.session_state.novo_cliente_temas = None
                    st.session_state.novo_cliente_temas_raw = ""
                    st.success(f"✅ Cliente **{nome_cliente}** pronto! Clique na aba **📋 Gerar Conteúdo** e selecione-o.")
                    st.balloons()
                    st.rerun()

        with col_cancel:
            if st.button("🔄 Gerar novamente", use_container_width=True):
                st.session_state.novo_cliente_temas = None
                st.session_state.novo_cliente_temas_raw = ""
                st.rerun()

        # Salvar permanentemente no GitHub
        st.divider()
        st.markdown("#### 💾 Salvar permanentemente")
        st.caption("Salva os temas no GitHub para ficarem disponíveis mesmo após reiniciar o app.")
        if st.button("☁️ Salvar no GitHub", use_container_width=True):
            if not nome_cliente:
                st.error("Nome do cliente em branco.")
            else:
                with st.spinner("Salvando no GitHub..."):
                    header = "| Nº | Pilar | Tema | Formato Sugerido | Persona-Alvo |\n|---|---|---|---|---|\n"
                    temas_content = f"# LISTA DE TEMAS — {nome_cliente}\n\n" + header + "\n".join(
                        f"| {t['num']} | {t['pilar']} | {t['tema']} | {t['formato']} | {t['persona']} |"
                        for t in temas
                    )
                    files = {
                        f"_outputs/{nome_cliente}/04-lista-temas.md": temas_content,
                        f"_outputs/{nome_cliente}/01-mapa-empatia.md": mapa_empatia,
                        f"_outputs/{nome_cliente}/02-proposta-valor.md": proposta_valor,
                        f"_outputs/{nome_cliente}/03-personas.md": personas,
                    }
                    ok, msg = save_to_github(nome_cliente, files)
                    if ok:
                        st.success("✅ Salvo no GitHub! O cliente estará disponível permanentemente.")
                    else:
                        st.error(f"❌ {msg}")
