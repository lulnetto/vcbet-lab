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


AVAILABLE_MARKETS: tuple[str, ...] = (
    "asian_total",
    "total_goals",
    "asian_handicap",
    "draw_no_bet",
    "team_total",
    "btts",
)

AVAILABLE_PRICING_VARIANTS: tuple[str, ...] = (
    "xg_only",
    "xg_residual_adjusted_v1",
)

NON_STRATEGY_CONFIG_FILES = {"profile_ledger_bindings.json"}


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
class OddRange:
    min: float
    max: float

    def contains(self, value: float) -> bool:
        return self.min <= value <= self.max


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
    allowed_odd_ranges: tuple[OddRange, ...] = ()


@dataclass(frozen=True)
class ConfigValidationIssue:
    severity: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class RuntimeConfig:
    payload: dict[str, Any]
    markets: dict[str, MarketThreshold]
    enabled_markets: set[str] | None
    allowed_odd_ranges: tuple[OddRange, ...]
    blocked_odd_ranges: tuple[OddRange, ...]
    side_rules: dict[str, Any]
    ev_policy: dict[str, Any]
    market_exceptions: dict[str, Any]
    stake_policy: dict[str, Any]
    sport_sense_policy: dict[str, Any]
    league_filter: dict[str, Any]
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
        if self.enabled_markets is not None:
            return set(self.enabled_markets)
        return set(self.markets.keys())

    @property
    def primary_markets(self) -> set[str]:
        return {name for name, cfg in self.markets.items() if cfg.is_primary_market and name in self.allowed_markets}

    def allowed_odd_ranges_for_market(self, market_type: str) -> tuple[OddRange, ...]:
        market = self.markets.get(market_type)
        if market and market.allowed_odd_ranges:
            return market.allowed_odd_ranges
        return self.allowed_odd_ranges

    def blocked_odd_ranges_for_market(self, market_type: str) -> tuple[OddRange, ...]:
        return self.blocked_odd_ranges

    def is_league_allowed(self, league: str) -> bool:
        cfg = self.league_filter if isinstance(self.league_filter, dict) else {}
        mode = str(cfg.get("mode") or "disabled").strip().lower()
        if not cfg.get("enabled", mode != "disabled") or mode == "disabled":
            return True
        league_key = str(league or "").strip().casefold()
        allowed = {str(item).strip().casefold() for item in cfg.get("allowed_leagues", []) if str(item).strip()}
        blocked = {str(item).strip().casefold() for item in cfg.get("blocked_leagues", []) if str(item).strip()}
        if mode == "allowlist":
            return bool(league_key and league_key in allowed)
        if mode == "blocklist":
            return not (league_key and league_key in blocked)
        return True

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


def _normalize_odd_ranges(value: Any, *, field_name: str = "allowed_odd_ranges") -> tuple[OddRange, ...]:
    if not value:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    ranges: list[OddRange] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"{field_name} items must be objects")
        ranges.append(OddRange(min=float(item["min"]), max=float(item["max"])))
    return tuple(ranges)


def resolve_strategy_config_payload(payload: dict[str, Any], config_name: str | None = None) -> dict[str, Any]:
    merged = _deep_merge(DEFAULT_CONFIG_PAYLOAD, payload)
    metadata = merged.setdefault("metadata", {})
    raw_metadata = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
    if config_name and not raw_metadata.get("name"):
        metadata["name"] = config_name
    metadata.setdefault("name", config_name or "default")
    metadata.setdefault("label", metadata["name"])
    return merged


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
            allowed_odd_ranges=_normalize_odd_ranges(cfg.get("allowed_odd_ranges"), field_name=f"markets.{market_type}.allowed_odd_ranges"),
        )
        for market_type, cfg in normalized.get("markets", {}).items()
    }
    enabled_value = normalized.get("enabled_markets")
    enabled_markets = (
        {str(item) for item in enabled_value}
        if isinstance(enabled_value, list)
        else None
    )
    league_filter = normalized.get("league_filter", {})
    if not isinstance(league_filter, dict):
        league_filter = {}
    return RuntimeConfig(
        payload=normalized,
        markets=markets,
        enabled_markets=enabled_markets,
        allowed_odd_ranges=_normalize_odd_ranges(normalized.get("allowed_odd_ranges"), field_name="allowed_odd_ranges"),
        blocked_odd_ranges=_normalize_odd_ranges(normalized.get("blocked_odd_ranges"), field_name="blocked_odd_ranges"),
        side_rules=dict(normalized.get("side_rules", {}) if isinstance(normalized.get("side_rules", {}), dict) else {}),
        ev_policy=dict(normalized.get("ev_policy", {}) if isinstance(normalized.get("ev_policy", {}), dict) else {}),
        market_exceptions=dict(normalized.get("market_exceptions", {}) if isinstance(normalized.get("market_exceptions", {}), dict) else {}),
        stake_policy=dict(normalized.get("stake_policy", {}) if isinstance(normalized.get("stake_policy", {}), dict) else {}),
        sport_sense_policy=dict(normalized.get("sport_sense_policy", {}) if isinstance(normalized.get("sport_sense_policy", {}), dict) else {}),
        league_filter=dict(league_filter),
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


def load_raw_config_payload(config_name: str | None = None, config_file: str | Path | None = None) -> tuple[dict[str, Any], str | None]:
    explicit_request = config_name is not None or config_file is not None
    path = resolve_config_file(config_name=config_name, config_file=config_file, strict=explicit_request)
    if path is None:
        return deepcopy(DEFAULT_CONFIG_PAYLOAD), None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload, str(path)


def load_config_payload(config_name: str | None = None, config_file: str | Path | None = None) -> tuple[dict[str, Any], str | None]:
    explicit_request = config_name is not None or config_file is not None
    path = resolve_config_file(config_name=config_name, config_file=config_file, strict=explicit_request)
    if path is None:
        return deepcopy(DEFAULT_CONFIG_PAYLOAD), None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return resolve_strategy_config_payload(payload, config_name=config_name or path.stem), str(path)


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
        if path.name in NON_STRATEGY_CONFIG_FILES:
            continue
        try:
            payload, source = load_config_payload(config_name=path.stem)
            runtime = _build_runtime_config(payload, source_path=source)
            configs.append({
                "name": runtime.name,
                "label": runtime.label,
                "description": runtime.description,
                "path": str(path),
                "fingerprint": runtime.fingerprint,
                "pricing_variant": runtime.pricing_variant,
                "enabled_markets": sorted(runtime.allowed_markets),
                "updated_at": path.stat().st_mtime,
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


def _issue(issues: list[ConfigValidationIssue], severity: str, path: str, message: str) -> None:
    issues.append(ConfigValidationIssue(severity=severity, path=path, message=message))


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _validate_number(
    issues: list[ConfigValidationIssue],
    payload: dict[str, Any],
    key: str,
    path: str,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
    positive: bool = False,
) -> float | None:
    value = _as_float(payload.get(key))
    if value is None:
        _issue(issues, "error", f"{path}.{key}", "deve ser numérico")
        return None
    if positive and value <= 0:
        _issue(issues, "error", f"{path}.{key}", "deve ser positivo")
    if min_value is not None and value < min_value:
        _issue(issues, "error", f"{path}.{key}", f"deve ser >= {min_value}")
    if max_value is not None and value > max_value:
        _issue(issues, "error", f"{path}.{key}", f"deve ser <= {max_value}")
    return value


def _validate_odd_ranges(issues: list[ConfigValidationIssue], value: Any, path: str) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        _issue(issues, "error", path, "deve ser uma lista de ranges")
        return
    for idx, item in enumerate(value):
        item_path = f"{path}[{idx}]"
        if not isinstance(item, dict):
            _issue(issues, "error", item_path, "range deve ser objeto com min e max")
            continue
        min_value = _as_float(item.get("min"))
        max_value = _as_float(item.get("max"))
        if min_value is None or max_value is None:
            _issue(issues, "error", item_path, "range deve ter min e max numéricos")
            continue
        if min_value <= 1.0:
            _issue(issues, "error", f"{item_path}.min", "min deve ser > 1.0")
        if max_value <= min_value:
            _issue(issues, "error", f"{item_path}.max", "max deve ser maior que min")
        if max_value > 10.0:
            _issue(issues, "error", f"{item_path}.max", "max deve ser <= 10.0")


def _validate_optional_positive_int_or_null(issues: list[ConfigValidationIssue], value: Any, path: str) -> None:
    if value is None:
        return
    try:
        number = int(value)
    except (TypeError, ValueError):
        _issue(issues, "error", path, "deve ser inteiro positivo ou null")
        return
    if number <= 0:
        _issue(issues, "error", path, "deve ser inteiro positivo ou null")


def _validate_optional_non_negative_or_null(issues: list[ConfigValidationIssue], value: Any, path: str) -> None:
    if value is None:
        return
    number = _as_float(value)
    if number is None or number < 0:
        _issue(issues, "error", path, "deve ser >= 0 ou null")


def validate_strategy_config_payload(payload: dict[str, Any], expected_name: str | None = None) -> list[ConfigValidationIssue]:
    issues: list[ConfigValidationIssue] = []
    if not isinstance(payload, dict):
        return [ConfigValidationIssue("error", "$", "payload deve ser um objeto JSON")]

    known_top_level = {
        "metadata",
        "pricing_variant",
        "xg_residual_adjustment",
        "enabled_markets",
        "allowed_odd_ranges",
        "blocked_odd_ranges",
        "side_rules",
        "ev_policy",
        "market_exceptions",
        "stake_policy",
        "sport_sense_policy",
        "league_filter",
        "market_priority",
        "markets",
        "critical_flags",
        "confidence_caps",
        "confidence_penalties",
        "data_quality",
        "rules",
    }
    for key in sorted(set(payload) - known_top_level):
        _issue(issues, "warning", key, "campo desconhecido será preservado")

    try:
        resolved = resolve_strategy_config_payload(payload, config_name=expected_name)
    except Exception as exc:
        return [ConfigValidationIssue("error", "$", f"não foi possível resolver defaults: {exc}")]

    metadata = resolved.get("metadata", {})
    if not isinstance(metadata, dict):
        _issue(issues, "error", "metadata", "metadata deve ser objeto")
        metadata = {}
    name = str(metadata.get("name") or "").strip()
    label = str(metadata.get("label") or "").strip()
    if expected_name and name != expected_name:
        _issue(issues, "error", "metadata.name", "deve ser igual ao nome do arquivo")
    if not name:
        _issue(issues, "error", "metadata.name", "é obrigatório")
    if not label:
        _issue(issues, "error", "metadata.label", "não pode ficar vazio")

    pricing_variant = str(resolved.get("pricing_variant") or "").strip()
    if pricing_variant not in AVAILABLE_PRICING_VARIANTS:
        _issue(issues, "error", "pricing_variant", f"deve ser um de: {', '.join(AVAILABLE_PRICING_VARIANTS)}")

    enabled_markets = payload.get("enabled_markets")
    if enabled_markets is not None:
        if not isinstance(enabled_markets, list):
            _issue(issues, "error", "enabled_markets", "deve ser lista")
        else:
            for idx, market in enumerate(enabled_markets):
                if str(market) not in AVAILABLE_MARKETS:
                    _issue(issues, "error", f"enabled_markets[{idx}]", "mercado inválido")

    _validate_odd_ranges(issues, payload.get("allowed_odd_ranges"), "allowed_odd_ranges")
    _validate_odd_ranges(issues, payload.get("blocked_odd_ranges"), "blocked_odd_ranges")

    side_rules = payload.get("side_rules")
    if side_rules is not None:
        if not isinstance(side_rules, dict):
            _issue(issues, "error", "side_rules", "deve ser objeto")
        else:
            for market_type, cfg in side_rules.items():
                if str(market_type) not in AVAILABLE_MARKETS:
                    _issue(issues, "warning", f"side_rules.{market_type}", "mercado desconhecido será preservado")
                if not isinstance(cfg, dict):
                    _issue(issues, "error", f"side_rules.{market_type}", "regra deve ser objeto")
                    continue
                for key in ("allowed_sides", "blocked_sides"):
                    if key in cfg and not isinstance(cfg.get(key), list):
                        _issue(issues, "error", f"side_rules.{market_type}.{key}", "deve ser lista")

    ev_policy = payload.get("ev_policy")
    if ev_policy is not None:
        if not isinstance(ev_policy, dict):
            _issue(issues, "error", "ev_policy", "deve ser objeto")
        else:
            if "cap_ev_score_contribution" in ev_policy:
                _validate_number(issues, ev_policy, "cap_ev_score_contribution", "ev_policy", min_value=0.0, max_value=1.0)
            min_by_market = ev_policy.get("min_ev_by_market")
            if min_by_market is not None:
                if not isinstance(min_by_market, dict):
                    _issue(issues, "error", "ev_policy.min_ev_by_market", "deve ser objeto")
                else:
                    for market_type, value in min_by_market.items():
                        if str(market_type) not in AVAILABLE_MARKETS:
                            _issue(issues, "warning", f"ev_policy.min_ev_by_market.{market_type}", "mercado desconhecido será preservado")
                        if _as_float(value) is None:
                            _issue(issues, "error", f"ev_policy.min_ev_by_market.{market_type}", "deve ser numérico")

    market_exceptions = payload.get("market_exceptions")
    if market_exceptions is not None:
        if not isinstance(market_exceptions, dict):
            _issue(issues, "error", "market_exceptions", "deve ser objeto")
        else:
            btts = market_exceptions.get("btts")
            if btts is not None:
                if not isinstance(btts, dict):
                    _issue(issues, "error", "market_exceptions.btts", "deve ser objeto")
                else:
                    yes = btts.get("yes")
                    if yes is not None:
                        if not isinstance(yes, dict):
                            _issue(issues, "error", "market_exceptions.btts.yes", "deve ser objeto")
                        else:
                            if "allow_negative_ev_floor" in yes:
                                _validate_number(issues, yes, "allow_negative_ev_floor", "market_exceptions.btts.yes", min_value=-1.0, max_value=1.0)
                            for key in ("min_odd", "max_odd"):
                                if key in yes:
                                    _validate_number(issues, yes, key, "market_exceptions.btts.yes", min_value=1.01, max_value=10.0)
                            if "stake_cap" in yes:
                                _validate_number(issues, yes, "stake_cap", "market_exceptions.btts.yes", min_value=0.0)
                            min_odd = _as_float(yes.get("min_odd"))
                            max_odd = _as_float(yes.get("max_odd"))
                            if min_odd is not None and max_odd is not None and max_odd <= min_odd:
                                _issue(issues, "error", "market_exceptions.btts.yes.max_odd", "deve ser maior que min_odd")
                    no = btts.get("no")
                    if no is not None and not isinstance(no, dict):
                        _issue(issues, "error", "market_exceptions.btts.no", "deve ser objeto")

    stake_policy = payload.get("stake_policy")
    if stake_policy is not None:
        if not isinstance(stake_policy, dict):
            _issue(issues, "error", "stake_policy", "deve ser objeto")
        else:
            for key in ("default_stake", "full_stake", "max_stake", "odds_above_2_50_max_stake"):
                if key in stake_policy:
                    _validate_number(issues, stake_policy, key, "stake_policy", min_value=0.0)
            if "full_stake_only_for" in stake_policy and not isinstance(stake_policy.get("full_stake_only_for"), list):
                _issue(issues, "error", "stake_policy.full_stake_only_for", "deve ser lista")
            reduced = stake_policy.get("reduced_stake_for")
            if reduced is not None:
                if not isinstance(reduced, dict):
                    _issue(issues, "error", "stake_policy.reduced_stake_for", "deve ser objeto")
                else:
                    for market_type, value in reduced.items():
                        if str(market_type) not in AVAILABLE_MARKETS:
                            _issue(issues, "warning", f"stake_policy.reduced_stake_for.{market_type}", "mercado desconhecido será preservado")
                        if _as_float(value) is None or float(value) < 0:
                            _issue(issues, "error", f"stake_policy.reduced_stake_for.{market_type}", "deve ser >= 0")

    sport_sense = payload.get("sport_sense_policy")
    if sport_sense is not None:
        if not isinstance(sport_sense, dict):
            _issue(issues, "error", "sport_sense_policy", "deve ser objeto")
        else:
            team_total_policy = sport_sense.get("team_total_policy")
            if team_total_policy is not None:
                if not isinstance(team_total_policy, dict):
                    _issue(issues, "error", "sport_sense_policy.team_total_policy", "deve ser objeto")
                else:
                    for key in (
                        "underdog_over_allow_lines_lte",
                        "underdog_over_block_lines_gte",
                        "favorite_under_allow_lines_gte",
                        "favorite_under_block_lines_lte",
                    ):
                        if key in team_total_policy:
                            _validate_number(
                                issues,
                                team_total_policy,
                                key,
                                "sport_sense_policy.team_total_policy",
                                min_value=0.0,
                            )

    raw_markets = payload.get("markets", {})
    if raw_markets is not None and not isinstance(raw_markets, dict):
        _issue(issues, "error", "markets", "markets deve ser objeto")
        raw_markets = {}
    for market_type, cfg in (raw_markets or {}).items():
        if str(market_type) not in AVAILABLE_MARKETS:
            _issue(issues, "error", f"markets.{market_type}", "mercado inválido")
        if isinstance(cfg, dict):
            known_market_fields = {
                "odd_min",
                "standard_max",
                "extended_max",
                "edge_min",
                "edge_strong",
                "edge_premium_extended",
                "is_primary_market",
                "allowed_odd_ranges",
            }
            for key in sorted(set(cfg) - known_market_fields):
                _issue(issues, "warning", f"markets.{market_type}.{key}", "campo desconhecido será preservado")
            _validate_odd_ranges(issues, cfg.get("allowed_odd_ranges"), f"markets.{market_type}.allowed_odd_ranges")

    for market_type, cfg in resolved.get("markets", {}).items():
        if str(market_type) not in AVAILABLE_MARKETS:
            continue
        if not isinstance(cfg, dict):
            _issue(issues, "error", f"markets.{market_type}", "config do mercado deve ser objeto")
            continue
        path = f"markets.{market_type}"
        odd_min = _validate_number(issues, cfg, "odd_min", path, min_value=1.01, max_value=10.0)
        standard_max = _validate_number(issues, cfg, "standard_max", path, min_value=1.01, max_value=10.0)
        extended_max = _validate_number(issues, cfg, "extended_max", path, min_value=1.01, max_value=10.0)
        if odd_min is not None and standard_max is not None and standard_max <= odd_min:
            _issue(issues, "error", f"{path}.standard_max", "deve ser maior que odd_min")
        if odd_min is not None and extended_max is not None and extended_max <= odd_min:
            _issue(issues, "error", f"{path}.extended_max", "deve ser maior que odd_min")
        edge_min = _validate_number(issues, cfg, "edge_min", path, min_value=0.0, max_value=1.0)
        edge_strong = _validate_number(issues, cfg, "edge_strong", path, min_value=0.0, max_value=1.0)
        _validate_number(issues, cfg, "edge_premium_extended", path, min_value=0.0, max_value=1.0)
        if edge_min is not None and edge_strong is not None and edge_strong < edge_min:
            _issue(issues, "error", f"{path}.edge_strong", "deve ser >= edge_min")

    league_filter = payload.get("league_filter")
    if league_filter is not None:
        if not isinstance(league_filter, dict):
            _issue(issues, "error", "league_filter", "deve ser objeto")
        else:
            mode = str(league_filter.get("mode") or "disabled")
            if mode not in {"disabled", "allowlist", "blocklist"}:
                _issue(issues, "error", "league_filter.mode", "deve ser disabled, allowlist ou blocklist")
            for key in ("allowed_leagues", "blocked_leagues"):
                if key in league_filter and not isinstance(league_filter.get(key), list):
                    _issue(issues, "error", f"league_filter.{key}", "deve ser lista")

    xg = resolved.get("xg_residual_adjustment", {})
    if xg is not None and not isinstance(xg, dict):
        _issue(issues, "error", "xg_residual_adjustment", "deve ser objeto")
        xg = {}
    if isinstance(xg, dict):
        if "weight" in xg:
            _validate_number(issues, xg, "weight", "xg_residual_adjustment", min_value=0.0, max_value=1.0)
        for key in ("max_residual_abs", "max_lambda_adjustment_pct"):
            if key in xg:
                _validate_number(issues, xg, key, "xg_residual_adjustment", positive=True)
        if "min_games" in xg:
            value = _as_float(xg.get("min_games"))
            if value is None or value < 0 or int(value) != value:
                _issue(issues, "error", "xg_residual_adjustment.min_games", "deve ser inteiro >= 0")
        if "markets" in xg:
            if not isinstance(xg.get("markets"), list):
                _issue(issues, "error", "xg_residual_adjustment.markets", "deve ser lista")
            else:
                for idx, market in enumerate(xg.get("markets", [])):
                    if str(market) not in AVAILABLE_MARKETS:
                        _issue(issues, "error", f"xg_residual_adjustment.markets[{idx}]", "mercado inválido")

    portfolio = resolved.get("rules", {}).get("portfolio", {})
    if portfolio is not None and not isinstance(portfolio, dict):
        _issue(issues, "error", "rules.portfolio", "deve ser objeto")
        portfolio = {}
    if isinstance(portfolio, dict):
        _validate_optional_positive_int_or_null(
            issues,
            portfolio.get("max_picks_per_match"),
            "rules.portfolio.max_picks_per_match",
        )
        for key in (
            "max_picks_per_league",
            "max_stake_per_league",
            "max_picks_per_market_family",
            "max_stake_per_market_family",
        ):
            _validate_optional_non_negative_or_null(issues, portfolio.get(key), f"rules.portfolio.{key}")

    return issues
