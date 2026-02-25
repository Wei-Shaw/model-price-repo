#!/usr/bin/env python3
"""Sync model pricing from upstream litellm, applying prefix filters,
aliases, and custom model definitions.

Usage:
    python3 scripts/sync_prices.py --config config.json --repo-root .
"""

import argparse
import copy
from decimal import Decimal
import hashlib
import json
import logging
import os
import sys
import urllib.error
import urllib.request

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REQUIRED_CONFIG_KEYS = [
    "upstream_url",
    "output_file",
    "hash_file",
    "sync_mode",
    "prefix_filters",
]


def load_config(path: str) -> dict:
    """Read and validate config.json."""
    if not os.path.isfile(path):
        log.error("Config file not found: %s", path)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    missing = [k for k in REQUIRED_CONFIG_KEYS if k not in cfg]
    if missing:
        log.error("Config missing required keys: %s", ", ".join(missing))
        sys.exit(1)
    if cfg["sync_mode"] not in ("additive", "full"):
        log.error("Invalid sync_mode '%s'; must be 'additive' or 'full'", cfg["sync_mode"])
        sys.exit(1)
    return cfg


# ---------------------------------------------------------------------------
# Existing data
# ---------------------------------------------------------------------------


def load_existing(path: str) -> dict:
    """Load the current output file, or return {} on first run."""
    if not os.path.isfile(path):
        log.info("No existing output file; starting fresh.")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_existing_hash(path: str) -> str:
    """Read the stored SHA-256 hex digest, or return empty string."""
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


# ---------------------------------------------------------------------------
# Upstream fetch
# ---------------------------------------------------------------------------


def fetch_upstream(url: str) -> dict:
    """Download the full upstream pricing JSON."""
    log.info("Fetching upstream: %s", url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "model-price-repo/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except (urllib.error.URLError, OSError) as exc:
        log.error("Failed to fetch upstream: %s", exc)
        sys.exit(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error("Upstream JSON is invalid: %s", exc)
        sys.exit(1)

    if not isinstance(data, dict):
        log.error("Upstream JSON is not an object (got %s)", type(data).__name__)
        sys.exit(1)

    log.info("Upstream contains %d model entries.", len(data))
    return data


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def filter_upstream(data: dict, config: dict) -> dict:
    """Apply prefix_filters and exclude_patterns to upstream data."""
    prefixes = tuple(config.get("prefix_filters", []))
    excludes = config.get("exclude_patterns", [])

    filtered = {}
    for key, value in data.items():
        # Exclude first
        if any(pat in key for pat in excludes):
            continue
        # Then check prefix match
        if prefixes and not key.startswith(prefixes):
            continue
        filtered[key] = value

    log.info("Filtered to %d models (from %d upstream).", len(filtered), len(data))
    return filtered


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


def merge_models(
    existing: dict,
    filtered: dict,
    sync_mode: str,
    update_existing: bool,
) -> tuple[dict, dict]:
    """Merge filtered upstream into existing data.

    Returns (merged_dict, stats_dict).
    """
    stats = {"added": 0, "updated": 0, "unchanged": 0, "total_upstream": len(filtered)}

    if sync_mode == "full":
        # Full mode: replace entirely with filtered upstream
        stats["added"] = len(filtered)
        return dict(filtered), stats

    # Additive mode
    merged = dict(existing)
    for key, value in filtered.items():
        if key not in merged:
            merged[key] = value
            stats["added"] += 1
        elif update_existing:
            if merged[key] != value:
                merged[key] = value
                stats["updated"] += 1
            else:
                stats["unchanged"] += 1
        else:
            stats["unchanged"] += 1

    return merged, stats


# ---------------------------------------------------------------------------
# Aliases & custom models
# ---------------------------------------------------------------------------


def apply_aliases(data: dict, aliases: dict) -> dict:
    """Deep-copy source model data into alias keys."""
    for alias_key, alias_cfg in aliases.items():
        source = alias_cfg.get("source", "")
        if source not in data:
            log.warning(
                "Alias '%s': source model '%s' not found; skipping.",
                alias_key,
                source,
            )
            continue
        data[alias_key] = copy.deepcopy(data[source])
        log.info("Alias '%s' -> '%s' applied.", alias_key, source)
    return data


def apply_custom_models(data: dict, custom: dict) -> dict:
    """Inject custom model definitions (deep merge for existing, full set for new)."""
    for key, value in custom.items():
        if key in data and isinstance(data[key], dict) and isinstance(value, dict):
            data[key].update(value)
            log.info("Custom model '%s' merged (deep).", key)
        else:
            data[key] = value
            log.info("Custom model '%s' injected.", key)
    return data


def fill_cache_1hr_pricing(data: dict, config: dict) -> int:
    """Auto-fill missing cache_creation_input_token_cost_above_1hr for matching models.

    Uses a fixed ratio (default 1.6x) of the 5-minute cache write cost.
    Returns the number of models auto-filled.
    """
    auto_fill_cfg = config.get("cache_1hr_auto_fill")
    if not auto_fill_cfg:
        return 0

    prefix = auto_fill_cfg.get("model_prefix", "claude-")
    ratio = auto_fill_cfg.get("ratio", 1.6)
    count = 0

    for key, value in data.items():
        if not key.startswith(prefix):
            continue
        if not isinstance(value, dict):
            continue
        cost_5m = value.get("cache_creation_input_token_cost")
        if cost_5m is None:
            continue
        if value.get("cache_creation_input_token_cost_above_1hr") is not None:
            continue
        value["cache_creation_input_token_cost_above_1hr"] = float(
            Decimal(str(cost_5m)) * Decimal(str(ratio))
        )
        log.info("Auto-filled cache 1hr cost for '%s': %s * %s = %s", key, cost_5m, ratio, value["cache_creation_input_token_cost_above_1hr"])
        count += 1

    return count


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def compute_hash(json_bytes: bytes) -> str:
    """Return hex SHA-256 of the given bytes."""
    return hashlib.sha256(json_bytes).hexdigest()


def write_output(data: dict, json_path: str, hash_path: str, old_hash: str) -> tuple[bool, str]:
    """Write sorted JSON and SHA-256 hash file.

    Returns (changed: bool, new_hash: str).
    """
    json_bytes = (json.dumps(data, sort_keys=True, indent=2) + "\n").encode("utf-8")
    new_hash = compute_hash(json_bytes)

    if new_hash == old_hash:
        log.info("No changes detected (hash matches).")
        return False, new_hash

    with open(json_path, "wb") as f:
        f.write(json_bytes)
    with open(hash_path, "w", encoding="utf-8") as f:
        f.write(new_hash + "\n")

    log.info("Output written: %s (%d models)", json_path, len(data))
    log.info("Hash written:   %s", hash_path)
    return True, new_hash


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync model pricing from upstream.")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--repo-root", default=".", help="Repository root directory")
    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo_root)
    config_path = os.path.join(repo_root, args.config)

    # 1. Load config
    config = load_config(config_path)

    output_path = os.path.join(repo_root, config["output_file"])
    hash_path = os.path.join(repo_root, config["hash_file"])

    # 2. Load existing data
    existing = load_existing(output_path)
    old_hash = load_existing_hash(hash_path)
    log.info("Existing output has %d models.", len(existing))

    # 3. Fetch upstream
    upstream = fetch_upstream(config["upstream_url"])

    # 4. Filter
    filtered = filter_upstream(upstream, config)

    # 5. Merge
    merged, stats = merge_models(
        existing,
        filtered,
        config["sync_mode"],
        config.get("update_existing", False),
    )
    log.info(
        "Merge stats: %d added, %d updated, %d unchanged.",
        stats["added"],
        stats["updated"],
        stats["unchanged"],
    )

    # 6. Aliases
    aliases = config.get("aliases", {})
    if aliases:
        merged = apply_aliases(merged, aliases)

    # 7. Auto-fill cache 1hr pricing
    cache_1hr_count = fill_cache_1hr_pricing(merged, config)

    # 8. Custom models
    custom = config.get("custom_models", {})
    if custom:
        merged = apply_custom_models(merged, custom)

    # 9. Write output
    changed, new_hash = write_output(merged, output_path, hash_path, old_hash)

    # 10. Report
    log.info("--- Sync Report ---")
    log.info("Total models in output: %d", len(merged))
    log.info("Added:     %d", stats["added"])
    log.info("Updated:   %d", stats["updated"])
    log.info("Unchanged: %d", stats["unchanged"])
    log.info("Aliases:   %d", len(aliases))
    log.info("Cache 1hr auto-filled: %d", cache_1hr_count)
    log.info("Custom:    %d", len(custom))

    # Machine-readable output for CI
    print(f"CHANGED={str(changed).lower()}")
    print(f"HASH={new_hash}")


if __name__ == "__main__":
    main()
