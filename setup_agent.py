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

load_dotenv()

mcp_server_url = os.environ.get("MCP_SERVER_URL", "").strip()
if not mcp_server_url:
    sys.exit(
        "ERROR: MCP_SERVER_URL no está definido en .env.\n"
        "Agregá la URL pública de tu servidor MCP (ej. https://xxx.trycloudflare.com/mcp)."
    )

client = anthropic.Anthropic()
DOTENV_PATH = Path(__file__).parent / ".env"


print("► [1/2] Creando environment...")
environment = client.beta.environments.create(
    name="pokeapi-env",
    config={
        "type": "cloud",
        "networking": {"type": "unrestricted"},
    },
)
print(f"  Environment ID : {environment.id}")


system_prompt_path = Path(__file__).parent / "system_prompt.txt"
system_prompt = system_prompt_path.read_text(encoding="utf-8").strip()
print(f"  System prompt  : {len(system_prompt)} caracteres leídos de system_prompt.txt")

# MCP structure (two arrays with cross-references):
#   mcp_servers[].name       — "pokeapi" (referenced by tools)
#   tools[].mcp_server_name  — "pokeapi" (references the server)
# The API rejects definitions with unreferenced servers or dangling toolsets.
#
# No agent_toolset_20260401 → least privilege: agent can only call the MCP tools.
#
# permission_policy "always_allow" → read-only tools run without confirmation.
print("► [2/2] Creando agent...")
agent = client.beta.agents.create(
    name="pokeapi-agent",
    model="claude-sonnet-4-6",
    system=system_prompt,
    mcp_servers=[
        {
            "type": "url",
            "name": "pokeapi",
            "url": mcp_server_url,
        },
    ],
    tools=[
        {
            "type": "mcp_toolset",
            "mcp_server_name": "pokeapi",
            "default_config": {
                "permission_policy": {"type": "always_allow"},
            },
        },
    ],
)
print(f"  Agent ID       : {agent.id}")
print(f"  Version        : {agent.version}")

set_key(DOTENV_PATH, "AGENT_ID", agent.id)
set_key(DOTENV_PATH, "ENVIRONMENT_ID", environment.id)

print(f"\n✓ IDs guardados en {DOTENV_PATH.name}:")
print(f"  AGENT_ID       = {agent.id}")
print(f"  ENVIRONMENT_ID = {environment.id}")
print("\nPróximo paso: corré python run.py para iniciar una session.")
