# model-price-repo

Filtered model pricing data for CRS and sub2api projects. Syncs from the upstream [litellm](https://github.com/BerriAI/litellm) pricing file on a schedule, applying configurable prefix filters to keep only the models you actually use.

## How it works

A GitHub Actions workflow runs every 10 minutes (and on manual trigger):

1. Downloads the full `model_prices_and_context_window.json` from litellm
2. Filters models by the prefix rules in `config.json`
3. Merges new models into the existing output (additive — never removes)
4. Applies alias mappings and custom model definitions
5. Writes the output JSON + SHA-256 hash, commits only if content changed

## Configuration

All settings live in [`config.json`](config.json):

| Field | Description |
|---|---|
| `upstream_url` | URL to the upstream litellm pricing JSON |
| `output_file` | Output filename (default: `model_prices_and_context_window.json`) |
| `hash_file` | SHA-256 hash filename for change detection |
| `sync_mode` | `"additive"` (only add new) or `"full"` (replace each run) |
| `update_existing` | Whether to update pricing data for models already in the output |
| `prefix_filters` | List of prefixes — a model key must start with one to be included |
| `exclude_patterns` | Substring patterns to exclude (applied before prefix matching) |
| `aliases` | Map alias model keys to existing source models (deep copy pricing) |
| `custom_models` | Manually defined pricing objects, always injected |

### Adding new model prefixes

Edit the `prefix_filters` array in `config.json`:

```json
{
  "prefix_filters": [
    "claude-",
    "gpt-",
    "your-new-prefix/"
  ]
}
```

### Adding aliases

Aliases create copies of an existing model's pricing under a new key:

```json
{
  "aliases": {
    "claude-opus-4-6-thinking": {
      "source": "claude-opus-4-6",
      "description": "Thinking variant, same pricing"
    }
  }
}
```

If the source model doesn't exist in the filtered data, the alias is skipped with a warning.

## Running locally

```bash
python3 scripts/sync_prices.py --config config.json --repo-root .
```

No pip dependencies — uses Python standard library only.

## CRS integration

Point CRS to the raw output file from this repo:

```
MODEL_PRICES_URL=https://raw.githubusercontent.com/<owner>/model-price-repo/main/model_prices_and_context_window.json
```

The output JSON structure is identical to what litellm produces (model key -> pricing object), so CRS `pricingService.js` works without changes.

## DeepSeek peak/off-peak pricing convention

DeepSeek bills peak/off-peak rates:

- **Time-of-use (peak/off-peak) pricing** took effect on **2026-08-16 16:00 UTC** (Beijing time 2026-08-17 00:00); see the [official changelog](https://api-docs.deepseek.com/updates).
- **Weekend all-off-peak** took effect on Beijing time **2026-08-23 00:00** (2026-08-22 16:00 UTC). The current time windows, per the [official pricing page](https://api-docs.deepseek.com/quick_start/pricing):

  - Peak hours: 01:00–04:00 and 06:00–10:00 UTC, Monday through Friday (Beijing time weekdays)
  - Peak rate = 2× off-peak rate; all other hours (including weekends) are off-peak

This file is a static price card and cannot express the time dimension, so the official v4 entries (`deepseek-v4-flash`, `deepseek-v4-pro`, `deepseek-v4-flash-vision-exp`) record the **off-peak rates**. Consumers that bill DeepSeek traffic MUST apply the 2× peak multiplier themselves during the peak windows above; billing the recorded rates around the clock under-charges peak traffic by half.

The deprecated `deepseek-chat` / `deepseek-reasoner` entries are an **exception**: they record the **flat rates** in effect when the services were decommissioned (2026-07-24) and must NOT be multiplied by 2 — they were retired before peak/off-peak pricing took effect. Earlier historical prices may differ, so precise historical billing requires a time-versioned price card.

## License

[MIT](LICENSE)
