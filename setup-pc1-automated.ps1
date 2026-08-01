$ErrorActionPreference = "Stop"

$ProjectPath = $PSScriptRoot
$OneDrivePath = "D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data"
$DbFiles = @(
    "universal_image_archive.db",
    "image_collection.db",
    "google_takeout_photos_2023.db"
)

function Write-Status {
    param([string]$Message, [string]$Level = "INFO")
    $t = Get-Date -Format "HH:mm:ss"
    Write-Host "$t [$Level] $Message"
}

function Format-Size {
    param([Int64]$Bytes)
    if ($Bytes -ge 1GB) { return "{0:N1} GB" -f ($Bytes / 1GB) }
    if ($Bytes -ge 1MB) { return "{0:N1} MB" -f ($Bytes / 1MB) }
    return "$Bytes B"
}

function Show-Progress {
    param([Int64]$Current, [Int64]$Total, [string]$Label, [datetime]$StartTime)
    if ($Total -le 0) { $Total = 1 }
    $pct = [math]::Floor(($Current / $Total) * 100)
    if ($pct -gt 100) { $pct = 100 }
    $width = 30
    $filled = [math]::Floor(($pct / 100) * $width)
    $bar = "[" + ("#" * $filled) + ("-" * ($width - $filled)) + "]"
    $elapsed = (Get-Date) - $StartTime
    $secs = [math]::Max(1, [int]$elapsed.TotalSeconds)
    $speed = $Current / 1MB / $secs
    Write-Host -NoNewline "`r$bar $pct% - $Label ($([math]::Round($speed,1)) MB/s)     "
}

Write-Host ""
Write-Host "============================================================"
Write-Host "  TheTimeThen PC1 Setup"
Write-Host "============================================================"
Write-Host ""

$dbSource = @()
foreach ($f in $DbFiles) {
    $p = Join-Path $ProjectPath $f
    if (-not (Test-Path $p)) { throw "Missing database file: $p" }
    $dbSource += $p
}

$dbDest = Join-Path $OneDrivePath "databases"
$dataDir = Join-Path $OneDrivePath "data"
$outputDir = Join-Path $OneDrivePath "output"

foreach ($d in @($OneDrivePath, $dbDest, $dataDir, $outputDir)) {
    if (-not (Test-Path $d)) {
        New-Item -Path $d -ItemType Directory -Force | Out-Null
    }
}

$totalBytes = 0
foreach ($f in $dbSource) { $totalBytes += (Get-Item $f).Length }

Write-Status "Copying only 3 DB files: $(Format-Size $totalBytes)" "INFO"
$done = 0

foreach ($src in $dbSource) {
    $name = Split-Path $src -Leaf
    $dest = Join-Path $dbDest $name
    $size = (Get-Item $src).Length
    $start = Get-Date

    $in = [System.IO.File]::OpenRead($src)
    $out = [System.IO.File]::Open($dest, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try {
        $buffer = New-Object byte[] (4MB)
        while (($read = $in.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $out.Write($buffer, 0, $read)
            $done += $read
            Show-Progress -Current $done -Total $totalBytes -Label $name -StartTime $start
        }
    } finally {
        $in.Dispose()
        $out.Dispose()
    }
    Write-Host ""
    Write-Status "Copied $name" "OK"
}

Write-Host ""
Write-Status "All 3 DB files copied. Wait for OneDrive to sync." "OK"

$envExample = Join-Path $ProjectPath ".env.example"
$envFile = Join-Path $ProjectPath ".env"
if (Test-Path $envExample) {
    Copy-Item $envExample $envFile -Force
    $content = Get-Content $envFile
    $content = $content -replace 'D:/Nvisions OneDrive/OneDrive/TheTimeThen-Data', ($OneDrivePath -replace '\\','/')
    Set-Content $envFile $content
    Write-Status ".env created" "OK"
}

Write-Host ""
Write-Status "PC1 done." "OK"