"""
mcp_server.py
Servidor MCP (FastMCP 3) sobre la PokéAPI pública.
Corre como servidor HTTP remoto compatible con Anthropic Managed Agents.

Arrancar : python mcp_server.py
Endpoint : http://127.0.0.1:8000/mcp
"""

from __future__ import annotations

import functools

import httpx
from fastmcp import FastMCP

_BASE = "https://pokeapi.co/api/v2"

_client = httpx.Client(timeout=10.0)


@functools.lru_cache(maxsize=512)
def _get_json(url: str) -> dict:
    """GET a url y devuelve el JSON parseado.

    Cacheado por URL: la PokéAPI es estática, cachear es correcto y responsable.
    Lanza httpx.HTTPStatusError / httpx.TimeoutException / httpx.NetworkError;
    las tools las capturan y devuelven un dict de error — nunca relanzar desde aquí.
    Importante: no mutar el dict devuelto (es la instancia cacheada).
    """
    resp = _client.get(url)
    resp.raise_for_status()
    return resp.json()


def _fetch_pokemon(name: str) -> dict:
    """Extrae los campos relevantes de /pokemon/{name}."""
    data = _get_json(f"{_BASE}/pokemon/{name}")
    return {
        "id":         data["id"],
        "name":       data["name"],
        "types":      [t["type"]["name"] for t in data["types"]],
        "height":     data["height"],
        "weight":     data["weight"],
        "base_stats": {s["stat"]["name"]: s["base_stat"] for s in data["stats"]},
        "abilities":  [a["ability"]["name"] for a in data["abilities"]],
    }


def _fetch_type(type_name: str) -> dict:
    """Extrae las seis relaciones de daño de /type/{type_name}."""
    data = _get_json(f"{_BASE}/type/{type_name}")
    dr = data["damage_relations"]
    return {
        "name":         data["name"],
        "strong_against": [t["name"] for t in dr["double_damage_to"]],
        "weak_against":   [t["name"] for t in dr["half_damage_to"]],
        "no_effect_to":   [t["name"] for t in dr["no_damage_to"]],
        "weak_to":        [t["name"] for t in dr["double_damage_from"]],
        "resists":        [t["name"] for t in dr["half_damage_from"]],
        "immune_to":      [t["name"] for t in dr["no_damage_from"]],
    }


def _walk_chain(node: dict) -> list[str]:
    """Recorre recursivamente un nodo evolution-chain y devuelve nombres en orden."""
    names = [node["species"]["name"]]
    for next_node in node["evolves_to"]:
        names.extend(_walk_chain(next_node))
    return names


def _fetch_evolution_chain(name: str) -> list[str]:
    """Devuelve la línea evolutiva de name como lista ordenada de nombres.

    Dos pedidos a la PokéAPI:
      1. /pokemon-species/{name}  →  obtiene la URL del evolution-chain
      2. /evolution-chain/{id}    →  recorre el árbol recursivamente
    """
    species = _get_json(f"{_BASE}/pokemon-species/{name}")
    chain_url = species["evolution_chain"]["url"]
    chain_data = _get_json(chain_url)
    return _walk_chain(chain_data["chain"])


mcp = FastMCP("PokeAPI MCP")


@mcp.tool
def get_pokemon(name: str) -> dict:
    """Obtiene datos básicos de un Pokémon por nombre o ID.

    Devuelve id, name, types (lista de strings), height (decímetros),
    weight (hectogramos), base_stats (dict stat→valor) y abilities (lista).
    Devuelve {"error": "..."} si el Pokémon no existe o hay problemas de red.

    Args:
        name: Nombre o número del Pokémon, e.g. "pikachu", "bulbasaur", "25".
    """
    key = name.strip().lower()
    try:
        return _fetch_pokemon(key)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {"error": f"No encontré el Pokémon '{key}'."}
        return {"error": f"Error HTTP {exc.response.status_code} consultando '{key}'."}
    except (httpx.TimeoutException, httpx.NetworkError):
        return {"error": "Timeout o error de red al contactar la PokéAPI."}
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool
def get_type_matchups(type_name: str) -> dict:
    """Devuelve las relaciones de daño de un tipo Pokémon.

    Campos devueltos (todos son listas de strings):
      strong_against  — este tipo hace ×2 daño A estos tipos
      weak_against    — este tipo hace ×0.5 daño A estos tipos
      no_effect_to    — este tipo hace ×0 daño A estos tipos
      weak_to         — este tipo recibe ×2 daño DE estos tipos
      resists         — este tipo recibe ×0.5 daño DE estos tipos
      immune_to       — este tipo recibe ×0 daño DE estos tipos
    Devuelve {"error": "..."} si el tipo no existe o hay problemas de red.

    Args:
        type_name: Nombre del tipo en inglés, e.g. "fire", "water", "psychic".
    """
    key = type_name.strip().lower()
    try:
        return _fetch_type(key)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {"error": f"No encontré el tipo '{key}'."}
        return {"error": f"Error HTTP {exc.response.status_code} consultando '{key}'."}
    except (httpx.TimeoutException, httpx.NetworkError):
        return {"error": "Timeout o error de red al contactar la PokéAPI."}
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool
def get_evolution_chain(name: str) -> dict:
    """Devuelve la línea evolutiva completa de un Pokémon como lista ordenada.

    Realiza dos pedidos: primero /pokemon-species/{name} para obtener la URL
    del evolution-chain, luego /evolution-chain/{id} para recorrer el árbol.
    Para líneas ramificadas (e.g. Eevee) devuelve todas las ramas en orden DFS.
    Devuelve {"chain": ["base", "stage2", ...]} o {"error": "..."}.

    Args:
        name: Nombre del Pokémon, e.g. "charmander", "eevee", "ralts".
    """
    key = name.strip().lower()
    try:
        return {"chain": _fetch_evolution_chain(key)}
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {"error": f"No encontré la especie '{key}'."}
        return {"error": f"Error HTTP {exc.response.status_code} consultando '{key}'."}
    except (httpx.TimeoutException, httpx.NetworkError):
        return {"error": "Timeout o error de red al contactar la PokéAPI."}
    except Exception as exc:
        return {"error": str(exc)}


if __name__ == "__main__":
    print("MCP endpoint: http://127.0.0.1:8000/mcp")
    try:
        mcp.run(transport="streamable-http", host="127.0.0.1", port=8000)
    except KeyboardInterrupt:
        print("\nServer process interrupted by user. Shutting down.")