import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
SCRIPT_PATH = ROOT / "scripts" / "sync_prices.py"
SPEC = importlib.util.spec_from_file_location("sync_prices", SCRIPT_PATH)
sync_prices = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(sync_prices)


class CatalogConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT / "config.json").read_text())
        existing = json.loads((ROOT / "model_prices_and_context_window.json").read_text())
        cls.catalog, _stats, _cache_count = sync_prices.process_catalog(
            existing,
            {},
            cls.config,
        )

    def test_existing_models_follow_upstream_updates(self):
        self.assertTrue(self.config["update_existing"])
        for prefix in ("glm-", "kimi-", "minimax-", "qwen"):
            self.assertIn(prefix, self.config["prefix_filters"])

    def test_confirmed_price_corrections(self):
        expected = {
            "glm-5.1": (1.4, 4.4, 0.26, None),
            "kimi-k2.6": (0.95, 4.0, 0.16, None),
            "gpt-5.5-pro": (30.0, 180.0, None, None),
        }
        for model, prices in expected.items():
            with self.subTest(model=model):
                self.assertEqual(self.prices_per_million(model), prices)

    def test_new_canonical_models(self):
        expected = {
            "glm-5.2": (1.4, 4.4, 0.26, None),
            "kimi-k2.7-code": (0.95, 4.0, 0.19, None),
            "kimi-k3": (3.0, 15.0, 0.3, None),
            "minimax-m3": (0.3, 1.2, 0.06, None),
            "qwen3.6-plus": (0.5, 3.0, 0.05, 0.625),
            "qwen3.7-max": (2.5, 7.5, 0.5, 3.125),
            "qwen3.7-plus": (0.4, 1.6, 0.04, 0.5),
        }
        for model, prices in expected.items():
            with self.subTest(model=model):
                self.assertEqual(self.prices_per_million(model), prices)

    def test_deepseek_prices_do_not_regress(self):
        self.assertEqual(
            self.prices_per_million("deepseek-v4-flash"),
            (0.14, 0.28, 0.0028, None),
        )
        self.assertEqual(
            self.prices_per_million("deepseek-v4-pro"),
            (0.435, 0.87, 0.003625, None),
        )

    def test_qwen_long_context_tiers_are_preserved(self):
        plus_36 = self.catalog["qwen3.6-plus"]
        self.assertEqual(plus_36["input_cost_per_token_above_256k_tokens"] * 1_000_000, 2.0)
        self.assertEqual(plus_36["output_cost_per_token_above_256k_tokens"] * 1_000_000, 6.0)

        plus_37 = self.catalog["qwen3.7-plus"]
        self.assertEqual(plus_37["input_cost_per_token_above_256k_tokens"] * 1_000_000, 1.2)
        self.assertEqual(plus_37["output_cost_per_token_above_256k_tokens"] * 1_000_000, 4.8)

    def prices_per_million(self, model):
        entry = self.catalog[model]
        def scaled(field):
            value = entry.get(field)
            return None if value in (None, 0) else round(value * 1_000_000, 9)

        return (
            scaled("input_cost_per_token"),
            scaled("output_cost_per_token"),
            scaled("cache_read_input_token_cost"),
            scaled("cache_creation_input_token_cost"),
        )


if __name__ == "__main__":
    unittest.main()
