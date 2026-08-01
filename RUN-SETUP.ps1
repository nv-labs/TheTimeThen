# ╔════════════════════════════════════════════════════════════════════════════╗
# ║                                                                            ║
# ║     TheTimeThen - Automated Multi-Computer Setup                          ║
# ║     Run this script to automate your setup on both PCs                    ║
# ║                                                                            ║
# ╚════════════════════════════════════════════════════════════════════════════╝

## QUICK START GUIDE

Write-Host @"

╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║   TheTimeThen - Automated Setup for Multi-Computer Development            ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝

🚀 WHAT YOU HAVE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✅ setup-pc1-automated.ps1  → Automates PC 1 setup (copy 42GB to OneDrive)
  ✅ setup-pc2-automated.ps1  → Automates PC 2 setup (download from GitHub)
  ✅ verify-sync.ps1          → Monitors synchronization status

📋 TIMELINE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Phase 1 (PC 1):   60-90 minutes (mostly waiting for OneDrive upload)
  Phase 2 (PC 2):   50-80 minutes (mostly waiting for OneDrive download)
  Phase 3 (Verify): 5 minutes
  ─────────────────────────────────
  Total:            ~2-2.5 hours

⚡ KEY FEATURES IN THESE SCRIPTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✨ Real-time progress bars (% complete)
  ✨ Updates every 60 seconds
  ✨ Shows upload/download speed
  ✨ Monitors OneDrive sync status
  ✨ Automatic Docker build
  ✨ Git initialization & commits
  ✨ Comprehensive error checking
  ✨ Color-coded status messages

📋 STEP-BY-STEP PROCESS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PHASE 1 - PC 1 (This PC):
────────────────────────────────────────────────────────────────────────────
  1. Creates OneDrive folder structure (5 min)
  2. Copies 42GB databases to OneDrive (15 min copy + upload in background)
  3. WAITS for OneDrive sync (most time - 10-30 min) ⏳
  4. Creates .env configuration file (1 min)
  5. Initializes Git repository (1 min)
  6. Builds Docker image (10 min)
  7. Pushes to GitHub (you'll do manually) ✋

PHASE 2 - PC 2 (Other PC):
────────────────────────────────────────────────────────────────────────────
  1. Clones code from GitHub (2 min)
  2. Creates .env configuration (1 min)
  3. WAITS for OneDrive to download 42GB (most time - 20-40 min) ⏳
  4. Verifies database files (1 min)
  5. Builds Docker image (10 min)

PHASE 3 - Verification (Both PCs):
────────────────────────────────────────────────────────────────────────────
  Run: verify-sync.ps1 (shows real-time sync status)
  Or:  verify-sync.ps1 -Monitor (continuous monitoring)

🎯 PREREQUISITES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ☑️  Docker Desktop installed on BOTH PCs
  ☑️  Git installed on BOTH PCs
  ☑️  OneDrive installed and running
  ☑️  GitHub account ready
  ☑️  Run PowerShell as Administrator

❌ COMMON ISSUES & FIXES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Issue:   "Permission denied" or "Access is denied"
  Fix:    Right-click PowerShell → Run as Administrator

  Issue:   "docker: command not found"
  Fix:    Install Docker Desktop
          Add Docker to your PATH
          Restart PowerShell

  Issue:   "OneDrive path not accessible"
  Fix:    Check OneDrive is running
          Wait for sync to complete on PC 1 before starting PC 2
          Verify path: D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data

  Issue:   "Git repository not found"
  Fix:    Make sure PC 1 pushed to GitHub
          Check GitHub repo is public or you have access

💡 PROGRESS MONITORING:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Progress Bar Example:
    [████████████░░░░░░░░░░░░░░░░] 45% - Downloaded: 18.2/40.9 GB at 12.5 MB/s

  What to watch:
    ✨ Green checkmarks ✅ in File Explorer = files synced
    ✨ Progress percentage increasing = working
    ✨ Download/upload speed > 0 MB/s = transferring data

⚠️  IMPORTANT TIMING:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  🔴 DO NOT start PC 2 until PC 1 completes OneDrive sync
  🔴 DO NOT close PowerShell during setup
  🔴 DO NOT unplug ethernet/disconnect WiFi during sync
  🔴 DO NOT minimize OneDrive window during sync

✅ YOUR NEXT STEP:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Press Enter to start PC 1 setup now!

" -ForegroundColor Cyan

Read-Host "Ready to start? (Press Enter to continue, Ctrl+C to cancel)"

Write-Host ""
Write-Host "Starting PC 1 automated setup..." -ForegroundColor Green
Write-Host ""

# Run the PC 1 setup
& "D:\Dev\TheTimeThen\setup-pc1-automated.ps1"
