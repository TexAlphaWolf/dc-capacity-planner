# Security

## Model

dccap is a command line program that **reads a facility JSON and an inventory CSV, computes metrics, and writes files**. It starts no
service, opens no network connection and runs no code from its input.

- **What it reads:** the facility JSON (only known fields are read, every value is checked), the inventory CSV (parsed with the
  standard `csv` module; a bad number, a bad month, an unknown rack or a row of the wrong width is an error that names the line, exit
  code 2), the truth JSON of a synthetic data center, and a `report.json` or `bench.json` given to `render`.
- **What it writes:** only where the options say: `generate DIR` (it refuses to overwrite its files), `analyze --out`, `bench --out`,
  `render -o` and `--figure`.
- **The Docker image** runs as an unprivileged user and works with a read-only root filesystem (plus `--tmpfs /tmp` for matplotlib's
  cache), no capabilities and no network (`--network none`); see `tools/docker_e2e.sh`.
- **No real data** is in the repository: the data centers are synthetic. An inventory of your own can describe where your servers are
  and what they draw; analyse it locally, as the image is built to be run.

## Reporting

If you find a vulnerability, please open a private security advisory on the GitHub repository (Security tab) rather than a public
issue.
