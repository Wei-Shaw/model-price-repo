# model-price-repo

Filtered model pricing data for CRS and sub2api projects. Syncs from the upstream [litellm](https://github.com/BerriAI/litellm) pricing file on a schedule, applying configurable prefix filters to keep only the models you actually use.

## How it works

A GitHub Actions workflow runs every 10 minutes (and on manual trigger):

1. Downloads the full `model_prices_and_context_window.json` from litellm
2. Filters models by the prefix rules in `config.json`, then picks up models that
   upstream only publishes under a provider prefix (`provider_sources`, e.g.
   `gemini/gemini-4-neon` → `gemini-4-neon`)
3. Merges into the existing output (additive — never removes models). With
   `update_existing: true`, every model upstream provides is rebuilt from upstream
   on each run, so upstream price changes (and removed fields) are picked up
4. Applies custom model definitions and alias mappings
5. Writes the output JSON + SHA-256 hash, commits only if content changed

### Precedence (`update_existing: true`)

**Upstream always wins.** For a model that upstream provides (bare key or via
`provider_sources`):

- upstream fields > `custom_models` fields — custom fields only fill fields
  upstream does not have (e.g. a missing `cache_creation_input_token_cost`);
- an alias is skipped once upstream ships a real entry under the alias name.

`custom_models` entries for models upstream does not provide are injected as-is.
Bare upstream keys win over provider-prefixed ones; among `provider_sources`,
earlier entries win.

## Configuration

All settings live in [`config.json`](config.json):

| Field | Description |
|---|---|
| `upstream_url` | URL to the upstream litellm pricing JSON |
| `output_file` | Output filename (default: `model_prices_and_context_window.json`) |
| `hash_file` | SHA-256 hash filename for change detection |
| `sync_mode` | `"additive"` (only add new) or `"full"` (replace each run) |
| `update_existing` | `true`: upstream is the source of truth for models it provides (see Precedence). `false`: legacy — existing entries only absorb new upstream fields, custom fields override |
| `prefix_filters` | List of prefixes — a model key must start with one to be included |
| `provider_sources` | List of `{"provider": "gemini/", "prefixes": ["gemini-"], "lowercase": false}` — strip the provider prefix from upstream keys and include the result if it starts with one of `prefixes` (`lowercase` lower-cases the name, e.g. `minimax/MiniMax-M3` → `minimax-m3`). `alias_of` targets are rewritten accordingly |
| `exclude_patterns` | Substring patterns to exclude (applied before prefix matching) |
| `aliases` | Map alias model keys to existing source models (deep copy pricing) |
| `custom_models` | Manually defined pricing objects (see Precedence) |

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

## License

[MIT](LICENSE)
