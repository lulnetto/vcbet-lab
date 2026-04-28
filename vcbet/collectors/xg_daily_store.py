import argparse
import shutil
from pathlib import Path

from vcbet.collectors.fotmob_xg_collector import construir_banco_dados as fotmob_build
from vcbet.collectors.footystats_xg_collector import construir_banco_dados as footystats_build
from vcbet.core.run_utils import ensure_run_dir


def get_or_build_daily_xg(
    target_date: str,
    source: str,
    leagues: str | None = None,
    output_dir: str = "data/xg",
):
    daily_dir = Path(output_dir) / target_date
    daily_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = daily_dir / "xg_snapshot.csv"

    if snapshot_path.exists():
        print(f"[xG CACHE] Reutilizando snapshot diário: {snapshot_path}")
        return str(snapshot_path)

    run_id = "daily"
    run_dir = ensure_run_dir(run_id=run_id, target_date=target_date, base_output_dir=output_dir)
    ligas_alvo = [l.strip() for l in leagues.split(",") if l.strip()] if leagues else None

    if source == "fotmob":
        fotmob_build(
            run_id=run_id,
            target_date=target_date,
            output_dir=output_dir,
            ligas_alvo=ligas_alvo,
        )
    else:
        footystats_build(
            run_id=run_id,
            target_date=target_date,
            output_dir=output_dir,
            ligas_alvo=ligas_alvo,
        )

    src = run_dir / "xg_snapshot.csv"
    if not src.exists():
        raise FileNotFoundError(f"xG snapshot não gerado em {src}")

    shutil.copy(str(src), str(snapshot_path))
    print(f"[xG CACHE] Snapshot diário criado: {snapshot_path}")
    return str(snapshot_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cache/snapshot diário de xG")
    parser.add_argument("--date", required=True, help="Data alvo YYYY-MM-DD")
    parser.add_argument("--source", default="fotmob", choices=["fotmob", "footystats"])
    parser.add_argument("--leagues", default="", help="Ligas separadas por vírgula")
    parser.add_argument("--output-dir", default="data/xg")
    args = parser.parse_args()
    get_or_build_daily_xg(
        target_date=args.date,
        source=args.source,
        leagues=args.leagues or None,
        output_dir=args.output_dir,
    )
