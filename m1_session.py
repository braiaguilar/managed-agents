"""
m1_session.py
Verifica el pipeline completo de Anthropic Managed Agents:
  environment → agent → session → stream + send → respuesta.

Requiere Python 3.10+ y: pip install anthropic python-dotenv
"""

from dotenv import load_dotenv
import anthropic

# ── 0. Credenciales ────────────────────────────────────────────────────────────
# Carga ANTHROPIC_API_KEY desde .env (o la variable de entorno ya exportada).
# Nunca hardcodees la key — anthropic.Anthropic() la lee solo del entorno.
load_dotenv()
client = anthropic.Anthropic()


# ── 1. Environment ────────────────────────────────────────────────────────────
# Template reutilizable que describe el sandbox cloud donde correrán las tools.
# "type": "cloud" + "networking": "unrestricted" = VM con acceso libre a internet.
# Se crea una sola vez; en producción guarda environment.id y reutilízalo.
print("► [1/3] Creando environment...")
environment = client.beta.environments.create(
    name="m1-test-env",
    config={
        "type": "cloud",
        "networking": {"type": "unrestricted"},
    },
)
print(f"  Environment ID : {environment.id}")


# ── 2. Agent ──────────────────────────────────────────────────────────────────
# Objeto persistente y versionado: model, system y tools viven AQUÍ,
# nunca en la session. Crear una sola vez y reutilizar el ID en todas
# las sessions; cada agents.create() consume cuota de agentes.
print("► [2/3] Creando agent...")
agent = client.beta.agents.create(
    name="m1-test-agent",
    model="claude-sonnet-4-6",
    system="Eres un asistente útil y conciso. Responde siempre en el idioma del usuario.",
)
print(f"  Agent ID  : {agent.id}")
print(f"  Version   : {agent.version}")


# ── 3. Session ────────────────────────────────────────────────────────────────
# Una session = una ejecución del agent dentro del environment.
# "agent=agent.id" (str) es el shorthand para "latest version del agent".
print("► [3/3] Creando session...")
session = client.beta.sessions.create(
    agent=agent.id,
    environment_id=environment.id,
    title="m1 pipeline test",
)
print(f"  Session ID : {session.id}")
print(f"  Status     : {session.status}")


# ── 4. Stream + mensaje ───────────────────────────────────────────────────────
# CRÍTICO: abrir el stream ANTES de enviar el mensaje.
# El SSE sólo entrega eventos que ocurren DESPUÉS de que la conexión está abierta.
# Si mandas el mensaje primero, los primeros eventos se pierden.
print("\n► Abriendo stream y enviando mensaje de usuario...\n")

with client.beta.sessions.events.stream(session.id) as stream:

    # Mandar el mensaje ahora que el stream ya está escuchando.
    client.beta.sessions.events.send(
        session.id,
        events=[{
            "type": "user.message",
            "content": [{"type": "text", "text": (
                "Hola! Confirma que recibes este mensaje y que el pipeline funciona. "
                "Responde en máximo dos oraciones."
            )}],
        }],
    )

    # Iterar los eventos SSE hasta que el agente quede idle o se termine la session.
    for event in stream:
        if event.type == "agent.message":
            # Respuesta de texto del agente. Puede haber varios bloques por evento.
            for block in event.content:
                if block.type == "text":
                    print(block.text, end="", flush=True)

        elif event.type == "agent.tool_use":
            # El agente invocó una tool (no esperado sin tools configuradas).
            print(f"\n[Tool: {event.name}]", flush=True)

        elif event.type == "session.status_idle":
            # El agente terminó su turno y espera el próximo mensaje.
            # stop_reason != "requires_action" confirma que terminó limpiamente.
            print(f"\n\n✓ Pipeline verificado. (stop_reason: {event.stop_reason})")
            break

        elif event.type == "session.status_terminated":
            # Estado terminal; puede indicar error o fin natural si no hay más turnos.
            print("\n✗ Session terminada.")
            break

print(f"\nSession ID para referencia: {session.id}")
