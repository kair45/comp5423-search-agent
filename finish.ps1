param([string]$GroupFile,[string]$Chrome,[string]$FFmpeg='ffmpeg')
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$py=Join-Path $root '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $py)) {$py=(Get-Command python).Source}
$env:PYTHONUTF8='1'
function RunPy([string[]]$Argv) { & $py @Argv; if($LASTEXITCODE -ne 0){throw "Step failed: $($Argv[0])"} }
$main=Join-Path $root 'code/main.py'
$data=Join-Path $root 'data'
$out=[IO.Directory]::CreateDirectory((Join-Path $root 'deliverables')).FullName
$exp=Join-Path $root 'runs/holdout'
RunPy @($main,'batch',"$data/test.jsonl","$out/test_prediction.jsonl")
RunPy @($main,'verify',"$data/test.jsonl","$out/test_prediction.jsonl")
RunPy @($main,'experiment',"$data/validation/validation.jsonl",$exp,'--split','holdout')
$prefix=if($GroupFile){
    $GroupFile=(Resolve-Path -LiteralPath $GroupFile).Path
    $groupId=(Get-Content -Raw -Encoding utf8 -LiteralPath $GroupFile | ConvertFrom-Json).group
    if("$groupId" -notmatch '^[A-Za-z0-9-]+$'){throw 'Invalid group ID'}
    "Group-$groupId"
}else{'Project'}
if(!$Chrome){
    $Chrome=@('C:\Program Files\Google\Chrome\Application\chrome.exe','C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe') | Where-Object {Test-Path -LiteralPath $_} | Select-Object -First 1
}
if($FFmpeg -eq 'ffmpeg' -and !(Get-Command ffmpeg -ErrorAction SilentlyContinue)){
    $base=(& $py -c 'import sys; print(sys.base_prefix)').Trim()
    $condaFFmpeg=Join-Path $base 'Library/bin/ffmpeg.exe'
    if(Test-Path -LiteralPath $condaFFmpeg){$FFmpeg=$condaFFmpeg}
}
$port=8537
$pythonArgs=@('-m','streamlit','run',('"{0}"' -f (Join-Path $root 'code/app.py')),'--server.address','127.0.0.1','--server.port',"$port",'--server.headless','true','--browser.gatherUsageStats','false')
$server=Start-Process -FilePath $py -ArgumentList $pythonArgs -WorkingDirectory $root -PassThru -WindowStyle Hidden
try {
    $ready=$false
    foreach($i in 1..30){
        if($server.HasExited){throw 'New local UI server exited early'}
        try{$ready=(Invoke-WebRequest "http://127.0.0.1:$port/_stcore/health" -TimeoutSec 2).StatusCode -eq 200}catch{}
        if($ready){break}
        Start-Sleep -Seconds 1
    }
    if(!$ready){throw 'Local UI startup timed out'}
    $demo=@((Join-Path $root 'tools/demo_capture.py'),'--url',"http://127.0.0.1:$port",'--ffmpeg',$FFmpeg,'--predictions',"$exp/E.jsonl",'--output',"$out/$prefix-Video.mp4")
    if($Chrome){$demo+=@('--chrome',$Chrome)}
    RunPy $demo
} finally {if(!$server.HasExited){Stop-Process -Id $server.Id}}
$report=@((Join-Path $root 'tools/build_report.py'),'--metrics',"$exp/metrics.json",'--cases',"$exp/E.jsonl")
if($GroupFile){$report+=@('--group',$GroupFile,'--output',"$out/$prefix-Report.pdf")}
RunPy $report
if($GroupFile){RunPy @((Join-Path $root 'tools/package.py'),'--group',"$groupId")}
