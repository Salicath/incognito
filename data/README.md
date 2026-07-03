# Vendored data

## `justdeleteme_sites.json`

Account-deletion instructions (deletion URL, difficulty, notes, domains) used by
`backend/core/account_registry.py` to turn a discovered account into a concrete
erasure route.

- **Source:** [jdm-contrib/jdm](https://github.com/jdm-contrib/jdm) — the maintained
  community fork powering [JustDelete.me](https://justdeleteme.xyz).
- **File:** `_data/sites.json`
- **License:** MIT (JustDelete.me contributors)
- **Snapshot taken:** 2026-07-03 (2556 entries)

Vendored (rather than fetched at runtime) so the tool works offline and pins a known
dataset. Refresh by re-downloading the raw file:

```bash
curl -sSL https://raw.githubusercontent.com/jdm-contrib/jdm/master/_data/sites.json \
  -o data/justdeleteme_sites.json
```
