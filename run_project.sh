#!/usr/bin/env bash
set -euo pipefail

MODE="full"
RUN_ID=""
TARGET_DATE=""
ODDS_FILE=""
XG_FILE=""
LEDGER_FILE="data/history/bets_ledger.csv"
OUTPUT_DIR="data/runs"
DEBUG=0
DRY_RUN=0
JSON_FLAG=0
PYTHON_BIN="python3"
CONFIG_FILE=""
CONFIG_NAME=""
XG_SOURCE="fotmob"
TEMP_ROOT=""
ORIGINAL_OUTPUT_DIR="$OUTPUT_DIR"
ORIGINAL_LEDGER_FILE="$LEDGER_FILE"

cleanup() {
  if [[ -n "$TEMP_ROOT" && -d "$TEMP_ROOT" ]]; then
    rm -rf "$TEMP_ROOT"
  fi
}

usage() {
  cat <<USAGE
Uso:
  Modo completo (coleta odds, detecta ligas ativas, coleta xG filtrado e roda pipeline):
    ./run_project.sh --mode full --date 2026-04-22 [--run-id run_20260422_120000] [--json] [--debug] [--dry-run]

  Modo legado (usa CSVs antigos já existentes):
    ./run_project.sh --mode legacy --odds-file odds_multiplas_betano_2026-04-22.csv --xg-file base_xg_stats.csv [--date 2026-04-22] [--run-id run_20260422_120000] [--debug] [--dry-run]

Parâmetros:
  --mode         full | legacy
  --date         Data alvo no formato YYYY-MM-DD
  --run-id       Identificador da run. Se omitido, é gerado automaticamente.
  --odds-file    Caminho do CSV de odds (obrigatório no modo legacy)
  --xg-file      Caminho do CSV de xG (obrigatório no modo legacy)
  --ledger-file  Caminho do bets_ledger.csv
  --output-dir   Diretório base das runs
  --json         No modo full, também salva JSON de odds
  --debug        Roda sem persistir picks finais do pipeline
  --dry-run      Executa o fluxo completo em diretório temporário e apaga tudo no final
  --python-bin   Binário do Python (default: python3)
  --config-file  Arquivo JSON da estratégia
  --config-name  Preset da estratégia em ./configs
  --xg-source    fotmob | footystats (default: fotmob)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="$2"; shift 2 ;;
    --date)
      TARGET_DATE="$2"; shift 2 ;;
    --run-id)
      RUN_ID="$2"; shift 2 ;;
    --odds-file)
      ODDS_FILE="$2"; shift 2 ;;
    --xg-file)
      XG_FILE="$2"; shift 2 ;;
    --ledger-file)
      LEDGER_FILE="$2"; shift 2 ;;
    --output-dir)
      OUTPUT_DIR="$2"; shift 2 ;;
    --python-bin)
      PYTHON_BIN="$2"; shift 2 ;;
    --config-file)
      CONFIG_FILE="$2"; shift 2 ;;
    --config-name)
      CONFIG_NAME="$2"; shift 2 ;;
    --xg-source)
      XG_SOURCE="$2"; shift 2 ;;
    --json)
      JSON_FLAG=1; shift ;;
    --debug)
      DEBUG=1; shift ;;
    --dry-run)
      DRY_RUN=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Parâmetro desconhecido: $1" >&2
      usage
      exit 1 ;;
  esac
done

generate_run_id() {
  date +"run_%Y%m%d_%H%M%S"
}

extract_date_from_filename() {
  local input="$1"
  local extracted
  extracted=$(basename "$input" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' | head -n1 || true)
  echo "$extracted"
}

extract_active_leagues_from_odds() {
  local odds_snapshot="$1"
  "$PYTHON_BIN" - "$odds_snapshot" <<'PY'
import csv
import sys
from pathlib import Path

odds_file = Path(sys.argv[1])
if not odds_file.exists():
    sys.exit(0)

league_names = []
seen = set()
with odds_file.open("r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f, delimiter=';')
    for row in reader:
        league = (row.get("league") or row.get("Liga") or "").strip()
        if league and league not in seen:
            seen.add(league)
            league_names.append(league)

print(",".join(league_names))
PY
}

if [[ -z "$RUN_ID" ]]; then
  RUN_ID="$(generate_run_id)"
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  TEMP_ROOT="$(mktemp -d)"
  trap cleanup EXIT
  OUTPUT_DIR="$TEMP_ROOT/runs"
  LEDGER_FILE="$TEMP_ROOT/bets_ledger.csv"
  mkdir -p "$OUTPUT_DIR"
  echo "[DRY-RUN] Diretório temporário: $TEMP_ROOT"
  echo "[DRY-RUN] Nenhum artefato será mantido após o término."
fi

if [[ "$MODE" == "legacy" ]]; then
  if [[ -z "$ODDS_FILE" || -z "$XG_FILE" ]]; then
    echo "No modo legacy, --odds-file e --xg-file são obrigatórios." >&2
    exit 1
  fi
  if [[ ! -f "$ODDS_FILE" ]]; then
    echo "Arquivo de odds não encontrado: $ODDS_FILE" >&2
    exit 1
  fi
  if [[ ! -f "$XG_FILE" ]]; then
    echo "Arquivo de xG não encontrado: $XG_FILE" >&2
    exit 1
  fi

  if [[ -z "$TARGET_DATE" ]]; then
    TARGET_DATE="$(extract_date_from_filename "$ODDS_FILE")"
  fi
  if [[ -z "$TARGET_DATE" ]]; then
    TARGET_DATE="$(date +%F)"
  fi

  RUN_DIR="$OUTPUT_DIR/$TARGET_DATE/$RUN_ID"
  mkdir -p "$RUN_DIR"

  LEGACY_ODDS_SNAPSHOT="$RUN_DIR/odds_snapshot.csv"
  LEGACY_XG_SNAPSHOT="$RUN_DIR/xg_snapshot.csv"

  cp "$ODDS_FILE" "$LEGACY_ODDS_SNAPSHOT"
  cp "$XG_FILE" "$LEGACY_XG_SNAPSHOT"

  echo "[LEGACY] Run ID: $RUN_ID"
  echo "[LEGACY] Data:   $TARGET_DATE"
  echo "[LEGACY] Odds:   $LEGACY_ODDS_SNAPSHOT"
  echo "[LEGACY] xG:     $LEGACY_XG_SNAPSHOT"

  PIPELINE_ARGS=(
    --run-id "$RUN_ID"
    --odds-file "$LEGACY_ODDS_SNAPSHOT"
    --xg-file "$LEGACY_XG_SNAPSHOT"
    --ledger-file "$LEDGER_FILE"
    --output-dir "$OUTPUT_DIR"
  )

  if [[ -n "$CONFIG_FILE" ]]; then
    PIPELINE_ARGS+=(--config-file "$CONFIG_FILE")
  fi
  if [[ -n "$CONFIG_NAME" ]]; then
    PIPELINE_ARGS+=(--config-name "$CONFIG_NAME")
  fi

  if [[ "$DEBUG" -eq 1 ]]; then
    PIPELINE_ARGS+=(--debug)
  fi

  "$PYTHON_BIN" -m vcbet.core.pipeline_ev "${PIPELINE_ARGS[@]}"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DRY-RUN] Execução concluída sem persistir artefatos em $ORIGINAL_OUTPUT_DIR ou $ORIGINAL_LEDGER_FILE."
  fi
  exit 0
fi

if [[ "$MODE" != "full" ]]; then
  echo "Modo inválido: $MODE. Use full ou legacy." >&2
  exit 1
fi

if [[ -z "$TARGET_DATE" ]]; then
  TARGET_DATE="$(date +%F)"
fi

RUN_DIR="$OUTPUT_DIR/$TARGET_DATE/$RUN_ID"
mkdir -p "$RUN_DIR"

ODDS_SNAPSHOT="$RUN_DIR/odds_snapshot.csv"
XG_SNAPSHOT="$RUN_DIR/xg_snapshot.csv"

echo "[FULL] Run ID: $RUN_ID"
echo "[FULL] Data:   $TARGET_DATE"
echo "[FULL] Pasta:  $RUN_DIR"

ODDS_ARGS=(--run-id "$RUN_ID" --d "$TARGET_DATE" --output-dir "$OUTPUT_DIR")
if [[ "$JSON_FLAG" -eq 1 ]]; then
  ODDS_ARGS+=(--json)
fi
if [[ "$DEBUG" -eq 1 ]]; then
  ODDS_ARGS+=(--debug)
fi

"$PYTHON_BIN" -m vcbet.collectors.odds_collector "${ODDS_ARGS[@]}"

if [[ ! -f "$ODDS_SNAPSHOT" ]]; then
  echo "[ERRO] odds_snapshot.csv não foi gerado. Abortando a etapa de xG e pipeline." >&2
  exit 1
fi

ACTIVE_LEAGUES="$(extract_active_leagues_from_odds "$ODDS_SNAPSHOT")"
if [[ -z "$ACTIVE_LEAGUES" ]]; then
  echo "[INFO] Nenhuma liga com jogos encontrada nas odds do dia. Encerrando sem coletar xG/pipeline."
  exit 0
fi

echo "[FULL] Ligas detectadas nas odds: $ACTIVE_LEAGUES"

SNAPSHOT_DATE="$(date +%F)"
if [[ "$DRY_RUN" -eq 1 ]]; then
  DAILY_XG_DIR="$TEMP_ROOT/xg/$SNAPSHOT_DATE"
else
  DAILY_XG_DIR="data/xg/$SNAPSHOT_DATE"
fi
DAILY_XG_SNAPSHOT="$DAILY_XG_DIR/xg_snapshot.csv"

if [[ -f "$DAILY_XG_SNAPSHOT" ]]; then
  echo "[FULL] Reutilizando snapshot xG diário: $DAILY_XG_SNAPSHOT"
  cp "$DAILY_XG_SNAPSHOT" "$XG_SNAPSHOT"
else
  echo "[FULL] Coletando snapshot xG diário (fonte: $XG_SOURCE) para $SNAPSHOT_DATE..."
  if [[ "$DRY_RUN" -eq 1 ]]; then
    "$PYTHON_BIN" -m vcbet.collectors.xg_daily_store \
      --date "$TARGET_DATE" \
      --source "$XG_SOURCE" \
      --snapshot-date "$SNAPSHOT_DATE" \
      --output-dir "$TEMP_ROOT/xg"
  else
    "$PYTHON_BIN" -m vcbet.collectors.xg_daily_store \
      --date "$TARGET_DATE" \
      --source "$XG_SOURCE" \
      --snapshot-date "$SNAPSHOT_DATE"
  fi
  if [[ -f "$DAILY_XG_SNAPSHOT" ]]; then
    cp "$DAILY_XG_SNAPSHOT" "$XG_SNAPSHOT"
  fi
fi

PIPELINE_ARGS=(
  --run-id "$RUN_ID"
  --odds-file "$ODDS_SNAPSHOT"
  --xg-file "$XG_SNAPSHOT"
  --ledger-file "$LEDGER_FILE"
  --output-dir "$OUTPUT_DIR"
)

if [[ "$DEBUG" -eq 1 ]]; then
  PIPELINE_ARGS+=(--debug)
fi
if [[ "$DRY_RUN" -eq 1 ]]; then
  PIPELINE_ARGS+=(--dry-run)
fi

if [[ -n "$CONFIG_FILE" ]]; then
  PIPELINE_ARGS+=(--config-file "$CONFIG_FILE")
fi
if [[ -n "$CONFIG_NAME" ]]; then
  PIPELINE_ARGS+=(--config-name "$CONFIG_NAME")
fi

if [[ ! -f "$XG_SNAPSHOT" ]]; then
  echo "[ERRO] xg_snapshot.csv não foi gerado. Abortando o pipeline." >&2
  exit 1
fi

"$PYTHON_BIN" -m vcbet.core.pipeline_ev "${PIPELINE_ARGS[@]}"

echo "[OK] Execução concluída."
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[DRY-RUN] Execução concluída sem persistir artefatos em $ORIGINAL_OUTPUT_DIR ou $ORIGINAL_LEDGER_FILE."
fi
