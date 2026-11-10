# Contributing

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest --cov
```

No service is needed. `DCCAP_TEST_DRAWS` and `DCCAP_TEST_SEED` run the same tests with more (or different) random facilities (CI
also uses 150 draws with seed 11).

Rules that keep the project honest:

- **A change to the analysis needs both implementations.** Change `pipeline.py` (vectorised) and `reference.py` (plain loops) the same
  way, add a hand-computed case to `tests/test_analysis.py` (it runs through both), and let `dccap verify` compare them.
- **A change to the forecast needs a truth.** Run the sweep (`dccap bench --seeds 50`), look at the coverage by distance and at the
  false alarms and misses, and keep seeds 1 to 20 for choosing and seeds 21 to 40 for checking.
- **Numbers in the README and `docs/analysis.md` come from `docs/report.json` and `docs/bench.json`**, and `tests/test_docs.py` checks
  them. After a change to the generator or the analysis, regenerate them (`dccap analyze --out`, then `tools/run_full.ps1` for the
  benchmark) and update the text where a number moved.
- **The demo must not depend on the platform.** Floating-point results differ by about 1e-10 between platforms; compare reports with a
  relative tolerance, never exactly.
