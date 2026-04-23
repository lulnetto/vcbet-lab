from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

ARQUIVO_LIGAS = Path(__file__).resolve().parent / "ligas.json"


def _normalizar_filtro_nomes(ligas_nomes: Iterable[str] | None) -> Set[str] | None:
    if ligas_nomes is None:
        return None
    nomes = {str(nome).strip() for nome in ligas_nomes if str(nome).strip()}
    return nomes or None


def carregar_ligas(
    apenas_ativas: bool = True,
    ligas_nomes: Iterable[str] | None = None,
) -> List[Dict[str, Any]]:
    with open(ARQUIVO_LIGAS, "r", encoding="utf-8") as arquivo:
        ligas = json.load(arquivo)

    if apenas_ativas:
        ligas = [liga for liga in ligas if liga.get("ativo", True)]

    filtro_nomes = _normalizar_filtro_nomes(ligas_nomes)
    if filtro_nomes is not None:
        ligas = [liga for liga in ligas if liga.get("nome") in filtro_nomes]

    nomes = [liga["nome"] for liga in ligas]
    duplicadas: Set[str] = {nome for nome in nomes if nomes.count(nome) > 1}
    if duplicadas:
        raise ValueError(f"Nomes de ligas duplicados em {ARQUIVO_LIGAS.name}: {sorted(duplicadas)}")

    return ligas


def carregar_ligas_betano(ligas_nomes: Iterable[str] | None = None) -> List[Dict[str, str]]:
    return [
        {"nome": liga["nome"], "path": liga["betano_path"]}
        for liga in carregar_ligas(ligas_nomes=ligas_nomes)
        if liga.get("betano_path")
    ]


def carregar_ligas_footystats(ligas_nomes: Iterable[str] | None = None) -> Dict[str, str]:
    return {
        liga["nome"]: liga["footystats_url"]
        for liga in carregar_ligas(ligas_nomes=ligas_nomes)
        if liga.get("footystats_url")
    }


def obter_nomes_ligas_ativas(ligas_nomes: Iterable[str] | None = None) -> Set[str]:
    return {liga["nome"] for liga in carregar_ligas(ligas_nomes=ligas_nomes)}


def obter_meta_liga(nome_liga: str) -> Dict[str, Any] | None:
    for liga in carregar_ligas(apenas_ativas=False):
        if liga.get("nome") == nome_liga:
            return liga
    return None


def liga_eh_caotica(nome_liga: str) -> bool:
    meta = obter_meta_liga(nome_liga)
    if not meta:
        return False
    return bool(meta.get("chaotic", False))


def obter_nomes_ligas_caoticas(apenas_ativas: bool = True) -> Set[str]:
    return {
        liga["nome"]
        for liga in carregar_ligas(apenas_ativas=apenas_ativas)
        if liga.get("chaotic", False)
    }
