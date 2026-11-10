# Architecture

```text
facility.json + inventory.csv --> model.py (strict readers: errors name the line)       generate.py --> facility + inventory + truth
                                      |                                                       |
                                      v                                                       |
                   +------------------+------------------+                                    |
                   v                                     v                                    |
           pipeline.py (NumPy)                   reference.py (plain loops)                   |
                   |                                     |                                    |
                   |   core.py: fill, runway, report layout (shared)                          |
                   |                                     +--> verify.py <-- compares the two
                   v
     analysis.py (one dictionary) <-- score.py <-- the truth
                   |
                   v
     report.json --> report.py (Markdown, figures)          bench.py (speed, accuracy sweep) --> bench.json
```

| File | Role |
|---|---|
| `params.py` | The policy and the device catalog, validated. |
| `model.py` | Facility, plants, racks and inventory; JSON and CSV readers and writers; validation (names, racks, fit in the rack, power, no two devices in the same unit at the same time). |
| `core.py` | What both implementations share: the `fill` and `runway` loops that call each implementation's `place`, and the layout of the report. |
| `pipeline.py` | The analysis on arrays: monthly series, occupancy matrix, rack tables, forecast fits, chunked first fit. |
| `reference.py` | The same, one device at a time. Shares with the pipeline only the definitions in `core.py`. |
| `verify.py` | Compares the two on random facilities with random policy. |
| `synth.py` | Random facilities and inventories (for verification) and large ones built without a Python loop per device (for the benchmark). |
| `generate.py` | The simulation of a data center and its truth. |
| `score.py` | Compares a forecast with the truth. |
| `analysis.py` | A report: the analysis, the score when there is a truth, the true future series to draw, and the what-if. |
| `report.py` | Markdown and figures from a report or a benchmark. Pure functions of the JSON: `dccap render` rebuilds them exactly. |
| `bench.py` | Times, accuracy over many seeds, agreement of the two implementations. |
| `cli.py` | The command line. |

## Decisions

- **Two implementations, not one and a lot of tests.** Hand-computed cases catch what the author thought of; a second implementation
  written differently and compared on random facilities catches the rest. The tests run the hand-computed cases through both.
- **Placement, not just totals.** A data center runs out when a device cannot be placed, not when a sum reaches a limit. The
  analysis keeps the rack by unit occupancy, so stranded capacity and the reason a device is refused are measured rather than guessed.
- **A first fit in chunks.** The occupancy of all racks is a boolean matrix; candidates are examined 64 racks at a time with a cumulative
  sum, so a facility of 17,000 racks places a device without looking at all of them when an early rack has room.
- **A truth the forecast cannot see.** The simulation produces the future and the analysis never reads it; the difference between the
  two is the real error.
- **The report is data first.** `report.json` holds everything (including the true future series); the Markdown and the figure are
  functions of it.
- **No pandas.** NumPy, matplotlib and the standard library are enough, and keep the image small.
