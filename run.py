"""
run.py
Loop de chat interactivo sobre un agent y environment ya existentes.
Crea una session nueva, muestra el tool-calling en tiempo real y elimina
la session al salir para no dejarla colgada.

Pre-requisitos en .env (generados por setup_agent.py):
  AGENT_ID=agt_01...
  ENVIRONMENT_ID=env_01...
"""

import json
import os
import sys

from dotenv import load_dotenv
import anthropic

# ── 0. Credenciales e IDs ──────────────────────────────────────────────────────
# AGENT_ID y ENVIRONMENT_ID los genera setup_agent.py y los escribe en .env.
# Si faltan, fallamos pronto con un mensaje que dice exactamente qué hacer.
load_dotenv()

agent_id = os.environ.get("AGENT_ID", "").strip()
environment_id = os.environ.get("ENVIRONMENT_ID", "").strip()

missing = [k for k, v in [("AGENT_ID", agent_id), ("ENVIRONMENT_ID", environment_id)] if not v]
if missing:
    sys.exit(
        f"ERROR: Faltan en .env: {', '.join(missing)}\n"
        "Corré python setup_agent.py primero para crear el agent y el environment."
    )

client = anthropic.Anthropic()


# ── 1. Session ─────────────────────────────────────────────────────────────────
# Una session = una instancia de ejecución del agent dentro del environment.
# El agente mantiene el historial de conversación entre turnos de la misma session.
print("Creando session...")
session = client.beta.sessions.create(
    agent=agent_id,
    environment_id=environment_id,
    title="run.py chat session",
)
print(f"Session ID : {session.id}")
print("Escribí 'exit' o 'quit' para salir.\n")


# ── 2. Lógica de un turno ──────────────────────────────────────────────────────
def _run_turn(session_id: str, user_text: str) -> bool:
    """Abre el stream, envía el mensaje y procesa eventos hasta que el agente queda idle.

    Devuelve False si la session fue terminada (session.status_terminated),
    True en todos los demás casos (incluyendo errores recuperables).
    """
    # CRÍTICO: abrir el stream ANTES del send.
    # El SSE solo entrega eventos que ocurren DESPUÉS de que la conexión está abierta.
    with client.beta.sessions.events.stream(session_id) as stream:
        client.beta.sessions.events.send(
            session_id,
            events=[{
                "type": "user.message",
                "content": [{"type": "text", "text": user_text}],
            }],
        )

        for event in stream:
            match event.type:

                case "agent.message":
                    # Respuesta de texto del agente.
                    for block in event.content:
                        if block.type == "text":
                            print(block.text, end="", flush=True)

                case "agent.tool_use":
                    # El agente llamó una tool del agent_toolset (bash, read, write…).
                    args = json.dumps(getattr(event, "input", {}), ensure_ascii=False)
                    print(f"\n[tool] {event.name}({args})", flush=True)

                case "agent.mcp_tool_use":
                    # El agente llamó una tool del MCP server (get_pokemon, etc.).
                    args = json.dumps(getattr(event, "input", {}), ensure_ascii=False)
                    print(f"\n[mcp]  {event.name}({args})", flush=True)

                case "agent.tool_result" | "agent.mcp_tool_result":
                    # Resultado de la tool; mostramos un resumen corto.
                    content = getattr(event, "content", None)
                    if content:
                        summary = str(content)[:200].replace("\n", " ")
                        print(f"\n       → {summary}", flush=True)

                case "session.error":
                    # Error a nivel de session (ej. MCP server inalcanzable).
                    msg = getattr(event.error, "message", "error desconocido") if event.error else "error desconocido"
                    print(f"\n[error de session] {msg}", flush=True)
                    break

                case "session.status_idle":
                    # El agente terminó su turno y espera el próximo mensaje.
                    # stop_reason.type == "end_turn"        → respuesta normal
                    # stop_reason.type == "requires_action" → espera confirmación de tool
                    #   (no debería ocurrir con permission_policy: always_allow)
                    print()  # nueva línea tras la respuesta del agente
                    return True

                case "session.status_terminated":
                    # Estado terminal irrecuperable.
                    print("\n[session terminada]")
                    return False

    return True


# ── 3. Loop principal ──────────────────────────────────────────────────────────
try:
    while True:
        try:
            user_input = input("Vos: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break

        print("PokéDex: ", end="", flush=True)
        try:
            keep_going = _run_turn(session.id, user_input)
        except Exception as exc:
            # Un error en un turno no tira todo el programa: muestra el error y sigue.
            print(f"\n[error en el turno] {exc}")
            keep_going = True

        if not keep_going:
            break

finally:
    # ── 4. Terminar la session ─────────────────────────────────────────────────
    # Eliminar la session libera el sandbox y evita dejarla colgada.
    print(f"\nEliminando session {session.id}...")
    try:
        client.beta.sessions.delete(session.id)
        print("Session eliminada. ¡Hasta luego!")
    except Exception as exc:
        print(f"No se pudo eliminar la session: {exc}")
