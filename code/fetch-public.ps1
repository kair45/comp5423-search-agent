param([string]$Data = (Join-Path $PSScriptRoot '..\data'))
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = [IO.Directory]::CreateDirectory($Data).FullName
$specs = @(
    @('datasets','HongruCai/COMP5423-BrowseComp-Plus-Test','','.','^test\.jsonl$'),
    @('datasets','HongruCai/COMP5423-BrowseComp-Plus-Val','','validation','^validation\.jsonl$'),
    @('datasets','Tevatron/browsecomp-plus-corpus','data','corpus','\.parquet$'),
    @('models','intfloat/multilingual-e5-small','','models/e5','^(config\.json|model\.safetensors|tokenizer\.json|tokenizer_config\.json|special_tokens_map\.json|sentencepiece\.bpe\.model)$'),
    @('models','Qwen/Qwen3-Embedding-0.6B','','models/qwen','^(config\.json|model\.safetensors|tokenizer\.json|tokenizer_config\.json|merges\.txt|vocab\.json)$'),
    @('datasets','Tevatron/browsecomp-plus-indexes','qwen3-embedding-0.6b','qwen-index','\.pkl$')
)
$jobs = foreach ($spec in $specs) {
    $kind,$repo,$sub,$local,$pattern = $spec
    $revision = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'public-revisions.json') -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable)[$repo]
    $treeUrl = "https://huggingface.co/api/$kind/$repo/tree/$revision"
    if ($sub) { $treeUrl += "/$sub" }
    $items = Invoke-RestMethod $treeUrl
    foreach ($item in $items) {
        $name = [IO.Path]::GetFileName($item.path)
        if ($name -notmatch $pattern -or $item.type -ne 'file') { continue }
        $prefix = if ($kind -eq 'datasets') {'datasets/'} else {''}
        [PSCustomObject]@{url="https://huggingface.co/$prefix$repo/resolve/$revision/$($item.path)"; path="$root/$local/$name"; bytes=$item.size; sha256=$item.lfs.oid; repo=$repo; revision=$revision}
    }
}
$jobs | ConvertTo-Json | Set-Content -Encoding utf8 "$root/public-manifest.json"
$jobs | ForEach-Object -Parallel {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    $j = $_
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($j.path)) | Out-Null
    if ((Test-Path -LiteralPath $j.path) -and (Get-Item -LiteralPath $j.path).Length -eq $j.bytes) {
        if (!$j.sha256 -or (Get-FileHash -LiteralPath $j.path).Hash -eq $j.sha256) { return }
    }
    for ($n=0; $n -lt 3; $n++) {
        try {
            Invoke-WebRequest -Uri $j.url -OutFile ($j.path+'.part') -TimeoutSec 900
            if ((Get-Item -LiteralPath ($j.path+'.part')).Length -ne $j.bytes) { throw 'Download size mismatch' }
            if ($j.sha256 -and (Get-FileHash -LiteralPath ($j.path+'.part')).Hash -ne $j.sha256) { throw 'Download checksum mismatch' }
            Move-Item -Force -LiteralPath ($j.path+'.part') -Destination $j.path
            Write-Output ([IO.Path]::GetFileName($j.path))
            break
        } catch { if ($n -eq 2) { throw }; Start-Sleep -Seconds 2 }
    }
} -ThrottleLimit 4
foreach ($j in $jobs) { if (!(Test-Path -LiteralPath $j.path) -or (Get-Item -LiteralPath $j.path).Length -ne $j.bytes) { throw "Incomplete download: $($j.path)" } }
