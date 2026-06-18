"""
mcp_server.py
MCP server (FastMCP 3) over the public PokéAPI.
Runs as a remote HTTP server compatible with Anthropic Managed Agents.

Start   : python mcp_server.py
Endpoint: http://127.0.0.1:8000/mcp
"""

from __future__ import annotations

import functools

import httpx
from fastmcp import FastMCP

_BASE = "https://pokeapi.co/api/v2"

_client = httpx.Client(timeout=10.0)


@functools.lru_cache(maxsize=512)
def _get_json(url: str) -> dict:
    """GET a URL and return parsed JSON.

    Cached by URL: PokéAPI is static, caching is correct and responsible.
    Raises httpx.HTTPStatusError / httpx.TimeoutException / httpx.NetworkError;
    tools catch these and return an error dict — never re-raise from here.
    Important: do not mutate the returned dict (it is the cached instance).
    """
    resp = _client.get(url)
    resp.raise_for_status()
    return resp.json()


def _fetch_pokemon(name: str) -> dict:
    """Extract the relevant fields from /pokemon/{name}."""
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
    """Extract the six damage relations from /type/{type_name}."""
    data = _get_json(f"{_BASE}/type/{type_name}")
    dr = data["damage_relations"]
    return {
        "name":           data["name"],
        "strong_against": [t["name"] for t in dr["double_damage_to"]],
        "weak_against":   [t["name"] for t in dr["half_damage_to"]],
        "no_effect_to":   [t["name"] for t in dr["no_damage_to"]],
        "weak_to":        [t["name"] for t in dr["double_damage_from"]],
        "resists":        [t["name"] for t in dr["half_damage_from"]],
        "immune_to":      [t["name"] for t in dr["no_damage_from"]],
    }


def _walk_chain(node: dict) -> list[str]:
    """Recursively walk an evolution-chain node and return species names in order."""
    names = [node["species"]["name"]]
    for next_node in node["evolves_to"]:
        names.extend(_walk_chain(next_node))
    return names


def _fetch_evolution_chain(name: str) -> list[str]:
    """Return the evolution line for name as an ordered list of species names.

    Two requests to PokéAPI:
      1. /pokemon-species/{name}  →  retrieve the evolution-chain URL
      2. /evolution-chain/{id}    →  walk the tree recursively
    """
    species = _get_json(f"{_BASE}/pokemon-species/{name}")
    chain_url = species["evolution_chain"]["url"]
    chain_data = _get_json(chain_url)
    return _walk_chain(chain_data["chain"])


mcp = FastMCP("PokeAPI MCP")


@mcp.tool
def get_pokemon(name: str) -> dict:
    """Fetch basic data for a Pokémon by name or ID.

    Returns id, name, types (list of strings), height (decimetres),
    weight (hectograms), base_stats (dict stat→value), and abilities (list).
    Returns {"error": "..."} if the Pokémon does not exist or a network error occurs.

    Args:
        name: Pokémon name or number, e.g. "pikachu", "bulbasaur", "25".
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
    """Return the damage relations for a Pokémon type.

    Returned fields (all are lists of strings):
      strong_against  — este tipo hace ×2 daño A estos tipos
      weak_against    — este tipo hace ×0.5 daño A estos tipos
      no_effect_to    — este tipo hace ×0 daño A estos tipos
      weak_to         — este tipo recibe ×2 daño DE estos tipos
      resists         — este tipo recibe ×0.5 daño DE estos tipos
      immune_to       — este tipo recibe ×0 daño DE estos tipos
    Returns {"error": "..."} if the type does not exist or a network error occurs.

    Args:
        type_name: Type name in English, e.g. "fire", "water", "psychic".
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
    """Return the full evolution line of a Pokémon as an ordered list.

    Makes two requests: first /pokemon-species/{name} to get the evolution-chain
    URL, then /evolution-chain/{id} to walk the tree.
    For branching lines (e.g. Eevee) returns all branches in DFS order.
    Returns {"chain": ["base", "stage2", ...]} or {"error": "..."}.

    Args:
        name: Pokémon name, e.g. "charmander", "eevee", "ralts".
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
