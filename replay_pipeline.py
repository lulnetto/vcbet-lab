from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from strategy_config import CONFIGS_DIR, ConfigResolutionError, list_available_configs, resolve_config_file


ROOT = Path(__file__).resolve().parent
DEFAULT_REPLAY_DIR = ROOT / "data" / "replays"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_signature(df: pd.DataFrame) -> pd.Series:
    line = df.get("line", pd.Series([pd.NA] * len(df)))
    line_text = line.apply(lambda v: "" if pd.isna(v) else f"{float(v):.2f}")
    return (
        df.get("match_name", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.lower()
        + "|" + df.get("market_type", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.lower()
        + "|" + df.get("selection_raw", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.lower()
        + "|" + line_text.astype(str)
    )




def _normalize_family_signature(df: pd.DataFrame) -> pd.Series:
    return (
        df.get("match_name", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.lower()
        + "|" + df.get("market_type", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.lower()
        + "|" + df.get("side", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.lower()
        + "|" + df.get("target_team_role", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.lower()
        + "|" + df.get("target_team_name", pd.Series([""] * len(df))).fillna("").astype(str).str.strip().str.lower()
    )


def _asian_total_line_drift(reference_df: pd.DataFrame, candidate_df: pd.DataFrame) -> dict[str, Any]:
    ref = reference_df.loc[reference_df.get("market_type", pd.Series(dtype=object)).eq("asian_total")].copy()
    cand = candidate_df.loc[candidate_df.get("market_type", pd.Series(dtype=object)).eq("asian_total")].copy()
    if ref.empty or cand.empty:
        return {
            "shifted_line_matches_total": 0,
            "delta_counts": {},
            "examples": [],
        }

    ref["family_sig"] = _normalize_family_signature(ref)
    cand["family_sig"] = _normalize_family_signature(cand)
    ref["line_num"] = pd.to_numeric(ref.get("line"), errors="coerce")
    cand["line_num"] = pd.to_numeric(cand.get("line"), errors="coerce")
    delta_counts: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []

    for _, row in ref.iterrows():
        if pd.isna(row["line_num"]):
            continue
        family = cand.loc[cand["family_sig"] == row["family_sig"]].copy()
        if family.empty:
            continue
        exact = family.loc[(family["selection_raw"].astype(str).str.lower() == str(row.get("selection_raw", "")).lower()) & (family["line_num"] == row["line_num"])]
        if not exact.empty:
            continue
        family = family.dropna(subset=["line_num"])
        if family.empty:
            continue
        family["line_delta"] = (family["line_num"] - float(row["line_num"])).abs()
        best = family.sort_values(["line_delta", "confidence_score", "ev_percent"], ascending=[True, False, False]).iloc[0]
        delta = round(float(best["line_num"]) - float(row["line_num"]), 2)
        if abs(delta) > 1.0:
            continue
        delta_counts[f"{delta:+.2f}"] += 1
        if len(examples) < 20:
            examples.append({
                "match_name": row.get("match_name"),
                "reference_selection": row.get("selection_raw"),
                "reference_line": float(row["line_num"]),
                "candidate_selection": best.get("selection_raw"),
                "candidate_line": float(best["line_num"]),
                "delta": delta,
            })

    return {
        "shifted_line_matches_total": int(sum(delta_counts.values())),
        "delta_counts": dict(sorted(delta_counts.items())),
        "examples": examples,
    }

def _compare_pick_sets(reference_df: pd.DataFrame, candidate_df: pd.DataFrame) -> dict[str, Any]:
    if reference_df.empty and candidate_df.empty:
        return {
            "reference_total": 0,
            "candidate_total": 0,
            "overlap": 0,
            "precision": 0.0,
            "recall": 0.0,
            "jaccard": 0.0,
            "missing_from_candidate": [],
            "extra_in_candidate": [],
        }

    ref_sig = set(_normalize_signature(reference_df).tolist())
    cand_sig = set(_normalize_signature(candidate_df).tolist())
    overlap = ref_sig & cand_sig
    missing = sorted(ref_sig - cand_sig)
    extra = sorted(cand_sig - ref_sig)
    precision = len(overlap) / len(cand_sig) if cand_sig else 0.0
    recall = len(overlap) / len(ref_sig) if ref_sig else 0.0
    union = len(ref_sig | cand_sig)
    jaccard = len(overlap) / union if union else 0.0
    return {
        "reference_total": len(ref_sig),
        "candidate_total": len(cand_sig),
        "overlap": len(overlap),
        "precision": round(precision * 100, 2),
        "recall": round(recall * 100, 2),
        "jaccard": round(jaccard * 100, 2),
        "missing_from_candidate": missing[:50],
        "extra_in_candidate": extra[:50],
    }


def _resolve_source_run(source_run_dir: Path) -> dict[str, Path | str | None]:
    manifest = _load_json(source_run_dir / "run_manifest.json")

    def _from_manifest(*keys: str) -> Path | None:
        value = manifest
        for key in keys:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        if not value:
            return None
        path = Path(str(value))
        if not path.is_absolute():
            path = (ROOT / path).resolve()
        return path

    odds_path = source_run_dir / "odds_snapshot.csv"
    xg_path = source_run_dir / "xg_snapshot.csv"
    if not odds_path.exists():
        odds_path = _from_manifest("source_files", "odds_file") or _from_manifest("odds_snapshot_file") or odds_path
    if not xg_path.exists():
        xg_path = _from_manifest("source_files", "xg_file") or _from_manifest("xg_snapshot_file") or xg_path

    picks_path = source_run_dir / "picks_snapshot.csv"
    if not picks_path.exists():
        picks_path = _from_manifest("picks_file") or picks_path

    target_date = manifest.get("target_date") or source_run_dir.parent.name
    run_id = manifest.get("run_id") or source_run_dir.name
    if not Path(odds_path).exists():
        raise FileNotFoundError(f"odds_snapshot não encontrado para {source_run_dir}")
    if not Path(xg_path).exists():
        raise FileNotFoundError(f"xg_snapshot não encontrado para {source_run_dir}")

    return {
        "manifest": manifest,
        "odds_path": Path(odds_path),
        "xg_path": Path(xg_path),
        "picks_path": Path(picks_path),
        "target_date": str(target_date),
        "run_id": str(run_id),
    }


def _load_picks_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, sep=";")


def _run_single_replay(*, source_info: dict[str, Any], config_ref: str, output_root: Path, alias_file: str, python_bin: str) -> dict[str, Any]:
    possible_path = Path(config_ref)
    if possible_path.exists():
        config_path = resolve_config_file(config_file=possible_path, strict=True)
    else:
        config_path = resolve_config_file(config_name=config_ref, strict=True)
    config_name = Path(config_path).stem if config_path else config_ref
    replay_run_id = f"replay_{source_info['run_id']}_{config_name}"
    replay_target_date = str(source_info["target_date"])
    replay_dir = output_root / replay_target_date / replay_run_id
    replay_dir.mkdir(parents=True, exist_ok=True)
    ledger_file = replay_dir / "replay_ledger.csv"

    cmd = [
        python_bin,
        str(ROOT / "pipeline_ev.py"),
        "--run-id", replay_run_id,
        "--odds-file", str(source_info["odds_path"]),
        "--xg-file", str(source_info["xg_path"]),
        "--alias-file", alias_file,
        "--ledger-file", str(ledger_file),
        "--output-dir", str(output_root),
    ]
    if config_path:
        cmd += ["--config-file", str(config_path)]
    else:
        cmd += ["--config-name", config_ref]

    result = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    replay_picks = replay_dir / "picks_snapshot.csv"
    candidate_df = _load_picks_csv(replay_picks)
    reference_df = _load_picks_csv(Path(source_info["picks_path"]))
    comparison = _compare_pick_sets(reference_df, candidate_df)
    asian_total_line_drift = _asian_total_line_drift(reference_df, candidate_df)

    quality_report = _load_json(replay_dir / "quality_report.json")
    payload = {
        "config_name": config_name,
        "config_path": str(config_path) if config_path else config_ref,
        "run_id": replay_run_id,
        "return_code": result.returncode,
        "stdout_tail": result.stdout.splitlines()[-80:],
        "stderr_tail": result.stderr.splitlines()[-40:],
        "picks_total": int(len(candidate_df)),
        "picks_by_market": dict(Counter(candidate_df.get("market_type", pd.Series(dtype=object)).fillna("missing"))),
        "comparison": comparison,
        "asian_total_line_drift": asian_total_line_drift,
        "quality_report_file": str(replay_dir / "quality_report.json") if (replay_dir / "quality_report.json").exists() else None,
        "quality_processing": quality_report.get("processing", {}),
        "quality_outputs": quality_report.get("outputs", {}),
        "replay_dir": str(replay_dir),
    }
    (replay_dir / "replay_result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def replay_configs_for_run(*, source_run_dir: Path, config_refs: list[str], output_dir: Path, alias_file: str, python_bin: str) -> Path:
    source_info = _resolve_source_run(source_run_dir)
    comparison_dir = output_dir / str(source_info["target_date"]) / f"comparison_{source_info['run_id']}"
    comparison_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for config_ref in config_refs:
        results.append(
            _run_single_replay(
                source_info=source_info,
                config_ref=config_ref,
                output_root=output_dir,
                alias_file=alias_file,
                python_bin=python_bin,
            )
        )

    summary = {
        "source_run_dir": str(source_run_dir),
        "source_run_id": source_info["run_id"],
        "target_date": source_info["target_date"],
        "source_picks_file": str(source_info["picks_path"]),
        "results": results,
        "available_configs": list_available_configs(),
    }
    summary_path = comparison_dir / "comparison_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = []
    for item in results:
        comp = item["comparison"]
        rows.append({
            "config_name": item["config_name"],
            "picks_total": item["picks_total"],
            "return_code": item["return_code"],
            "overlap": comp["overlap"],
            "precision_percent": comp["precision"],
            "recall_percent": comp["recall"],
            "jaccard_percent": comp["jaccard"],
            "edge_below_min_discards": item["quality_processing"].get("discard_reason_counts", {}).get("pick_filter_edge_below_min", 0),
            "odd_out_of_range_discards": item["quality_processing"].get("discard_reason_counts", {}).get("pick_filter_odd_out_of_range", 0),
            "asian_total_shifted_lines": item.get("asian_total_line_drift", {}).get("shifted_line_matches_total", 0),
        })
    pd.DataFrame(rows).sort_values(["jaccard_percent", "overlap", "picks_total"], ascending=[False, False, False]).to_csv(
        comparison_dir / "comparison_summary.csv",
        index=False,
        sep=";",
        encoding="utf-8-sig",
    )
    return summary_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Reprocessa snapshots históricos com configs versionadas para reconstruir baseline.")
    parser.add_argument("--source-run-dir", required=True, help="Diretório da run histórica original")
    parser.add_argument("--config", action="append", required=True, dest="configs", help="Preset em ./configs ou caminho para JSON. Pode repetir.")
    parser.add_argument("--output-dir", default=str(DEFAULT_REPLAY_DIR), help="Diretório base para os replays")
    parser.add_argument("--alias-file", default="alias_times.json", help="Arquivo de aliases")
    parser.add_argument("--python-bin", default="python3", help="Binário Python")
    args = parser.parse_args()

    summary_path = replay_configs_for_run(
        source_run_dir=Path(args.source_run_dir).resolve(),
        config_refs=args.configs,
        output_dir=Path(args.output_dir).resolve(),
        alias_file=args.alias_file,
        python_bin=args.python_bin,
    )
    print(f"[OK] Replay concluído. Resumo salvo em: {summary_path}")


if __name__ == "__main__":
    try:
        main()
    except ConfigResolutionError as exc:
        raise SystemExit(f"[ERRO_CONFIG] {exc}")
