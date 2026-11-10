# End to end inside the image, from Windows PowerShell: a synthetic data center and its truth are written to a volume,
# validated, analysed and scored, the report is rebuilt from its JSON, a what-if is planned, the two implementations are compared and the
# benchmark runs small
# (read-only root, no capabilities, no network). Needs Docker Desktop.
# Usage: .\tools\docker_e2e.ps1 [-Image dccap]
param([string]$Image = "dccap")
$ErrorActionPreference = "Stop"

$id = Get-Random
$vol = "dccap-e2e-$id"
$secure = @("--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--network", "none", "-v", "${vol}:/data")

# Windows PowerShell 5.1 turns a program's message on stderr into an error under "Stop": the commands that are expected to
# fail run with errors not terminating, and only their exit code is looked at.
function Invoke-DccapCode([int[]]$Allowed, [string[]]$DccapArgs) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = docker run --rm @secure $Image @DccapArgs 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    if ($Allowed -notcontains $code) { throw "dccap $DccapArgs exited with $code : $out" }
    ($out | Out-String)
}
function Invoke-Dccap([string[]]$DccapArgs) { Invoke-DccapCode @(0) $DccapArgs }
function Read-Volume($path) {
    $out = docker run --rm --entrypoint cat -v "${vol}:/data" $Image $path 2>$null
    if ($LASTEXITCODE -ne 0) { throw "cannot read $path" }
    ($out | Out-String)
}
function Assert-Contains($text, $needle) { if ($text -notmatch [regex]::Escape($needle)) { throw "expected '$needle' in: $text" } }

try {
    docker volume create $vol | Out-Null
    docker run --rm --user 0 -v "${vol}:/data" --entrypoint chown $Image 10001 /data
    if ($LASTEXITCODE -ne 0) { throw "could not prepare the volume" }

    Assert-Contains (Invoke-Dccap @("generate", "/data/dc", "--months", "36", "--future", "24", "--seed", "4")) "written: /data/dc/facility.json"
    Assert-Contains (Invoke-Dccap @("validate", "/data/dc/facility.json", "/data/dc/inventory.csv")) "ok: 24 racks (1,008 U) from 2020-01; "

    $run = Invoke-Dccap @("analyze", "/data/dc/facility.json", "/data/dc/inventory.csv", "--truth", "/data/dc/truth.json", "--out", "/data/out")
    Assert-Contains $run "/data/dc/inventory.csv: 24 racks, 1,008 U; "
    Assert-Contains $run "what happened next (months to the limit): "
    $md = Read-Volume "/data/out/report.md"
    Invoke-Dccap @("render", "/data/out/report.json", "-o", "/data/out/again.md") | Out-Null
    if ((Read-Volume "/data/out/again.md") -ne $md) { throw "the report rebuilt from the JSON is not identical" }

    Assert-Contains (Invoke-Dccap @("plan", "/data/dc/facility.json", "/data/dc/inventory.csv", "--add", "srv-1u=5")) "add 5 x srv-1u: 5 placed"
    Assert-Contains (Invoke-Dccap @("analyze")) "demo data center (synthetic, 60 months, seed 1): 24 racks, 1,008 U; "
    Assert-Contains (Invoke-Dccap @("verify", "--draws", "5")) "6 of 6 comparisons agree with the literal implementation"

    Invoke-Dccap @("bench", "--sizes", "300,600", "--repeat", "1", "--draws", "3", "--ref-devices", "200", "--seeds", "2", "--out", "/data/bench") | Out-Null
    Assert-Contains (Read-Volume "/data/bench/bench.json") '"ok": true'

    Invoke-DccapCode @(2) @("validate", "/data/nope.json", "/data/nope.csv") | Out-Null
    Write-Host "docker end-to-end: OK"
}
finally {
    $ErrorActionPreference = "Continue"
    docker volume rm -f $vol 2>&1 | Out-Null
}
