# AUTOMATED SETUP - QUICK CHECKLIST

## Files Created for You

✅ **setup-pc1-automated.ps1** (8.8 KB)
   - Automates PC 1 setup
   - Copies 40.9GB databases to OneDrive
   - Shows real-time progress bar (updates every second)
   - Monitors OneDrive sync (updates every 60 seconds)
   - Time: 60-90 minutes
   - **Location:** D:\Dev\TheTimeThen\setup-pc1-automated.ps1

✅ **setup-pc2-automated.ps1** (8.3 KB)
   - Automates PC 2 setup
   - Clones code from GitHub
   - Waits for OneDrive download
   - Shows real-time progress bar (updates every second)
   - Time: 50-80 minutes
   - **Location:** D:\Dev\TheTimeThen\setup-pc2-automated.ps1

✅ **verify-sync.ps1** (7.9 KB)
   - Verifies synchronization status
   - Checks all databases synced
   - Verifies Docker, Git, configuration
   - Can run once or continuously (-Monitor)
   - Time: 2-3 seconds
   - **Location:** D:\Dev\TheTimeThen\verify-sync.ps1

✅ **AUTOMATED-SETUP-GUIDE.md** (11.7 KB)
   - Complete step-by-step guide
   - What to expect and when
   - Example progress output
   - Troubleshooting section
   - **Location:** D:\Dev\TheTimeThen\AUTOMATED-SETUP-GUIDE.md

---

## Pre-Execution Checklist

Before running setup-pc1-automated.ps1, verify:

- [ ] Docker Desktop is installed
- [ ] Git is installed and configured
- [ ] OneDrive is running and synchronized
- [ ] You have 50+ GB free disk space on local drive
- [ ] You have 50+ GB free space on OneDrive
- [ ] Internet connection is stable
- [ ] GitHub account created (for pushing code)

---

## PC 1 Setup Checklist

### Before Starting
- [ ] cd D:\Dev\TheTimeThen
- [ ] Read AUTOMATED-SETUP-GUIDE.md (take 5 minutes)
- [ ] Verify all prerequisites above

### Running Setup
- [ ] Run: `.\setup-pc1-automated.ps1`
- [ ] Watch progress bars for the entire duration
- [ ] DO NOT close PowerShell window
- [ ] DO NOT disconnect internet
- [ ] Note the time it completes

### After Setup
- [ ] Script shows "[OK] PC 1 SETUP COMPLETE!"
- [ ] Check OneDrive in File Explorer:
  - [ ] `D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data\databases\`
  - [ ] universal_image_archive.db shows ✅ green checkmark
  - [ ] image_collection.db shows ✅ green checkmark
  - [ ] google_takeout_photos_2023.db shows ✅ green checkmark
- [ ] Push to GitHub:
  ```powershell
  cd D:\Dev\TheTimeThen
  git remote add origin <YOUR_REPO_URL>
  git push -u origin main
  ```
- [ ] Verify "Creating branch main..." message
- [ ] GitHub repo now has your code

---

## PC 2 Setup Checklist

### Prerequisites (Only after PC 1 complete!)
- [ ] PC 1 setup completely finished
- [ ] OneDrive shows green checkmarks for all 3 databases
- [ ] You successfully pushed to GitHub
- [ ] You have the GitHub repo URL

### Before Starting
- [ ] Docker Desktop is installed
- [ ] Git is installed
- [ ] OneDrive is running
- [ ] You have 50+ GB free disk space
- [ ] Internet connection is stable

### Running Setup
- [ ] Run: `.\setup-pc2-automated.ps1 -GitHubRepo <YOUR_REPO_URL>`
  Or without parameters and enter URL when prompted
- [ ] Watch progress bars for the entire duration
- [ ] DO NOT close PowerShell window
- [ ] DO NOT disconnect internet
- [ ] Note the time it completes

### After Setup
- [ ] Script shows "[OK] PC 2 SETUP COMPLETE!"
- [ ] Check OneDrive in File Explorer:
  - [ ] All 3 database files show ✅ green checkmarks
  - [ ] Files sizes match PC 1 (35.3GB + 1.7GB + 3.9GB)

---

## Verification Checklist

### Run After Both PCs Complete

```powershell
.\verify-sync.ps1
```

Expected output:
```
[OK] Checking database files...
  universal_image_archive.db: 35.3 / 35.3 GB [100%]
  image_collection.db: 1.7 / 1.7 GB [100%]
  google_takeout_photos_2023.db: 3.9 / 3.9 GB [100%]

[OK] Total: 40.9 / 40.9 GB
[OK] Docker Ready
[OK] Git Status
[OK] Configuration

SUCCESS: All systems ready for development!
```

Verify:
- [ ] All databases show [100%]
- [ ] Total is 40.9 GB
- [ ] Docker shows [OK]
- [ ] Git shows [OK]
- [ ] Configuration shows [OK]
- [ ] Final line says "SUCCESS"

### Continuous Monitoring (Optional)

```powershell
.\verify-sync.ps1 -Monitor
```

- [ ] Status updates every 60 seconds
- [ ] All systems remain green/OK
- [ ] Press Ctrl+C to stop

---

## Progress Monitoring During Setup

### What You'll See on PC 1

```
11:17:36 [i] Verifying paths...
11:17:36 [OK] Found: D:\Dev\TheTimeThen
11:17:36 [..] Creating OneDrive folder structure...
11:17:36 [OK] Created: D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data\databases
11:17:36 [..] Copying universal_image_archive.db...
[####------] 25% - Copied: 10.3/40.9 GB (68 MB/s)
[######----] 40% - Copied: 16.4/40.9 GB (66 MB/s)
[########--] 65% - Copied: 26.6/40.9 GB (65 MB/s)
[##########] 100% - Copied successfully!
11:18:42 [..] Waiting for OneDrive to sync...
[#####-----] 50% - Syncing... (check OneDrive)
[##########] 100% - OneDrive sync appears complete!
11:35:15 [OK] Git repository initialized
11:45:22 [OK] Docker image built successfully
[OK] PC 1 SETUP COMPLETE!
```

### What You'll See on PC 2

```
[i] Configuration:
  GitHub: https://github.com/user/repo.git
  Local:  D:\Dev\TheTimeThen
  OneDrive: D:\Nvisions OneDrive\...

[OK] Repository cloned successfully
[OK] .env created and configured
[..] Waiting for OneDrive download...
[####------] 25% - Downloaded: 10.3/40.9 GB
[######----] 40% - Downloaded: 16.4/40.9 GB
[########--] 65% - Downloaded: 26.6/40.9 GB
[##########] 100% - OneDrive download complete!
[OK] Database files verified
[OK] Docker image built successfully
[OK] PC 2 SETUP COMPLETE!
```

---

## Troubleshooting Quick Reference

### Problem: "Permission denied"
**Solution:** Right-click PowerShell → Run as Administrator

### Problem: "Docker: command not found"
**Solution:** Install Docker Desktop, restart PowerShell

### Problem: "OneDrive path not accessible"
**Solution:** Verify path exists, start OneDrive, wait for sync

### Problem: "Git repository not found"
**Solution:** Ensure PC 1 pushed to GitHub first

### Problem: Progress stuck at 0%
**Solution:** Wait 1-2 minutes, check internet, check disk space

### Problem: OneDrive stuck syncing
**Solution:** Check File Explorer, wait for green checkmarks, don't interrupt

---

## Time Estimate Summary

| Phase | Duration | Notes |
|-------|----------|-------|
| PC 1 Folder Creation | 5 min | Quick |
| PC 1 Copy 40.9GB | 10-15 min | Fast (local copy) |
| PC 1 OneDrive Sync | 20-60 min | ⏳ LONGEST (internet) |
| PC 1 Docker Build | 10 min | One-time |
| PC 1 Git Setup | 2 min | Quick |
| **PC 1 Total** | **60-90 min** | |
| **PC 2 Clone Code** | **2 min** | Quick |
| **PC 2 OneDrive Download** | **20-40 min** | ⏳ LONGEST (internet) |
| **PC 2 Docker Build** | **10 min** | One-time |
| **PC 2 Total** | **50-80 min** | |
| **Verification** | **2-3 min** | Quick |
| **GRAND TOTAL** | **~2-2.5 HOURS** | Mostly waiting |

---

## Success Criteria

### PC 1 is Complete When:
✅ Script shows "[OK] PC 1 SETUP COMPLETE!"
✅ OneDrive shows green checkmarks for all databases
✅ Git shows "creating branch main..."
✅ You successfully pushed to GitHub

### PC 2 is Complete When:
✅ Script shows "[OK] PC 2 SETUP COMPLETE!"
✅ OneDrive shows green checkmarks for all databases
✅ verify-sync.ps1 shows "SUCCESS"

### Full Setup is Complete When:
✅ Both PCs have same code (via git pull)
✅ Both PCs see same databases (via OneDrive)
✅ Both PCs have identical Docker environment
✅ verify-sync.ps1 -Monitor shows all systems ready
✅ Both PCs can start Docker containers with data access

---

## Next Steps After Setup

1. **Start Docker on PC 1:**
   ```powershell
   cd D:\Dev\TheTimeThen
   docker-compose up -d
   ```

2. **Start Docker on PC 2:**
   ```powershell
   cd D:\Dev\TheTimeThen
   docker-compose up -d
   ```

3. **Verify containers running:**
   ```powershell
   docker-compose ps
   ```

4. **Test database access:**
   ```powershell
   docker-compose exec timethen python check_db.py
   ```

5. **Monitor sync continuously:**
   ```powershell
   .\verify-sync.ps1 -Monitor
   ```

---

## File Locations

All scripts are in: **D:\Dev\TheTimeThen\**

```
D:\Dev\TheTimeThen\
├── setup-pc1-automated.ps1         ← Run this FIRST on PC 1
├── setup-pc2-automated.ps1         ← Run this SECOND on PC 2
├── verify-sync.ps1                 ← Run this to check status
├── AUTOMATED-SETUP-GUIDE.md        ← Read this for full details
├── Dockerfile                      ← Docker config
├── docker-compose.yml              ← Container orchestration
├── requirements.txt                ← Python dependencies
├── .env.example                    ← Environment template
├── .gitignore                      ← Git ignore rules
├── README.md                       ← Project overview
├── START_HERE.txt                  ← Quick reference
└── ... (other files)
```

---

## Support

If you get stuck:

1. **Read the full guide:**
   ```powershell
   notepad AUTOMATED-SETUP-GUIDE.md
   ```

2. **Check script help:**
   ```powershell
   Get-Help .\setup-pc1-automated.ps1 -Full
   ```

3. **Look for error messages** in the output (red [!!])

4. **Check file locations and permissions**

5. **Verify internet connection and disk space**

---

## Ready to Start?

```powershell
cd D:\Dev\TheTimeThen
.\setup-pc1-automated.ps1
```

Good luck! The scripts handle all the hard work. Just watch the progress bars and follow the instructions. 🚀
