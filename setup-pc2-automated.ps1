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
Write-Host "  TheTimeThen PC2 Setup"
Write-Host "============================================================"
Write-Host ""

if (-not (Test-Path $ProjectPath)) { throw "Project path not found: $ProjectPath" }
$dbDir = Join-Path $OneDrivePath "databases"
if (-not (Test-Path $dbDir)) { throw "Database folder not found: $dbDir" }

$totalExpected = 0
foreach ($name in $DbFiles) {
    $local = Join-Path $ProjectPath $name
    if (-not (Test-Path $local)) { throw "Missing local reference file: $local" }
    $totalExpected += (Get-Item $local).Length
}

Write-Status "Watching only the 3 DB files: $(Format-Size $totalExpected)" "INFO"

$start = Get-Date
$lastMinute = -1

while ($true) {
    $current = 0
    $found = 0

    foreach ($name in $DbFiles) {
        $f = Join-Path $dbDir $name
        if (Test-Path $f) {
            $found++
            $current += (Get-Item $f).Length
        }
    }

    $minute = [math]::Floor(((Get-Date) - $start).TotalSeconds / 60)
    if ($minute -ne $lastMinute) {
        $lastMinute = $minute
        $label = "Found $found/3 DB files; $(Format-Size $current)/$(Format-Size $totalExpected)"
        Show-Progress -Current $current -Total $totalExpected -Label $label -StartTime $start
        Write-Host ""
    }

    if ($found -eq 3 -and $current -ge ($totalExpected * 0.99)) {
        Write-Host ""
        Write-Status "All 3 DB files are synced." "OK"
        break
    }

    Start-Sleep -Seconds 60
}

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
Write-Status "PC2 done." "OK"