import argparse
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

import pandas as pd
import requests
from bs4 import BeautifulSoup
import re

from vcbet.collectors.footystats_fetcher import FootyStatsBrowserFetcher
from vcbet.core.config_ligas import carregar_ligas_footystats
from vcbet.core.run_utils import build_manifest, ensure_run_dir, generate_run_id, save_manifest, update_manifest
from vcbet.core.temporal_contract import TEMPORAL_CONTRACT_VERSION, file_md5, snapshot_time_from_dataframe



def parse_leagues_arg(raw_value: str | None) -> List[str] | None:
    if not raw_value:
        return None
    leagues = [item.strip() for item in raw_value.split(",") if item.strip()]
    return leagues or None



def _fetch_html_requests(url: str, timeout: int = 20) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8",
    }
    resposta = requests.get(url, headers=headers, timeout=timeout)
    resposta.raise_for_status()
    return resposta.text


def extrair_dados_completos(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "html.parser")

    tabela = soup.select_one("table.full-league-table")
    if not tabela:
        raise ValueError("Tabela principal 'full-league-table' não encontrada no HTML.")

    headers_th = tabela.select("thead th")
    nomes_headers = [th.get_text(" ", strip=True).upper() for th in headers_th]

    try:
        idx_xg = nomes_headers.index("XG")
        idx_xga = nomes_headers.index("XGA")
    except ValueError as e:
        raise ValueError(
            f"Não foi possível localizar colunas XG/XGA. Headers encontrados: {nomes_headers}"
        ) from e

    dados_globais = {}

    for linha in tabela.select("tbody > tr"):
        colunas = linha.find_all("td", recursive=False)
        if len(colunas) <= max(idx_xg, idx_xga):
            continue

        link_time = linha.select_one("td.team a")
        if not link_time:
            continue

        textos_diretos = link_time.find_all(string=True, recursive=False)
        time_limpo = "".join(textos_diretos).strip()
        if not time_limpo:
            time_limpo = link_time.get_text(" ", strip=True)

        try:
            xg = float(colunas[idx_xg].get_text(strip=True).replace(",", "."))
            xga = float(colunas[idx_xga].get_text(strip=True).replace(",", "."))
        except ValueError:
            continue

        dados_globais[time_limpo] = {
            "team_name": time_limpo,
            "xg": xg,
            "xga": xga,
            "xg_home": xg,
            "xg_away": xg,
            "xga_home": xga,
            "xga_away": xga,
        }

    def parse_ui_list(header_text):
        heading = soup.find(
            lambda tag: tag.name in {"h1", "h2", "h3", "h4"}
            and header_text.lower() in tag.get_text(" ", strip=True).lower()
        )
        if not heading:
            return {}

        ul = heading.find_next("ul", class_="ui-list")
        if not ul:
            return {}

        valores = {}
        for li in ul.select("li.list-row"):
            link = li.select_one("div.main a") or li.find("a")
            bubble = li.select_one("div.small-bubble")

            if not link or not bubble:
                continue

            nome = link.get_text(" ", strip=True)
            texto_bubble = bubble.get_text(" ", strip=True).replace(",", ".")
            m = re.search(r"(\d+(?:\.\d+)?)", texto_bubble)
            if m:
                valores[nome] = float(m.group(1))

        return valores

    xg_home_dict = parse_ui_list("xG Home")
    xg_away_dict = parse_ui_list("xG Away")
    xga_home_dict = parse_ui_list("xGA Home")
    xga_away_dict = parse_ui_list("xGA Away")

    if not xg_home_dict or not xg_away_dict:
        print("      [ALERTA] Listas de xG Home/Away vazias. Usando xG Global como fallback.")

    if not xga_home_dict or not xga_away_dict:
        print("      [ALERTA] Listas de xGA Home/Away vazias. Usando xGA Global como fallback.")

    lista_final = []
    for team_name, stats in dados_globais.items():
        stats["xg_home"] = xg_home_dict.get(team_name, stats["xg"])
        stats["xg_away"] = xg_away_dict.get(team_name, stats["xg"])
        stats["xga_home"] = xga_home_dict.get(team_name, stats["xga"])
        stats["xga_away"] = xga_away_dict.get(team_name, stats["xga"])
        lista_final.append(stats)

    return pd.DataFrame(lista_final)


def _slugify_league(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _fetch_html(
    url: str,
    *,
    fetch_mode: str = "browser",
    fetcher: FootyStatsBrowserFetcher | None = None,
) -> str:
    if fetch_mode in ("browser", "browser_only"):
        if fetcher is None:
            raise RuntimeError(
                "footystats_browser_unavailable: browser fetch mode requires FootyStatsBrowserFetcher."
            )
        result = fetcher.fetch_html(url)
        if not result.ok:
            raise RuntimeError(
                f"footystats_browser_fetch_failed: {result.error}"
            )
        if result.html is None:
            raise RuntimeError("footystats_browser_fetch_failed: empty html response")
        return result.html

    if fetch_mode == "browser_first":
        if fetcher is not None:
            result = fetcher.fetch_html(url)
            if result.ok and result.html:
                return result.html
            print(f"      [ALERTA] Browser fetch falhou para {url}; tentando requests fallback.")
        else:
            print("      [ALERTA] Browser fetcher não disponível; tentando requests fallback.")
        return _fetch_html_requests(url)

    if fetch_mode == "requests":
        return _fetch_html_requests(url)

    raise ValueError(f"fetch_mode desconhecido: {fetch_mode}")


def construir_banco_dados(
    run_id: str,
    target_date: str,
    output_dir: str,
    ligas_alvo: Iterable[str] | None = None,
    modo_debug: bool = False,
    fetch_mode: str = "browser",
    browser_headed: bool = False,
    browser_profile_dir: str | None = None,
):
    print(f"================ [ ATUALIZANDO BANCO DE DADOS DE xG | RUN_ID: {run_id} ] ================")
    run_dir = ensure_run_dir(run_id=run_id, target_date=target_date, base_output_dir=output_dir)
    debug_dir = run_dir / "_debug"

    manifest = build_manifest(
        run_id=run_id,
        target_date=target_date,
        run_dir=run_dir,
        odds_snapshot_file=str(run_dir / "odds_snapshot.csv"),
        xg_snapshot_file=str(run_dir / "xg_snapshot.csv"),
        status="xg_initialized",
    )
    save_manifest(run_dir, manifest)

    mapa_footystats = carregar_ligas_footystats(ligas_nomes=ligas_alvo)
    if ligas_alvo:
        print(f" -> Filtro de ligas ativo: {', '.join(mapa_footystats.keys()) if mapa_footystats else '(nenhuma liga válida)'}")

    if not mapa_footystats:
        update_manifest(
            run_dir,
            status="xg_empty",
            xg_rows=0,
            xg_target_leagues=list(ligas_alvo or []),
        )
        print("\n[FALHA] Nenhuma liga válida com footystats_url foi selecionada para a coleta de xG.")
        return

    lista_dfs = []
    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    league_failures: list[dict] = []

    browser_fetcher: FootyStatsBrowserFetcher | None = None
    try:
        if fetch_mode in ("browser", "browser_only", "browser_first"):
            browser_fetcher = FootyStatsBrowserFetcher(
                debug=modo_debug,
                headless=not browser_headed,
                profile_dir=browser_profile_dir,
            )
            browser_fetcher.__enter__()

        for liga, url_base in mapa_footystats.items():
            print(f" -> Baixando: {liga}...")
            league_slug = _slugify_league(liga)
            try:
                if fetch_mode in ("browser", "browser_only", "browser_first") and browser_fetcher is not None:
                    result = browser_fetcher.fetch_html(f"{url_base}/xg")
                    if not result.ok:
                        print(f"    [ERRO] Fetch falhou para {liga}: {result.error} (status={result.status_code})")
                        league_failures.append({"league": liga, "error": result.error, "status_code": result.status_code})
                        if browser_fetcher is not None:
                            browser_fetcher.save_debug_artifact(
                                url=f"{url_base}/xg",
                                debug_dir=debug_dir,
                                slug=league_slug,
                            )
                        continue
                    html = result.html
                else:
                    html = _fetch_html(f"{url_base}/xg", fetch_mode=fetch_mode, fetcher=browser_fetcher)

                df_completo = extrair_dados_completos(html)
                if df_completo is not None and not df_completo.empty:
                    df_completo["run_id"] = run_id
                    df_completo["collected_at"] = collected_at
                    df_completo["source"] = "footystats"
                    df_completo["league"] = liga
                    df_completo["fetch_method"] = "browser" if fetch_mode in ("browser", "browser_only", "browser_first") and browser_fetcher is not None else fetch_mode
                    lista_dfs.append(df_completo)
                    print(f"    [OK] {len(df_completo)} equipas extraídas.")
                else:
                    print(f"    [ERRO] DataFrame vazio retornado para {liga}.")
            except Exception:
                print(f"    [ERRO FATAL] Falha processando {liga}:")
                traceback.print_exc()
                league_failures.append({"league": liga, "error": "exception", "status_code": None})

            time.sleep(2)
    finally:
        if browser_fetcher is not None:
            browser_fetcher.__exit__(None, None, None)

    if lista_dfs:
        df_final = pd.concat(lista_dfs, ignore_index=True)
        ordered_columns = [
            "run_id",
            "collected_at",
            "source",
            "league",
            "team_name",
            "xg",
            "xga",
            "xg_home",
            "xg_away",
            "xga_home",
            "xga_away",
        ]
        # Preserve fetch_method if present (add after ordered columns)
        if "fetch_method" in df_final.columns:
            ordered_columns.append("fetch_method")
        df_final = df_final[ordered_columns + [c for c in df_final.columns if c not in ordered_columns]]
        xg_snapshot_path = run_dir / "xg_snapshot.csv"

        if not modo_debug:
            df_final.to_csv(xg_snapshot_path, index=False, sep=";", encoding="utf-8-sig")
            print(f"\n[SUCESSO] Snapshot gerado com {len(df_final)} equipas: '{xg_snapshot_path}'")
        else:
            print(f"\n[!] MODO DEBUG: Extração concluída ({len(df_final)} equipas). Arquivo CSV NÃO foi gerado.")
            print("\n--- AMOSTRA DOS DADOS EXTRAÍDOS ---")
            print(df_final.head(15).to_string(index=False))

        update_manifest(
            run_dir,
            status="xg_completed",
            xg_rows=len(df_final),
            xg_snapshot_file=str(xg_snapshot_path),
            xg_snapshot_hash=file_md5(xg_snapshot_path) if xg_snapshot_path.exists() else None,
            xg_asof=snapshot_time_from_dataframe(df_final),
            temporal_contract_version=TEMPORAL_CONTRACT_VERSION,
            xg_target_leagues=list(mapa_footystats.keys()),
            xg_league_failures=league_failures if league_failures else None,
        )
    else:
        update_manifest(
            run_dir,
            status="xg_empty",
            xg_rows=0,
            xg_target_leagues=list(mapa_footystats.keys()),
            xg_league_failures=league_failures if league_failures else None,
        )
        print("\n[FALHA] Nenhum dado foi extraído.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Coletor de snapshot xG por run")
    parser.add_argument("--debug", action="store_true", help="Executa normalmente, mas não salva arquivos no final")
    parser.add_argument("--run-id", type=str, help="Identificador único da execução")
    parser.add_argument("--output-dir", type=str, default="data/runs", help="Diretório base para salvar as runs")
    parser.add_argument("--data", type=str, help="Data da run no formato YYYY-MM-DD")
    parser.add_argument("--leagues", type=str, help="Lista de ligas separadas por vírgula para limitar a coleta de xG")
    parser.add_argument(
        "--fetch-mode",
        type=str,
        default="browser",
        choices=["browser", "browser_only", "browser_first", "requests"],
        help="Modo de fetch: browser (padrão), browser_only, browser_first, requests",
    )
    parser.add_argument("--browser-headed", action="store_true", help="Abre o Chromium visível para depuração")
    parser.add_argument("--browser-profile-dir", type=str, help="Diretório de perfil persistente do browser para reuso de sessão")
    args = parser.parse_args()

    target_date = args.data or datetime.today().strftime("%Y-%m-%d")
    run_id = args.run_id or generate_run_id()
    ligas_alvo = parse_leagues_arg(args.leagues)
    construir_banco_dados(
        run_id=run_id,
        target_date=target_date,
        output_dir=args.output_dir,
        ligas_alvo=ligas_alvo,
        modo_debug=args.debug,
        fetch_mode=args.fetch_mode,
        browser_headed=args.browser_headed,
        browser_profile_dir=args.browser_profile_dir,
    )
