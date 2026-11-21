param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot
$exe=Join-Path $root '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $exe)) { $exe=(Get-Command python).Source }
$env:PYTHONUTF8='1'
if ($Arguments.Count -and $Arguments[0] -eq 'ui') {
    & $exe -m streamlit run (Join-Path $PSScriptRoot 'app.py') --server.address 127.0.0.1 --browser.gatherUsageStats false
} else {
    & $exe (Join-Path $PSScriptRoot 'main.py') @Arguments
}
exit $LASTEXITCODE
