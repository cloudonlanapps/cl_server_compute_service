# QUICK – Test Commands

## Run all unit tests

```bash
uv run pytest tests/ -v -m "not integration"
```

Duration: ~0.5 seconds
No external services required

## Run all tests

```bash
uv run pytest
```

Duration: ~2 seconds
Coverage: 90% minimum required (HTML + terminal reports)

## Run all integration tests

```bash
uv run pytest tests/test_integration.py -v
```

Duration: ~1 second
No external services required (uses in-memory databases)
