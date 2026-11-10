#!/usr/bin/env bash
# End to end inside the image (read-only root, no capabilities, no network): a synthetic data center and its truth are written to a
# volume, validated, analysed and scored, the report is rebuilt from its JSON, a what-if is planned, the two implementations are
# compared, and the benchmark runs small. Needs Docker. Usage: tools/docker_e2e.sh [image]
set -euo pipefail
IMAGE="${1:-dccap}"
VOL="dccap-e2e-$$"
TMP="$(mktemp -d)"
trap 'docker volume rm -f "$VOL" >/dev/null 2>&1 || true; rm -rf "$TMP"' EXIT

[ "$(docker run --rm --entrypoint id "$IMAGE" -u)" != 0 ]   # not root
docker volume create "$VOL" >/dev/null
docker run --rm --user 0 -v "$VOL":/data --entrypoint chown "$IMAGE" 10001 /data

RUN=(docker run --rm --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --network none -v "$VOL":/data "$IMAGE")
cat_file() { docker run --rm --entrypoint cat -v "$VOL":/data "$IMAGE" "$1" > "$2"; }

out="$("${RUN[@]}" generate /data/dc --months 36 --future 24 --seed 4)"
grep -q 'written: /data/dc/facility.json, /data/dc/inventory.csv, /data/dc/truth.json' <<<"$out"
out="$("${RUN[@]}" validate /data/dc/facility.json /data/dc/inventory.csv)"
grep -q '^ok: 24 racks (1,008 U) from 2020-01; ' <<<"$out"

out="$("${RUN[@]}" analyze /data/dc/facility.json /data/dc/inventory.csv --truth /data/dc/truth.json --out /data/out)"
grep -q '^/data/dc/inventory.csv: 24 racks, 1,008 U; ' <<<"$out"
grep -q '^what happened next (months to the limit): ' <<<"$out"
cat_file /data/out/report.json "$TMP/report.json"
grep -q '"kind": "report"' "$TMP/report.json"
cat_file /data/out/report.md "$TMP/report.md"
"${RUN[@]}" render /data/out/report.json -o /data/out/again.md >/dev/null
cat_file /data/out/again.md "$TMP/again.md"
cmp "$TMP/again.md" "$TMP/report.md"                              # the report is rebuilt exactly from the JSON
cat_file /data/out/summary.png "$TMP/summary.png"
[ "$(head -c 4 "$TMP/summary.png" | tail -c 3)" = "PNG" ]

out="$("${RUN[@]}" plan /data/dc/facility.json /data/dc/inventory.csv --add srv-1u=5)"
grep -q '^add 5 x srv-1u: 5 placed' <<<"$out"

out="$("${RUN[@]}" analyze)"                                      # the demo data center, built inside the container
grep -q '^demo data center (synthetic, 60 months, seed 1): 24 racks, 1,008 U; ' <<<"$out"

out="$("${RUN[@]}" verify --draws 5)"
grep -q '^6 of 6 comparisons agree with the literal implementation' <<<"$out"

"${RUN[@]}" bench --sizes 300,600 --repeat 1 --draws 3 --ref-devices 200 --seeds 2 --out /data/bench >/dev/null
cat_file /data/bench/bench.json "$TMP/bench.json"
grep -q '"ok": true' "$TMP/bench.json"

set +e; "${RUN[@]}" validate /data/nope.json /data/nope.csv >/dev/null 2>&1; rc=$?; set -e   # a missing file is exit code 2
[ "$rc" = 2 ]
echo "docker end-to-end: OK"
