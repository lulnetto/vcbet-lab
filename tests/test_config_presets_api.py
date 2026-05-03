from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException

from vcbet.core import strategy_config
from vcbet.service.routes import config_presets


def _payload(name: str = "base_config") -> dict:
    payload = deepcopy(strategy_config.DEFAULT_CONFIG_PAYLOAD)
    payload["metadata"] = {
        "name": name,
        "label": name.replace("_", " ").title(),
        "description": "Config de teste.",
    }
    payload["pricing_variant"] = "xg_only"
    return payload


class ConfigPresetsApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.configs_dir = self.root / "configs"
        self.configs_dir.mkdir()
        self.patcher = patch.object(strategy_config, "CONFIGS_DIR", self.configs_dir)
        self.patcher.start()
        self.app = FastAPI()
        config_presets.register_routes(self.app, object())

    def tearDown(self) -> None:
        self.patcher.stop()
        self.tmp.cleanup()

    def _write_config(self, name: str, payload: dict | None = None) -> Path:
        path = self.configs_dir / f"{name}.json"
        path.write_text(json.dumps(payload or _payload(name), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _endpoint(self, method: str, path: str):
        for route in self.app.routes:
            if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
                return route.endpoint
        raise AssertionError(f"endpoint não encontrado: {method} {path}")

    def test_list_configs(self) -> None:
        self._write_config("legacy_v2")
        self._write_config("gd_experimental_v1")

        result = self._endpoint("GET", "/api/config-presets")()

        names = {item["name"] for item in result}
        self.assertEqual(names, {"legacy_v2", "gd_experimental_v1"})
        self.assertTrue(next(item for item in result if item["name"] == "legacy_v2")["protected"])
        self.assertIn("total_goals", next(item for item in result if item["name"] == "gd_experimental_v1")["enabled_markets"])

    def test_get_config_detail_has_raw_resolved_and_schema_options(self) -> None:
        payload = _payload("gd_experimental_v1")
        payload["markets"] = {"asian_total": payload["markets"]["asian_total"]}
        self._write_config("gd_experimental_v1", payload)

        detail = self._endpoint("GET", "/api/config-presets/{name}")("gd_experimental_v1")

        self.assertEqual(detail["raw"]["metadata"]["name"], "gd_experimental_v1")
        self.assertIn("total_goals", detail["resolved"]["markets"])
        self.assertIn("asian_handicap", detail["schema_options"]["available_markets"])
        self.assertIn("xg_residual_adjusted_v1", detail["schema_options"]["available_pricing_variants"])

    def test_clone_config(self) -> None:
        self._write_config("gd_experimental_v1")
        req = config_presets.ConfigPresetCloneRequest(
            name="gd_safe_odds_v1",
            label="GD Safe Odds v1",
            description="Clone de teste.",
        )

        detail = self._endpoint("POST", "/api/config-presets/{name}/clone")("gd_experimental_v1", req)

        self.assertEqual(detail["name"], "gd_safe_odds_v1")
        cloned = json.loads((self.configs_dir / "gd_safe_odds_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(cloned["metadata"]["name"], "gd_safe_odds_v1")
        self.assertEqual(cloned["metadata"]["label"], "GD Safe Odds v1")

    def test_reject_invalid_name_and_path_traversal(self) -> None:
        create = self._endpoint("POST", "/api/config-presets")

        with self.assertRaises(HTTPException) as invalid:
            create(config_presets.ConfigPresetCreateRequest(name="bad-name"))
        self.assertEqual(invalid.exception.status_code, 400)

        with self.assertRaises(HTTPException) as traversal:
            config_presets._config_path("../legacy_v2")
        self.assertEqual(traversal.exception.status_code, 400)

    def test_reject_invalid_odd_range(self) -> None:
        self._write_config("gd_experimental_v1")
        payload = _payload("gd_experimental_v1")
        payload["allowed_odd_ranges"] = [{"min": 2.0, "max": 1.9}]

        summary = self._endpoint("POST", "/api/config-presets/{name}/validate")("gd_experimental_v1", payload)

        self.assertFalse(summary["valid"])
        self.assertTrue(any("allowed_odd_ranges" in issue["path"] for issue in summary["errors"]))

    def test_save_valid_config_creates_backup(self) -> None:
        self._write_config("gd_experimental_v1")
        payload = _payload("gd_experimental_v1")
        payload["metadata"]["label"] = "GD Editado"

        detail = self._endpoint("PUT", "/api/config-presets/{name}")("gd_experimental_v1", payload)

        self.assertEqual(detail["raw"]["metadata"]["label"], "GD Editado")
        self.assertTrue((self.configs_dir / "gd_experimental_v1.json.bak").exists())
        self.assertTrue(detail["backup_path"].endswith("gd_experimental_v1.json.bak"))

    def test_delete_non_protected_config(self) -> None:
        self._write_config("temp_config")

        result = self._endpoint("DELETE", "/api/config-presets/{name}")("temp_config")

        self.assertEqual(result, {"status": "deleted", "name": "temp_config"})
        self.assertFalse((self.configs_dir / "temp_config.json").exists())

    def test_refuse_delete_protected_config(self) -> None:
        self._write_config("legacy_v2")

        with self.assertRaises(HTTPException) as exc:
            self._endpoint("DELETE", "/api/config-presets/{name}")("legacy_v2")

        self.assertEqual(exc.exception.status_code, 403)
        self.assertTrue((self.configs_dir / "legacy_v2.json").exists())

    def test_validate_enabled_markets(self) -> None:
        self._write_config("gd_experimental_v1")
        payload = _payload("gd_experimental_v1")
        payload["enabled_markets"] = ["asian_total", "bad_market"]

        summary = self._endpoint("POST", "/api/config-presets/{name}/validate")("gd_experimental_v1", payload)

        self.assertFalse(summary["valid"])
        self.assertTrue(any(issue["path"] == "enabled_markets[1]" for issue in summary["errors"]))

    def test_validate_allowed_odd_ranges(self) -> None:
        self._write_config("gd_experimental_v1")
        payload = _payload("gd_experimental_v1")
        payload["markets"]["asian_total"]["allowed_odd_ranges"] = [{"min": 1.5, "max": 2.0}]

        summary = self._endpoint("POST", "/api/config-presets/{name}/validate")("gd_experimental_v1", payload)

        self.assertTrue(summary["valid"])


if __name__ == "__main__":
    unittest.main()
