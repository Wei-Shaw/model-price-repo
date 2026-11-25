import unittest

from sync_prices import filter_upstream


class GeminiPricingFilterTest(unittest.TestCase):
    def test_bare_id_uses_google_ai_studio_prices(self):
        prices = {"input_cost_per_token": 3e-6, "cache_read_input_token_cost": 1.5e-7}
        upstream = {
            "vertex_ai/gemini-4-neon": {"input_cost_per_token": 1},
            "gemini/gemini-4-neon": prices,
            "github_copilot/gemini-4-other": {},
            "gemini/gemini-test-only": {},
        }
        config = {"prefix_filters": ["gemini-"], "exclude_patterns": ["test-only"]}
        self.assertEqual(filter_upstream(upstream, config), {"gemini-4-neon": prices})

    def test_explicit_bare_id_wins_in_either_input_order(self):
        entries = [("gemini/gemini-x", {"price": 1}), ("gemini-x", {"price": 2})]
        for ordered in (entries, reversed(entries)):
            result = filter_upstream(dict(ordered), {"prefix_filters": ["gemini-"]})
            self.assertEqual(result, {"gemini-x": {"price": 2}})

    def test_provider_key_filters_keep_their_original_behavior(self):
        upstream = {"gemini/gemini-x": {"price": 1}}
        for prefixes, expected in (([], upstream), (["gemini/"], upstream), (["gpt-"], {})):
            self.assertEqual(filter_upstream(upstream, {"prefix_filters": prefixes}), expected)
        both = filter_upstream(upstream, {"prefix_filters": ["gemini/", "gemini-"]})
        self.assertEqual(both, {**upstream, "gemini-x": {"price": 1}})
        self.assertIsNot(both["gemini-x"], both["gemini/gemini-x"])
