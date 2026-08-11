import copy
import importlib.util
from pathlib import Path
import unittest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "sync_prices.py"
SPEC = importlib.util.spec_from_file_location("sync_prices", SCRIPT_PATH)
sync_prices = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(sync_prices)


class SyncPricesTest(unittest.TestCase):
    def test_custom_models_are_available_to_aliases(self):
        config = {
            "sync_mode": "additive",
            "update_existing": True,
            "prefix_filters": [],
            "exclude_patterns": [],
            "custom_models": {
                "canonical-model": {
                    "input_cost_per_token": 1e-6,
                    "output_cost_per_token": 2e-6,
                }
            },
            "aliases": {
                "public-alias": {
                    "source": "canonical-model",
                    "description": "Underlying model reference price",
                }
            },
        }

        catalog, _stats, _cache_count = sync_prices.process_catalog({}, {}, config)

        self.assertEqual(catalog["public-alias"]["input_cost_per_token"], 1e-6)
        self.assertEqual(catalog["public-alias"]["output_cost_per_token"], 2e-6)

    def test_alias_records_safe_reference_metadata(self):
        source = {
            "canonical-model": {
                "input_cost_per_token": 1e-6,
                "output_cost_per_token": 2e-6,
            }
        }
        aliases = {
            "public-alias": {
                "source": "canonical-model",
                "description": "Underlying model reference price",
            }
        }

        result = sync_prices.apply_aliases(copy.deepcopy(source), aliases)

        self.assertEqual(result["public-alias"]["pricing_reference_model"], "canonical-model")
        self.assertEqual(
            result["public-alias"]["pricing_reference_note"],
            "Underlying model reference price",
        )
        self.assertNotIn("pricing_reference_model", result["canonical-model"])

    def test_custom_models_can_clear_incorrect_upstream_fields(self):
        data = {
            "model": {
                "input_cost_per_token": 1e-6,
                "cache_read_input_token_cost": 1e-7,
            }
        }

        result = sync_prices.apply_custom_models(
            data,
            {"model": {"cache_read_input_token_cost": None}},
        )

        self.assertIsNone(result["model"]["cache_read_input_token_cost"])


if __name__ == "__main__":
    unittest.main()
