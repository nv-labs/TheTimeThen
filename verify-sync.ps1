<#
.SYNOPSIS
    Verify and monitor synchronization between PC 1 and PC 2
    
.DESCRIPTION
    Checks:
    1. Database sync status (file sizes and modification times)
    2. Docker environment readiness
    3. Git repository status
    4. Configuration files
    
    Can run once or continuously with -Monitor parameter

.EXAMPLE
    .\verify-sync.ps1
    .\verify-sync.ps1 -Monitor
#>

param(
    [string]$OneDrivePath = "D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data",
    [string]$LocalPath = "D:\Dev\TheTimeThen",
    [switch]$Monitor
)

function Write-Status {
    param([string]$Message, [string]$Status = "Info")
    $timestamp = Get-Date -Format "HH:mm:ss"
    $symbols = @{ Info = "[i]"; Success = "[OK]"; Error = "[!!]"; Warning = "[!]"; Progress = "[..]"; Neutral = "[*]" }
    Write-Host "$timestamp $($symbols[$Status]) $Message" -ForegroundColor $(if ($Status -eq "Success") { "Green" } elseif ($Status -eq "Error") { "Red" } elseif ($Status -eq "Warning") { "Yellow" } else { "Cyan" })
}

function Format-Size {
    param([int64]$Bytes)
    if ($Bytes -lt 1MB) { return "$([math]::Round($Bytes/1KB, 1)) KB" }
    if ($Bytes -lt 1GB) { return "$([math]::Round($Bytes/1MB, 1)) MB" }
    return "$([math]::Round($Bytes/1GB, 2)) GB"
}

function Check-Databases {
    param([string]$DbPath)
    
    Write-Status "Checking database files..." "Progress"
    Write-Host ""
    
    $databases = @(
        @{ Name = "universal_image_archive.db"; Expected = 35.3 },
        @{ Name = "image_collection.db"; Expected = 1.7 },
        @{ Name = "google_takeout_photos_2023.db"; Expected = 3.9 }
    )
    
    $totalSize = 0
    $allGood = $true
    
    foreach ($db in $databases) {
        $dbFile = Join-Path $DbPath $db.Name
        
        if (Test-Path $dbFile) {
            $file = Get-Item $dbFile
            $size = $file.Length
            $sizeGb = [math]::Round($size / 1GB, 2)
            $expected = $db.Expected
            $percentComplete = [math]::Round(($sizeGb / $expected) * 100)
            
            $status = if ($percentComplete -ge 95) { "Success" } else { "Warning" }
            Write-Host "  $($db.Name): $sizeGb / $expected GB [$percentComplete%]" -ForegroundColor $(if ($status -eq "Success") { "Green" } else { "Yellow" })
            
            $totalSize += $size
            
            if ($percentComplete -lt 100) {
                $allGood = $false
            }
        } else {
            Write-Host "  $($db.Name): NOT FOUND" -ForegroundColor Red
            $allGood = $false
        }
    }
    
    Write-Host ""
    $totalGb = [math]::Round($totalSize / 1GB, 2)
    Write-Status "Total: $totalGb / 40.9 GB" $(if ($totalSize -ge (40.9 * 1GB * 0.95)) { "Success" } else { "Warning" })
    Write-Host ""
    
    return $allGood
}

function Check-Docker {
    param([string]$LocalPath)
    
    Write-Status "Checking Docker environment..." "Progress"
    Write-Host ""
    
    try {
        $version = & docker --version 2>&1
        Write-Status "Docker: $version" "Success"
    } catch {
        Write-Status "Docker not found or not running" "Error"
        return $false
    }
    
    if (Test-Path (Join-Path $LocalPath "docker-compose.yml")) {
        Write-Status "docker-compose.yml found" "Success"
    } else {
        Write-Status "docker-compose.yml not found" "Error"
        return $false
    }
    
    Write-Host ""
    return $true
}

function Check-Git {
    param([string]$LocalPath)
    
    Write-Status "Checking Git repository..." "Progress"
    Write-Host ""
    
    if (-not (Test-Path (Join-Path $LocalPath ".git"))) {
        Write-Status "Git repository not found" "Error"
        return $false
    }
    
    $currentLocation = Get-Location
    cd $LocalPath
    
    try {
        $branch = & git rev-parse --abbrev-ref HEAD 2>$null
        Write-Status "Current branch: $branch" "Success"
        
        $status = & git status --porcelain 2>$null
        if ($status) {
            Write-Status "Uncommitted changes found" "Warning"
        } else {
            Write-Status "All changes committed" "Success"
        }
        
        Write-Host ""
        return ($status.Count -eq 0)
    } finally {
        cd $currentLocation
    }
}

function Check-Environment {
    param([string]$LocalPath)
    
    Write-Status "Checking configuration..." "Progress"
    Write-Host ""
    
    $envPath = Join-Path $LocalPath ".env"
    if (Test-Path $envPath) {
        Write-Status ".env file exists" "Success"
    } else {
        Write-Status ".env file missing" "Error"
        return $false
    }
    
    Write-Host ""
    return $true
}

function Show-Summary {
    param([bool]$DbGood, [bool]$DockerGood, [bool]$GitGood, [bool]$EnvGood)
    
    Write-Host "============================================================"
    Write-Host "  SYNC STATUS SUMMARY"
    Write-Host "============================================================"
    Write-Host ""
    
    $checks = @(
        @{ Name = "Database Sync"; Status = $DbGood },
        @{ Name = "Docker Ready"; Status = $DockerGood },
        @{ Name = "Git Status"; Status = $GitGood },
        @{ Name = "Configuration"; Status = $EnvGood }
    )
    
    foreach ($check in $checks) {
        $symbol = if ($check.Status) { "[OK]" } else { "[!!]" }
        $color = if ($check.Status) { "Green" } else { "Red" }
        Write-Host "$symbol $($check.Name)" -ForegroundColor $color
    }
    
    Write-Host ""
    
    $allGood = $DbGood -and $DockerGood -and $GitGood -and $EnvGood
    if ($allGood) {
        Write-Host "SUCCESS: All systems ready for development!" -ForegroundColor Green
    } else {
        Write-Host "WARNING: Some items need attention (see above)" -ForegroundColor Yellow
    }
    
    Write-Host ""
}

function Main {
    Clear-Host
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "  TheTimeThen - Sync Verification & Monitoring"
    Write-Host "  Real-time synchronization status"
    Write-Host "============================================================"
    Write-Host ""
    
    # Verify paths exist
    if (-not (Test-Path $OneDrivePath)) {
        Write-Status "OneDrive path not accessible" "Error"
        exit 1
    }
    
    if (-not (Test-Path $LocalPath)) {
        Write-Status "Local path not found" "Error"
        exit 1
    }
    
    Write-Status "Paths verified" "Success"
    Write-Host ""
    
    $iteration = 0
    
    while ($true) {
        if ($iteration -gt 0) {
            Clear-Host
            Write-Host ""
            Write-Host "============================================================"
            Write-Host "  TheTimeThen - Sync Verification & Monitoring"
            Write-Host "  Real-time synchronization status"
            Write-Host "============================================================"
            Write-Host ""
        }
        
        $iteration++
        
        $dbGood = Check-Databases -DbPath (Join-Path $OneDrivePath "databases")
        $dockerGood = Check-Docker -LocalPath $LocalPath
        $gitGood = Check-Git -LocalPath $LocalPath
        $envGood = Check-Environment -LocalPath $LocalPath
        
        Show-Summary -DbGood $dbGood -DockerGood $dockerGood -GitGood $gitGood -EnvGood $envGood
        
        if (-not $Monitor) {
            break
        }
        
        Write-Host "Monitoring mode - updates every 60 seconds (Press Ctrl+C to stop)"
        Write-Host ""
        
        Start-Sleep -Seconds 60
    }
}

try {
    Main
} catch {
    Write-Status "ERROR: $_" "Error"
    exit 1
}
