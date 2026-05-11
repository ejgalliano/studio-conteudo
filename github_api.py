"""
Todas as operações com a API do GitHub em um único lugar.
"""
import base64
import os
import requests
import streamlit as st

from constants import GITHUB_REPO, DELETED_FILE


# ── Auth ──────────────────────────────────────────────────────────────────────

def _headers() -> dict:
    token = os.getenv("GITHUB_TOKEN") or st.secrets.get("GITHUB_TOKEN", "")
    if not token:
        return {}
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def _get_file(path: str) -> tuple[str | None, str | None]:
    """Returns (decoded_content, sha) or (None, None) if not found."""
    headers = _headers()
    if not headers:
        return None, None
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content, data["sha"]
    return None, None


def _put_file(path: str, content: str, message: str, sha: str | None = None) -> bool:
    headers = _headers()
    if not headers:
        return False
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode(),
    }
    if sha:
        payload["sha"] = sha
    resp = requests.put(url, json=payload, headers=headers)
    return resp.ok


def _delete_file(path: str, message: str) -> bool:
    headers = _headers()
    if not headers:
        return False
    _, sha = _get_file(path)
    if not sha:
        return True  # já não existe
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    resp = requests.delete(url, headers=headers, json={"message": message, "sha": sha})
    return resp.ok


# ── Deleted clients list ───────────────────────────────────────────────────────

def get_deleted_clients() -> set[str]:
    content, _ = _get_file(DELETED_FILE)
    if not content:
        return set()
    return {line.strip() for line in content.splitlines() if line.strip()}


def add_to_deleted(client_name: str):
    content, sha = _get_file(DELETED_FILE)
    existing = {line.strip() for line in content.splitlines() if line.strip()} if content else set()
    existing.add(client_name)
    _put_file(DELETED_FILE, "\n".join(sorted(existing)) + "\n",
              f"chore: marca {client_name} como apagado", sha)


def remove_from_deleted(client_name: str):
    content, sha = _get_file(DELETED_FILE)
    if not content or not sha:
        return
    existing = {line.strip() for line in content.splitlines() if line.strip()}
    existing.discard(client_name)
    _put_file(DELETED_FILE, "\n".join(sorted(existing)) + "\n",
              f"chore: reativa {client_name}", sha)


# ── Client files ───────────────────────────────────────────────────────────────

CLIENT_FILES = [
    "01-mapa-empatia.md",
    "02-proposta-valor.md",
    "03-personas.md",
    "04-lista-temas.md",
]


def save_client(client_name: str, files: dict[str, str]) -> tuple[bool, str]:
    """
    files = {filename: content}
    Ex: {"04-lista-temas.md": "...", "01-mapa-empatia.md": "..."}
    """
    for filename, content in files.items():
        if not content:
            continue
        path = f"_outputs/{client_name}/{filename}"
        _, sha = _get_file(path)
        ok = _put_file(path, content, f"feat: salva {client_name}/{filename}", sha)
        if not ok:
            return False, f"Erro ao salvar {filename}"
    return True, "ok"


def delete_client(client_name: str) -> tuple[bool, str]:
    """Remove todos os arquivos do cliente do GitHub e adiciona à lista negra."""
    add_to_deleted(client_name)
    for filename in CLIENT_FILES:
        _delete_file(f"_outputs/{client_name}/{filename}",
                     f"chore: remove {client_name}/{filename}")
    return True, "ok"


def load_client_context(client_name: str) -> dict[str, str]:
    """Carrega os documentos estratégicos do cliente do GitHub."""
    context = {}
    for filename in CLIENT_FILES[:3]:  # só os 3 docs (não os temas)
        content, _ = _get_file(f"_outputs/{client_name}/{filename}")
        if content:
            context[filename] = content
    return context


def load_client_themes_raw(client_name: str) -> str | None:
    """Retorna o conteúdo bruto do arquivo de temas, ou None se não existir."""
    content, _ = _get_file(f"_outputs/{client_name}/04-lista-temas.md")
    return content
