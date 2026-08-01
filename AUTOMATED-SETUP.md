# 🚀 TheTimeThen - Automated Multi-PC Setup - INDEX

## What's New

You now have **3 powerful automation scripts** that handle 95% of the setup work for you, with **real-time progress monitoring**!

---

## Files Created

### 🎯 Main Scripts (Ready to Run)

| Script | Purpose | Time | Progress |
|--------|---------|------|----------|
| **setup-pc1-automated.ps1** | Initialize PC 1 (copy 40.9GB to OneDrive) | 60-90 min | Real-time bar + 60sec updates |
| **setup-pc2-automated.ps1** | Initialize PC 2 (clone from GitHub) | 50-80 min | Real-time bar + 60sec updates |
| **verify-sync.ps1** | Check synchronization status | 2-3 sec | One-time or continuous |

### 📖 Documentation

| File | Contains |
|------|----------|
| **AUTOMATED-SETUP-GUIDE.md** | Complete step-by-step walkthrough with examples |
| **SETUP-CHECKLIST.md** | Quick checklist for each phase |
| **AUTOMATED-SETUP.md** | This index file |

### 📁 Location

All files: `D:\Dev\TheTimeThen\`

---

## Quick Start (5 Minutes to Begin)

```powershell
# 1. Open the guide
notepad D:\Dev\TheTimeThen\AUTOMATED-SETUP-GUIDE.md

# 2. Read: "Step-by-Step Execution" section (takes 2 min)

# 3. Run this on PC 1:
cd D:\Dev\TheTimeThen
.\setup-pc1-automated.ps1

# 4. Watch the progress bars!
```

---

## What You'll See

### Example Progress During Copy:

```
[##########--------] 52% - Copied: 21.2/40.9 GB (65 MB/s)
[##############----] 68% - Copied: 27.8/40.9 GB (62 MB/s)
[##################] 100% - Copy complete!
```

### Example Progress During Sync:

```
[#########---------] 50% - Syncing... (check OneDrive)
[##########--------] 60% - Syncing... (check OneDrive)
[####################] 100% - OneDrive sync complete!
```

---

## Timeline

```
Phase 1 - PC 1 Setup:     60-90 minutes
Phase 2 - PC 2 Setup:     50-80 minutes  (run after PC 1 done)
Phase 3 - Verification:   2-3 minutes
────────────────────────────────────────
TOTAL:                    ~2-2.5 hours
```

---

## Key Features

✅ **Real-time progress bars** - Shows `%`, bytes transferred, speed (MB/s)
✅ **60-second updates** - During sync phases
✅ **Time stamped messages** - Know when each step happened
✅ **Color-coded output** - Green ([OK]), Red ([!!]), Yellow ([!])
✅ **Automatic Docker builds** - No manual commands needed
✅ **Git initialization** - Repo ready to push to GitHub
✅ **OneDrive monitoring** - Shows sync status and files ready
✅ **Error handling** - Catches and explains issues

---

## The 3-Phase Process

### PHASE 1: PC 1 Setup (First PC - 60-90 min)

1. Run: `.\setup-pc1-automated.ps1`
2. Watch progress bars
3. Script copies 40.9GB to OneDrive
4. Script waits for OneDrive sync (with progress updates)
5. Script creates .env, Git repo, Docker image
6. When done: Push to GitHub (manually)

### PHASE 2: PC 2 Setup (Second PC - 50-80 min)

1. Run: `.\setup-pc2-automated.ps1 -GitHubRepo <URL>`
2. Script clones from GitHub
3. Script creates .env file
4. Script waits for OneDrive download (with progress updates)
5. Script verifies all 3 databases exist
6. Script builds Docker image

### PHASE 3: Verification (Both PCs - 2-3 min)

1. Run: `.\verify-sync.ps1`
2. Shows all databases synced
3. Verifies Docker ready
4. Checks Git status
5. Confirms configuration OK

---

## Where to Start

1. **First time?** Read this: `AUTOMATED-SETUP-GUIDE.md`
   - 15 minute read
   - Complete walkthrough
   - Troubleshooting included

2. **Prefer a checklist?** Use: `SETUP-CHECKLIST.md`
   - Boxes to check off
   - Quick reference
   - Success criteria

3. **Ready to begin?** Run: `.\setup-pc1-automated.ps1`
   - Watch the progress bars
   - Total time: 60-90 minutes
   - Most time is waiting for files to transfer

---

## Important Before You Start

- [ ] Docker Desktop installed
- [ ] Git installed
- [ ] OneDrive running
- [ ] 50+ GB free disk space (local + OneDrive)
- [ ] Stable internet connection
- [ ] GitHub account ready

---

## What Each Script Does

### setup-pc1-automated.ps1

**Runs PHASE 1 setup on PC 1**

```
1. Verify all required files exist
2. Create OneDrive folder structure
3. Copy 40.9GB databases to OneDrive
   └─ Shows real-time progress bar
4. Wait for OneDrive to sync
   └─ Progress updates every 60 seconds
5. Create .env configuration
6. Initialize Git repository
7. Build Docker image
```

**How to run:**
```powershell
.\setup-pc1-automated.ps1
```

**Parameters:**
```powershell
# With custom OneDrive path:
.\setup-pc1-automated.ps1 -OneDrivePath "D:\Your\Path"
```

---

### setup-pc2-automated.ps1

**Runs PHASE 2 setup on PC 2**

```
1. Clone code from GitHub
2. Create .env configuration
3. Wait for OneDrive to download 40.9GB
   └─ Progress updates every 60 seconds
4. Verify all 3 database files exist
5. Build Docker image
```

**How to run:**
```powershell
# With repo URL:
.\setup-pc2-automated.ps1 -GitHubRepo "https://github.com/user/repo.git"

# Or let it ask you:
.\setup-pc2-automated.ps1
```

---

### verify-sync.ps1

**Checks synchronization status**

```
1. Check database file sizes
2. Verify Docker installed and ready
3. Check Git repository status
4. Verify configuration files
5. Show overall status
```

**How to run:**
```powershell
# One-time check:
.\verify-sync.ps1

# Continuous monitoring (updates every 60 sec):
.\verify-sync.ps1 -Monitor

# With custom paths:
.\verify-sync.ps1 -OneDrivePath "D:\Your\Path" -LocalPath "D:\Dev"
```

---

## Progress Examples

### During Database Copy:

```
11:17:36 [..] Copying universal_image_archive.db...
[-----] 2% - Copied: 0.8/40.9 GB (5 MB/s)
[#-----] 5% - Copied: 2.0/40.9 GB (45 MB/s)
[##----] 15% - Copied: 6.1/40.9 GB (68 MB/s)
[####--] 35% - Copied: 14.3/40.9 GB (65 MB/s)
[######] 100% - Copy complete!
```

### During OneDrive Sync:

```
11:18:42 [..] Waiting for OneDrive to sync...
[#-----] 15% - Syncing... (check OneDrive)
[###---] 35% - Syncing... (check OneDrive)
[#####-] 65% - Syncing... (check OneDrive)
[######] 100% - OneDrive sync complete!
```

### During Docker Build:

```
11:45:22 [..] Building Docker image...
[Docker output - full build log shown]
11:47:15 [OK] Docker image built successfully
```

### After Everything:

```
============================================================
  [OK] PC 1 SETUP COMPLETE!
============================================================

Next Steps:
1. Verify OneDrive sync completed (green checkmarks)
2. Push to GitHub:
   cd D:\Dev\TheTimeThen
   git remote add origin <YOUR_REPO_URL>
   git push -u origin main
3. On PC 2, run: .\setup-pc2-automated.ps1 -GitHubRepo <URL>
```

---

## Troubleshooting Quick Links

| Issue | Solution |
|-------|----------|
| "Permission denied" | Run PowerShell as Administrator |
| "Docker: command not found" | Install Docker Desktop |
| "OneDrive path not accessible" | Verify path exists, start OneDrive |
| "Git repository not found" | Ensure PC 1 pushed to GitHub first |
| Progress stuck at 0% | Wait 1-2 min, check internet connection |

For more help, see: `AUTOMATED-SETUP-GUIDE.md` → Troubleshooting section

---

## Success Checklist

### PC 1 Complete:
- [ ] Script shows "[OK] PC 1 SETUP COMPLETE!"
- [ ] OneDrive shows green checkmarks for all 3 databases
- [ ] Successfully pushed to GitHub
- [ ] Git shows "creating branch main..."

### PC 2 Complete:
- [ ] Script shows "[OK] PC 2 SETUP COMPLETE!"
- [ ] OneDrive shows green checkmarks for all 3 databases
- [ ] `verify-sync.ps1` shows "SUCCESS: All systems ready!"

### Full Setup Complete:
- [ ] Both PCs have identical code (via git)
- [ ] Both PCs see same databases (via OneDrive)
- [ ] Both PCs have identical Docker environment
- [ ] `verify-sync.ps1 -Monitor` shows all systems OK

---

## After Setup

Once both PCs are done:

```powershell
# Start Docker on both PCs:
docker-compose up -d

# Verify containers running:
docker-compose ps

# Test database access:
docker-compose exec timethen python check_db.py

# Monitor continuously:
.\verify-sync.ps1 -Monitor
```

---

## Questions?

All scripts have built-in help:

```powershell
Get-Help .\setup-pc1-automated.ps1 -Full
Get-Help .\setup-pc2-automated.ps1 -Full
Get-Help .\verify-sync.ps1 -Full
```

---

## Ready?

1. **Read:** `AUTOMATED-SETUP-GUIDE.md` (15 min)
2. **Run:** `.\setup-pc1-automated.ps1` (60-90 min)
3. **Watch:** Progress bars update in real-time!
4. **Push:** To GitHub (manually)
5. **Repeat:** Steps 2-4 on PC 2

---

## Key Reminders

⚠️ Don't close PowerShell during setup
⚠️ Don't disconnect internet while syncing
⚠️ Wait for green checkmarks before starting PC 2
⚠️ Push to GitHub on PC 1 before starting PC 2
⚠️ Watch the progress bars - they tell you everything!

---

## Start Now!

```powershell
cd D:\Dev\TheTimeThen
.\setup-pc1-automated.ps1
```

Good luck! 🚀
