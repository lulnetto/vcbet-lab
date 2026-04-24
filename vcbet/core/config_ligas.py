from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set

from vcbet.paths import LIGAS_FILE

ARQUIVO_LIGAS = LIGAS_FILE


def carregar_ligas(apenas_ativas: bool = True) -> List[Dict[str, Any]]:
    with open(ARQUIVO_LIGAS, "r", encoding="utf-8") as arquivo:
        ligas = json.load(arquivo)

    if apenas_ativas:
        ligas = [liga for liga in ligas if liga.get("ativo", True)]

    nomes = [liga["nome"] for liga in ligas]
    duplicadas: Set[str] = {nome for nome in nomes if nomes.count(nome) > 1}
    if duplicadas:
        raise ValueError(f"Nomes de ligas duplicados em {ARQUIVO_LIGAS.name}: {sorted(duplicadas)}")

    return ligas


def _filtrar_por_nomes(
    ligas: List[Dict[str, Any]],
    ligas_nomes: List[str] | Set[str] | None = None,
) -> List[Dict[str, Any]]:
    if not ligas_nomes:
        return ligas
    alvo = {nome.strip() for nome in ligas_nomes if str(nome).strip()}
    return [liga for liga in ligas if liga["nome"] in alvo]


def carregar_ligas_betano(ligas_nomes: List[str] | Set[str] | None = None) -> List[Dict[str, str]]:
    ligas = _filtrar_por_nomes(carregar_ligas(), ligas_nomes)
    return [
        {"nome": liga["nome"], "path": liga["betano_path"]}
        for liga in ligas
        if liga.get("betano_path")
    ]


def carregar_ligas_footystats(ligas_nomes: List[str] | Set[str] | None = None) -> Dict[str, str]:
    ligas = _filtrar_por_nomes(carregar_ligas(), ligas_nomes)
    return {
        liga["nome"]: liga["footystats_url"]
        for liga in ligas
        if liga.get("footystats_url")
    }


def obter_nomes_ligas_ativas() -> Set[str]:
    return {liga["nome"] for liga in carregar_ligas()}


def obter_meta_liga(nome_liga: str) -> Dict[str, Any] | None:
    for liga in carregar_ligas():
        if liga["nome"] == nome_liga:
            return liga
    return None


def liga_eh_caotica(nome_liga: str) -> bool:
    meta = obter_meta_liga(nome_liga)
    return bool(meta and meta.get("chaotic", False))


def obter_nomes_ligas_caoticas() -> Set[str]:
    return {
        liga["nome"]
        for liga in carregar_ligas()
        if liga.get("chaotic", False)
    }


def obter_result_source_url(nome_liga: str, source: str = "flashscore") -> str | None:
    meta = obter_meta_liga(nome_liga)
    if not meta:
        return None
    field = {
        "flashscore": "flashscore_results_url",
        "sofascore": "sofascore_tournament_url",
    }.get(source, f"{source}_results_url")
    return meta.get(field)


def obter_sofascore_unique_tournament_id(nome_liga: str) -> int | None:
    meta = obter_meta_liga(nome_liga)
    if not meta:
        return None
    value = meta.get("sofascore_unique_tournament_id")
    if value in (None, "", 0):
        return None
    return int(value)


def carregar_ligas_resultados(
    source: str = "flashscore",
    ligas_nomes: List[str] | Set[str] | None = None,
) -> Dict[str, str]:
    ligas = _filtrar_por_nomes(carregar_ligas(), ligas_nomes)
    field = {
        "flashscore": "flashscore_results_url",
        "sofascore": "sofascore_tournament_url",
    }.get(source, f"{source}_results_url")
    return {
        liga["nome"]: liga[field]
        for liga in ligas
        if liga.get(field)
    }


def carregar_ligas_sofascore_ids(
    ligas_nomes: List[str] | Set[str] | None = None,
) -> Dict[str, int]:
    ligas = _filtrar_por_nomes(carregar_ligas(), ligas_nomes)
    result: Dict[str, int] = {}
    for liga in ligas:
        value = liga.get("sofascore_unique_tournament_id")
        if value not in (None, "", 0):
            result[liga["nome"]] = int(value)
    return result
