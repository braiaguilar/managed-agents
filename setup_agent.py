"""
setup_agent.py
Script de setup UNA sola vez: crea el environment y el agent persistente,
luego guarda sus IDs en .env para que run.py los lea.

Pre-requisitos en .env:
  ANTHROPIC_API_KEY=...
  MCP_SERVER_URL=https://xxx.trycloudflare.com/mcp   (URL pública del MCP)
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv, set_key
import anthropic

# ── 0. Credenciales y validación ───────────────────────────────────────────────
# Cargamos .env antes de leer variables de entorno.
# Si MCP_SERVER_URL no está, fallamos rápido con mensaje claro.
load_dotenv()

mcp_server_url = os.environ.get("MCP_SERVER_URL", "").strip()
if not mcp_server_url:
    sys.exit(
        "ERROR: MCP_SERVER_URL no está definido en .env.\n"
        "Agregá la URL pública de tu servidor MCP (ej. https://xxx.trycloudflare.com/mcp)."
    )

client = anthropic.Anthropic()  # lee ANTHROPIC_API_KEY del entorno
DOTENV_PATH = Path(__file__).parent / ".env"


# ── 1. Environment ─────────────────────────────────────────────────────────────
# El environment es el sandbox cloud reutilizable donde corren las tools.
# "networking": "unrestricted" permite que el agente acceda a internet (PokéAPI).
# Guardamos el ID para apuntarle desde cada session; el environment no se recrea.
print("► [1/2] Creando environment...")
environment = client.beta.environments.create(
    name="pokeapi-env",
    config={
        "type": "cloud",
        "networking": {"type": "unrestricted"},
    },
)
print(f"  Environment ID : {environment.id}")


# ── 2. System prompt ────────────────────────────────────────────────────────────
# El system prompt vive en system_prompt.txt para poder versionarlo en git
# sin tener que editar código Python.
system_prompt_path = Path(__file__).parent / "system_prompt.txt"
system_prompt = system_prompt_path.read_text(encoding="utf-8").strip()
print(f"  System prompt  : {len(system_prompt)} caracteres leídos de system_prompt.txt")


# ── 3. Agent ────────────────────────────────────────────────────────────────────
# El agent es el objeto persistente y versionado: model, system y tools viven aquí.
#
# Estructura MCP (dos arrays que se vinculan por nombre):
#   mcp_servers  — declara la conexión: tipo URL, nombre único, endpoint.
#   tools        — lista qué usar: "mcp_toolset" referencia ese nombre.
# La API rechaza entradas sin referencia cruzada en ambos sentidos.
#
# Sin agent_toolset_20260401 → principio de least privilege: el agente solo
# puede llamar las 3 tools del MCP, nada de bash/archivos/web.
#
# permission_policy "always_allow" → las tools son solo lectura (GET a PokéAPI),
# no necesitan confirmación manual en cada llamada.
print("► [2/2] Creando agent...")
agent = client.beta.agents.create(
    name="pokeapi-agent",
    model="claude-sonnet-4-6",
    system=system_prompt,
    mcp_servers=[
        {
            "type": "url",
            "name": "pokeapi",       # nombre único dentro del agent
            "url": mcp_server_url,   # leído de .env, nunca hardcodeado
        },
    ],
    tools=[
        {
            "type": "mcp_toolset",
            "mcp_server_name": "pokeapi",   # debe coincidir con mcp_servers[].name
            "default_config": {
                "permission_policy": {"type": "always_allow"},
            },
        },
    ],
)
print(f"  Agent ID       : {agent.id}")
print(f"  Version        : {agent.version}")


# ── 4. Guardar IDs en .env ──────────────────────────────────────────────────────
# set_key agrega la clave si no existe o actualiza su valor si ya estaba.
# Así si corrés el script dos veces no hay duplicados en el archivo.
set_key(DOTENV_PATH, "AGENT_ID", agent.id)
set_key(DOTENV_PATH, "ENVIRONMENT_ID", environment.id)

print(f"\n✓ IDs guardados en {DOTENV_PATH.name}:")
print(f"  AGENT_ID       = {agent.id}")
print(f"  ENVIRONMENT_ID = {environment.id}")
print("\nPróximo paso: corré python run.py para iniciar una session.")
