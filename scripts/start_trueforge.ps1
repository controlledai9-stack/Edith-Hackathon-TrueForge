$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeDirectory = Join-Path $ProjectRoot "trueforge"

if (-not (Test-Path -LiteralPath (Join-Path $RuntimeDirectory "node_modules"))) {
    throw "TrueForge dependencies are missing. Run npm install inside $RuntimeDirectory first."
}

Push-Location $RuntimeDirectory
try {
    npm start
}
finally {
    Pop-Location
}
