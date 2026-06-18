# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PokéDex chatbot built on **Anthropic Managed Agents** (Python SDK, `client.beta.*`). The agent answers Pokémon questions by calling 3 MCP tools that query the public PokéAPI.

## Commands

```bash
# Lint / format
ruff check .
ruff format .

# Tests
pytest
pytest path/to/test_file.py::test_name

# Run individual components
python mcp_server.py      # MCP server (keep running)
python setup_agent.py     # One-time agent/environment creation
python run.py             # Interactive chat loop
```

## Architecture

Three processes must be running for the system to work:

```
[run.py]  →  Anthropic Managed Agents (runs the loop)  →  [mcp_server.py]  →  PokéAPI
                                                    ↑
                                          [cloudflared tunnel]
                                          (exposes MCP to internet)
```

**Startup order:**
1. `python mcp_server.py` — listens on `http://127.0.0.1:8000/mcp`
2. `cloudflared tunnel --url http://127.0.0.1:8000` — copy the public URL + `/mcp` into `.env` as `MCP_SERVER_URL`
3. `python setup_agent.py` — creates the environment and agent **once**; writes `AGENT_ID` and `ENVIRONMENT_ID` to `.env`
4. `python run.py` — opens a session and starts the chat loop

`setup_agent.py` is a one-time script. Re-running it creates a new agent and environment (does not version or reuse existing ones). If the tunnel restarts, update `MCP_SERVER_URL` and re-run `setup_agent.py`.

## Managed Agents API

All calls go through `client.beta.*`. The SDK adds the required `managed-agents-2026-04-01` beta header automatically.

**Mandatory resource chain:** `environments.create()` → `agents.create()` → `sessions.create()` → stream events.

**Stream-before-send ordering:** The SSE stream must be opened *before* calling `events.send()`, or events are lost. See `run.py:_run_turn` — `events.stream()` wraps `events.send()`.

**MCP cross-reference constraint:** `agents.create()` takes two arrays that must reference each other:
- `mcp_servers[].name` (e.g. `"pokeapi"`) must match `tools[].mcp_server_name`
- The API rejects definitions where either side lacks a corresponding entry in the other

**Least privilege:** No `agent_toolset_20260401` is declared → the agent can only use the 3 MCP tools.

**Permission policy:** `"always_allow"` is set on the MCP toolset because all tools are read-only. Write-side tools would use `"always_ask"`.

**Session cleanup:** `client.beta.sessions.delete(session_id)` is the only termination method.

## MCP Server (`mcp_server.py`)

FastMCP 3 over streamable HTTP (`transport="streamable-http"` — valid alias for `"http"` in FastMCP 3.4.x, default path `/mcp`).

Uses a module-level `httpx.Client` (sync) because FastMCP runs tools in a thread pool, not an asyncio event loop.

`_get_json(url)` is cached with `lru_cache`. Callers must not mutate the returned dict — it is the live cached instance. Helper functions (`_fetch_*`) build new dicts from the cached data.

## Event Types (confirmed from SDK)

| Event type | Key fields |
|---|---|
| `agent.message` | `event.content[]` — blocks with `.type` and `.text` |
| `agent.tool_use` | `event.name`, `event.input` (dict) |
| `agent.mcp_tool_use` | `event.name`, `event.input` (dict) |
| `agent.tool_result` / `agent.mcp_tool_result` | `event.content` — list of text blocks |
| `session.status_idle` | break the stream loop; agent finished its turn |
| `session.status_terminated` | terminal state; delete session |
| `session.error` | `event.error.message` |

## Environment Variables

| Variable | Set by | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Manual (`.env`) | Anthropic API auth |
| `MCP_SERVER_URL` | Manual (`.env`) | Public cloudflared URL + `/mcp` |
| `AGENT_ID` | `setup_agent.py` | Persistent agent reference |
| `ENVIRONMENT_ID` | `setup_agent.py` | Persistent environment reference |

## Requirements

- Python 3.10+ (uses `match`/`case`)
- `anthropic==0.109.2`, `fastmcp==3.4.2`, `httpx==0.28.1`, `python-dotenv==1.2.2`
- `cloudflared` (or equivalent HTTP tunnel) to expose the local MCP server
