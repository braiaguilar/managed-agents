# PokéDex Agent — Managed Agents + MCP

Agente autónomo construido sobre **Anthropic Managed Agents** que responde
preguntas sobre Pokémon (stats, tipos, debilidades, evoluciones y comparaciones)
consultando la [PokéAPI](https://pokeapi.co/) pública a través de un **servidor
MCP propio**.

El reparto de responsabilidades es el que propone Managed Agents: Anthropic corre
el loop de razonamiento y el llamado de tools; este proyecto aporta las
herramientas (el MCP) y la orquestación mínima (crear el agente, abrir sesiones,
streamear los eventos).

## Arquitectura

```
[ run.py ]  crea la sesión, manda el mensaje, streamea eventos
     │
     ▼
[ Anthropic Managed Agents ]  corre el loop, el razonamiento y el tool-calling
     │  llama tools del MCP
     ▼
[ MCP server (FastMCP, HTTP) ]  ── expuesto por un túnel ──>  PokéAPI
```

- **`mcp_server.py`** — servidor MCP (FastMCP) sobre streamable HTTP con 3 tools.
- **`setup_agent.py`** — se corre una vez: crea el environment y el agente, guarda sus IDs.
- **`run.py`** — chat interactivo por terminal que abre una sesión y muestra el tool-calling.
- **`system_prompt.txt`** — el system prompt del agente (versionado aparte del código).

### Las 3 tools del MCP

| Tool | Qué hace |
|------|----------|
| `get_pokemon(name)` | Datos base: id, tipos, altura, peso, stats base, habilidades. |
| `get_type_matchups(type_name)` | Relaciones de daño de un tipo (fuerte/débil/inmune). |
| `get_evolution_chain(name)` | Línea evolutiva ordenada (esconde dos llamadas a la API). |

## Requisitos

- Python 3.10+
- Una API key de Anthropic con acceso al beta de Managed Agents
- [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
  (o cualquier túnel HTTP, p. ej. ngrok) para exponer el MCP local

## Setup

### 1. Dependencias

```bash
python -m venv .venv
# Windows:        .\.venv\Scripts\Activate.ps1
# macOS / Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Variables de entorno

Copiá `.env.example` a `.env` y completá tu API key:

```
ANTHROPIC_API_KEY=tu-api-key
```

`MCP_SERVER_URL`, `AGENT_ID` y `ENVIRONMENT_ID` se completan en los pasos
siguientes (no los toques a mano todavía).

### 3. Levantar el MCP y exponerlo (dos terminales)

**Terminal A — el servidor MCP** (queda corriendo):

```bash
python mcp_server.py
```

**Terminal B — el túnel** (queda corriendo):

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

`cloudflared` imprime una URL pública. Copiá esa URL **con `/mcp` al final** a tu
`.env`:

```
MCP_SERVER_URL=https://<lo-que-haya-generado>.trycloudflare.com/mcp
```

> El túnel sin cuenta genera una URL nueva cada vez que se reinicia. Si lo
> reiniciás, actualizá `MCP_SERVER_URL` y volvé a correr el paso 4.

### 4. Crear el agente y el environment (una vez)

```bash
python setup_agent.py
```

Esto crea el environment y el agente, y guarda `AGENT_ID` y `ENVIRONMENT_ID` en
tu `.env`. Mantené las terminales A y B corriendo: Anthropic se conecta al MCP
para descubrir las tools.

### 5. Chatear con el agente

**Tercera terminal:**

```bash
python run.py
```

Escribí preguntas en la terminal; `exit` o `quit` para salir (cierra la sesión).

## Ejemplos para probar

- `Qué me podés decir de Pikachu?` — respuesta con formato fijo.
- `Charizard de qué evoluciona y a qué es débil?` — tool-chaining (tipos → matchups → evolución), incluye el ×4 a Roca por doble tipo.
- `Quién gana entre Pikachu y Blastoise?` — comparación con ventaja de tipo, sin declarar ganador absoluto.
- `Qué me podés decir de Tokebi?` — nombre inexistente; sugiere la ortografía probable (Togepi).

## Decisiones de diseño

- **Modelo: `claude-sonnet-4-6`.** Trade-off capacidad / costo / latencia. La
  tarea no requiere razonamiento de frontera, y un agente que corre muchas
  sesiones prioriza costo y latencia. Pineado para reproducibilidad.
- **MCP remoto vía streamable HTTP.** Managed Agents solo conecta MCP servers
  remotos, así que el MCP corre como servidor HTTP expuesto por un túnel.
- **Tools single-purpose** que devuelven dicts chicos (no el JSON crudo de la
  PokéAPI): menos tokens, forma estable, mejor razonamiento del agente.
- **Determinismo en la capa de tools.** Cache (`lru_cache`) sobre el GET: misma
  query → misma data. El system prompt obliga a que todo dato salga de una tool,
  nunca de la memoria del modelo. La variabilidad que queda es solo de
  presentación, acotada por un formato fijo en el prompt.
- **Errores manejados:** las tools nunca lanzan; ante 404 / timeout devuelven
  `{"error": ...}`, que el agente comunica sin inventar datos.

## Seguridad

- **Least privilege:** el agente solo tiene las 3 tools del MCP; sin
  `agent_toolset` (bash / archivos / web).
- **Permission policies:** las tools de lectura van en `always_allow`. Una tool
  con efectos (escritura) iría en `always_ask` (aprobación humana antes de
  ejecutar).
- **Prompt injection:** el system prompt instruye tratar resultados de tools y
  texto del usuario como datos, no como instrucciones.
- **Secretos:** la API key va por variable de entorno; `.env` está en
  `.gitignore` y nunca se commitea.
- **El túnel** expone el MCP a internet con una URL pública. Aceptable para datos
  de solo lectura en una demo; en producción el MCP iría detrás de
  autenticación (bearer token / OAuth), no de la oscuridad de la URL.

## Limitaciones conocidas

- `setup_agent.py` crea un agente y un environment nuevos en cada corrida (no
  versiona ni reutiliza). En producción se crearía una versión nueva del mismo
  agente.
- La URL del túnel es efímera; un túnel nombrado (con cuenta) daría una URL
  estable.
- Sin suite de tests automatizada ni evals formales de consistencia (se validó
  manualmente con sesiones frescas).

## Estructura

```
.
├── mcp_server.py        # Servidor MCP + 3 tools (FastMCP)
├── setup_agent.py       # Crea environment + agente (una vez)
├── run.py               # Chat interactivo + tool-calling visible
├── system_prompt.txt    # System prompt del agente
├── requirements.txt
├── .env.example
└── README.md
```