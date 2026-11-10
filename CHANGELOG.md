# Changelog

## 1.0.0

First release.

- Strict readers and writers for a facility (JSON) and an inventory (CSV), with errors that name the line and a check that no two
  devices occupy the same rack unit at the same time.
- The analysis: space, power (allocated from the nameplate) and cooling (measured heat) against the policy limits, a per-rack table with
  the largest free block, stranded space and power, and a forecast per resource (line or exponential over a window, interval from the
  first-passage time of a random walk with drift) of when each reaches its limit.
- "How many more fit" per catalog model by first fit across racks, with the reason the next device is refused, and a what-if that
  adds devices now and every month.
- A plain Python implementation of the same analysis and `dccap verify`, which compares the two on random facilities.
- A synthetic data center with a known future (projects, purchases, retirements, devices turned away) and a scoring of the forecast
  against it, with a sweep over simulated data centers and dates.
- A report (JSON, Markdown, figure) rebuilt exactly from its JSON, and a benchmark of speed, accuracy and agreement.
- A command line (`generate`, `validate`, `analyze`, `plan`, `verify`, `bench`, `render`) with exit codes for a pipeline.
- Docker image (no network, read-only, no capabilities); CI on Python 3.11 to 3.14, Linux, Windows and macOS.
