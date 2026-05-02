from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vcbet.paths import CONFIGS_DIR


class ConfigResolutionError(FileNotFoundError):
    pass


DEFAULT_CONFIG_PAYLOAD: dict[str, Any] = {
    "metadata": {
        "name": "champion_strict",
        "label": "Champion Strict",
        "description": "Configuração atual mais restritiva, voltada a qualidade e controle de risco.",
    },
    "pricing_variant": "xg_only",
    "xg_residual_adjustment": {
        "enabled": False,
    },
    "markets": {
        "total_goals": {
            "odd_min": 1.65,
            "standard_max": 2.60,
            "extended_max": 3.20,
            "edge_min": 0.06,
            "edge_strong": 0.10,
            "edge_premium_extended": 0.12,
            "is_primary_market": True,
        },
        "team_total": {
            "odd_min": 1.70,
            "standard_max": 2.60,
            "extended_max": 3.00,
            "edge_min": 0.07,
            "edge_strong": 0.10,
            "edge_premium_extended": 0.12,
            "is_primary_market": False,
        },
        "btts": {
            "odd_min": 1.70,
            "standard_max": 2.40,
            "extended_max": 2.80,
            "edge_min": 0.07,
            "edge_strong": 0.10,
            "edge_premium_extended": 0.12,
            "is_primary_market": False,
        },
        "asian_total": {
            "odd_min": 1.70,
            "standard_max": 2.60,
            "extended_max": 3.00,
            "edge_min": 0.06,
            "edge_strong": 0.10,
            "edge_premium_extended": 0.12,
            "is_primary_market": True,
        },
        "asian_handicap": {
            "odd_min": 1.70,
            "standard_max": 2.60,
            "extended_max": 3.00,
            "edge_min": 0.07,
            "edge_strong": 0.10,
            "edge_premium_extended": 0.12,
            "is_primary_market": True,
        },
        "draw_no_bet": {
            "odd_min": 1.70,
            "standard_max": 2.60,
            "extended_max": 3.00,
            "edge_min": 0.07,
            "edge_strong": 0.10,
            "edge_premium_extended": 0.12,
            "is_primary_market": False,
        },
    },
    "market_priority": {
        "total_goals": 1,
        "asian_total": 2,
        "asian_handicap": 3,
        "btts": 4,
        "team_total": 5,
        "draw_no_bet": 6,
    },
    "critical_flags": ["MATCH_DUVIDOSO", "DADO_INCOMPLETO_LIGA"],
    "confidence_caps": {
        "MATCH_FUZZY": 4,
        "ODD_ALTA_VARIANCIA": 4,
        "MERCADO_TIME": 4,
        "LIGA_VOLATIL": 4,
        "DRAW_SENSITIVE_LINE": 4,
        "CORRELACAO_JOGO": 3,
        "LINHA_EXTREMA": 3,
        "POISSON_MARGIN_RISK": 3,
    },
    "confidence_penalties": {
        "MATCH_FUZZY": 1,
        "FALLBACK_XG_GLOBAL": 1,
        "MERCADO_TIME": 1,
        "LIGA_VOLATIL": 1,
        "LINHA_EXTREMA": 2,
        "DRAW_SENSITIVE_LINE": 1,
        "LOW_SCORE_MATCH": 1,
        "HIGH_TOTAL_MATCH": 1,
        "POISSON_MARGIN_RISK": 2,
        "HEAVY_FAVORITE_LINE": 1,
        "CORRELACAO_JOGO": 2,
        "MATCH_DUVIDOSO": 3,
        "DADO_INCOMPLETO_LIGA": 3,
        "ODD_ALTA_VARIANCIA": 2,
    },
    "data_quality": {
        "max_snapshot_age_hours": 36,
        "max_invalid_snapshot_row_rate": 0.25,
        "require_snapshot_health_ok": True,
    },
    "rules": {
        "max_ev_percent": 20.0,
        "very_strong_edge": 0.14,
        "bonuses": {
            "primary_market": 1,
            "complete_data": 1,
            "reliable_match": 1,
            "stable_league": 1,
            "clean_setup": 1,
        },
        "confidence": {
            "min_to_keep": 3,
            "full_unit_min": 5,
            "full_unit_requires_no_flags": True,
            "full_unit_requires_not_extended": True,
        },
        "extended_range": {
            "enabled": True,
            "min_confidence": 5,
            "require_no_flags": True,
            "require_no_critical_flags": True,
        },
        "stakes": {
            "full_unit": 1.0,
            "half_unit": 0.5,
            "zero_unit": 0.0,
        },
        "safety_gates": {
            "enabled": True,
            "block_flags": ["MATCH_FUZZY", "MATCH_DUVIDOSO", "MATCH_REGISTRY_PENDING", "MATCH_UNRESOLVED", "DADO_INCOMPLETO_LIGA"],
        },
        "portfolio": {
            "max_picks_per_match": 2,
            "max_picks_per_league": None,
            "max_stake_per_league": None,
            "max_picks_per_market_family": None,
            "max_stake_per_market_family": None,
            "near_duplicate_line_tolerance": 0.25,
            "contradictory_line_tolerance": 0.25,
            "medium_correlation_policy": "downgrade",
            "correlation_selection": {
                "enabled": True,
                "max_picks_per_high_correlation_cluster": 1,
                "ev_gap_override_pp": 2.0,
                "ev_gap_override_by_relation": {
                    "DNB_EQUALS_AH_0": 0.0,
                    "DNB_AH_PLUS_0_25": 4.0,
                    "DNB_AH_PLUS_0_5": 6.0,
                    "DNB_AH_MINUS_0_25": 2.0,
                    "AH_NEAR_DUPLICATE_LINE": 2.0,
                    "BTTS_YES_TEAM_TOTAL_OVER_0_5": 5.0,
                    "TOTAL_EQUALS_ASIAN_TOTAL": 0.0,
                },
                "total_line_ev_gap_override_by_distance": {
                    "0.25": 3.0,
                    "0.5": 5.0,
                    "0.75": 6.0,
                    "1.0": 7.0,
                },
                "total_line_default_ev_gap_override_pp": 5.0,
                "score_weights": {
                    "ev_percent": 1.0,
                    "confidence_score": 0.75,
                    "entry_quality_score": 0.15,
                    "market_priority": 0.75,
                    "selection_safety": 0.75,
                    "odds_quality": 0.25,
                    "risk_penalty": 1.0,
                },
                "market_priority": {
                    "draw_no_bet": 5,
                    "asian_handicap": 5,
                    "asian_total": 4,
                    "total_goals": 4,
                    "team_total": 3,
                    "btts": 3,
                },
            },
            "asian_total_line_ladder": {
                "enabled": False,
                "target_gap": 0.75,
                "tolerance": 0.26,
                "min_gap_for_secondary": 0.5,
                "primary_line_strategy": "lowest_line",
                "fallback_to_highest_if_no_gap_match": True,
            },
        },
    },
}


@dataclass(frozen=True)
class MarketThreshold:
    market_type: str
    odd_min: float
    standard_max: float
    extended_max: float
    edge_min: float
    edge_strong: float
    edge_premium_extended: float
    is_primary_market: bool = False


@dataclass(frozen=True)
class RuntimeConfig:
    payload: dict[str, Any]
    markets: dict[str, MarketThreshold]
    market_priority: dict[str, int]
    critical_flags: set[str]
    confidence_caps: dict[str, int]
    confidence_penalties: dict[str, int]
    data_quality: dict[str, Any]
    rules: dict[str, Any]
    source_path: str | None
    fingerprint: str

    @property
    def name(self) -> str:
        return str(self.payload.get("metadata", {}).get("name") or "default")

    @property
    def label(self) -> str:
        return str(self.payload.get("metadata", {}).get("label") or self.name)

    @property
    def description(self) -> str:
        return str(self.payload.get("metadata", {}).get("description") or "")

    @property
    def pricing_variant(self) -> str:
        return str(self.payload.get("pricing_variant") or "xg_only")

    @property
    def xg_residual_adjustment(self) -> dict[str, Any]:
        value = self.payload.get("xg_residual_adjustment", {})
        return dict(value) if isinstance(value, dict) else {"enabled": False}

    @property
    def allowed_markets(self) -> set[str]:
        return set(self.markets.keys())

    @property
    def primary_markets(self) -> set[str]:
        return {name for name, cfg in self.markets.items() if cfg.is_primary_market}

    @property
    def max_snapshot_age_hours(self) -> float:
        value = self.data_quality.get("max_snapshot_age_hours")
        if value is None:
            raise ValueError("max_snapshot_age_hours is mandatory")
        try:
            normalized = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_snapshot_age_hours must be numeric") from exc
        if normalized <= 0:
            raise ValueError("max_snapshot_age_hours must be positive")
        return normalized


_RUNTIME_CONFIG: RuntimeConfig | None = None


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _build_runtime_config(payload: dict[str, Any], source_path: str | None = None) -> RuntimeConfig:
    normalized = deepcopy(payload)
    metadata = normalized.setdefault("metadata", {})
    metadata.setdefault("name", "default")
    metadata.setdefault("label", metadata["name"])
    text = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    fingerprint = hashlib.md5(text.encode("utf-8")).hexdigest()[:12]
    markets = {
        market_type: MarketThreshold(
            market_type=market_type,
            odd_min=float(cfg["odd_min"]),
            standard_max=float(cfg["standard_max"]),
            extended_max=float(cfg["extended_max"]),
            edge_min=float(cfg["edge_min"]),
            edge_strong=float(cfg["edge_strong"]),
            edge_premium_extended=float(cfg["edge_premium_extended"]),
            is_primary_market=bool(cfg.get("is_primary_market", False)),
        )
        for market_type, cfg in normalized.get("markets", {}).items()
    }
    return RuntimeConfig(
        payload=normalized,
        markets=markets,
        market_priority={k: int(v) for k, v in normalized.get("market_priority", {}).items()},
        critical_flags=set(normalized.get("critical_flags", [])),
        confidence_caps={k: int(v) for k, v in normalized.get("confidence_caps", {}).items()},
        confidence_penalties={k: int(v) for k, v in normalized.get("confidence_penalties", {}).items()},
        data_quality=dict(normalized.get("data_quality", {})),
        rules=normalized.get("rules", {}),
        source_path=source_path,
        fingerprint=fingerprint,
    )


def resolve_config_file(config_name: str | None = None, config_file: str | Path | None = None, *, strict: bool = False) -> Path | None:
    if config_file is not None:
        candidate = Path(config_file).expanduser().resolve()
        if candidate.exists():
            return candidate
        if strict:
            raise ConfigResolutionError(f"Arquivo de configuração não encontrado: {candidate}")
        return None
    if config_name:
        candidate = (CONFIGS_DIR / f"{config_name}.json").resolve()
        if candidate.exists():
            return candidate
        if strict:
            available = ", ".join(item["name"] for item in list_available_configs())
            raise ConfigResolutionError(
                f"Preset de configuração não encontrado: {config_name}. Disponíveis: {available}"
            )
    return None


def load_config_payload(config_name: str | None = None, config_file: str | Path | None = None) -> tuple[dict[str, Any], str | None]:
    explicit_request = config_name is not None or config_file is not None
    path = resolve_config_file(config_name=config_name, config_file=config_file, strict=explicit_request)
    if path is None:
        return deepcopy(DEFAULT_CONFIG_PAYLOAD), None
    payload = json.loads(path.read_text(encoding="utf-8"))
    merged = _deep_merge(DEFAULT_CONFIG_PAYLOAD, payload)
    metadata = merged.setdefault("metadata", {})
    if config_name and not metadata.get("name"):
        metadata["name"] = config_name
    return merged, str(path)


def configure_runtime(config_name: str | None = None, config_file: str | Path | None = None) -> RuntimeConfig:
    global _RUNTIME_CONFIG
    payload, source_path = load_config_payload(config_name=config_name, config_file=config_file)
    _RUNTIME_CONFIG = _build_runtime_config(payload, source_path=source_path)
    return _RUNTIME_CONFIG


def get_runtime_config() -> RuntimeConfig:
    global _RUNTIME_CONFIG
    if _RUNTIME_CONFIG is None:
        _RUNTIME_CONFIG = _build_runtime_config(deepcopy(DEFAULT_CONFIG_PAYLOAD), source_path=None)
    return _RUNTIME_CONFIG


def list_available_configs() -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    for path in sorted(CONFIGS_DIR.glob("*.json")):
        try:
            payload, source = load_config_payload(config_file=path)
            runtime = _build_runtime_config(payload, source_path=source)
            configs.append({
                "name": runtime.name,
                "label": runtime.label,
                "description": runtime.description,
                "path": str(path),
                "fingerprint": runtime.fingerprint,
            })
        except Exception as exc:
            configs.append({
                "name": path.stem,
                "label": path.stem,
                "description": f"erro ao carregar: {exc}",
                "path": str(path),
                "fingerprint": None,
            })
    return configs


def save_runtime_snapshot(run_dir: str | Path) -> Path:
    runtime = get_runtime_config()
    target = Path(run_dir) / "strategy_config_snapshot.json"
    snapshot = deepcopy(runtime.payload)
    snapshot.setdefault("metadata", {})["fingerprint"] = runtime.fingerprint
    snapshot["resolved_from"] = runtime.source_path
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
