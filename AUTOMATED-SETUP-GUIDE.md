# TheTimeThen - Automated Multi-Computer Setup

## Quick Start

You now have **3 powerful automation scripts** ready to set up your multi-computer development environment with minimal manual work and **real-time progress monitoring**.

### The 3 Scripts

```
1. setup-pc1-automated.ps1    ← Run this FIRST on PC 1
2. setup-pc2-automated.ps1    ← Run this SECOND on PC 2 (after PC 1 finishes)
3. verify-sync.ps1             ← Run this on either PC to check status
```

---

## What You'll See: Real-Time Progress Monitoring

As the scripts run, you'll see **live progress bars** that update every 60 seconds:

```
[####----------------------------] 15% - Copied: 6.2/40.9 GB (65 MB/s)
```

Breaking this down:
- `[####---]` = Progress bar (# = done, - = remaining)
- `15%` = Percentage complete
- `6.2/40.9 GB` = Data transferred so far
- `65 MB/s` = Current transfer speed

---

## Step-by-Step Execution

### PHASE 1: PC 1 Setup (60-90 minutes)

#### Step 1: Open PowerShell on PC 1

```powershell
cd D:\Dev\TheTimeThen
```

#### Step 2: Start the automated setup

```powershell
.\setup-pc1-automated.ps1
```

#### Step 3: Watch the progress

The script will:
1. ✅ Verify all files exist (2 seconds)
2. ✅ Create OneDrive folders (5 seconds)
3. 📊 **Copy 40.9 GB databases** (10-15 min)
   - Watch progress bar update
   - You'll see: `[████████░░░░░░░░░░░░░░░░░░] 35% - Copied: 14.3/40.9 GB (68 MB/s)`
4. ⏳ **Wait for OneDrive sync** (10-30 min) - MOST TIME HERE
   - Watch File Explorer - files show blue cloud, then green checkmark
   - Progress bar updates every 60 seconds
   - You'll see: `[##################--] 82% - Syncing... (check OneDrive)`
5. ✅ Create .env configuration (10 seconds)
6. ✅ Initialize Git (20 seconds)
7. 🐳 **Build Docker image** (10 min)
   - Docker output shown in real-time
   - Will cache after first build

#### Step 4: After PC 1 completes

When you see:
```
============================================================
  [OK] PC 1 SETUP COMPLETE!
============================================================
```

Now you must:

1. **Verify OneDrive sync is complete**
   - Open File Explorer
   - Go to `D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data\databases\`
   - All 3 files should have ✅ green checkmarks
   - DON'T proceed until you see all green checkmarks!

2. **Push to GitHub**
   ```powershell
   cd D:\Dev\TheTimeThen
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```
   - You should see "Creating branch main..."
   - This uploads your code to GitHub

---

### PHASE 2: PC 2 Setup (50-80 minutes)

#### Only start this AFTER:
- ✅ PC 1 completely finished
- ✅ OneDrive shows green checkmarks for all 3 databases
- ✅ You successfully pushed to GitHub

#### Step 1: Open PowerShell on PC 2

```powershell
cd D:\  (or wherever you want to clone)
```

#### Step 2: Start the automated setup

```powershell
.\setup-pc2-automated.ps1 -GitHubRepo "https://github.com/YOUR_USERNAME/YOUR_REPO.git"
```

Or if prompted, just enter your repo URL when asked.

#### Step 3: Watch the progress

The script will:
1. ✅ Clone from GitHub (2 min)
2. ✅ Create .env configuration (10 seconds)
3. ⏳ **Wait for OneDrive download** (20-40 min) - MOST TIME HERE
   - Progress updates every 60 seconds
   - You'll see: `[####################------] 65% - Downloaded: 26.5/40.9 GB`
   - Watch File Explorer - files show blue cloud icon while downloading
   - When complete, you'll see green checkmarks
4. ✅ Verify all 3 databases exist (5 seconds)
5. 🐳 **Build Docker image** (10 min)

---

### PHASE 3: Verification (5 minutes)

#### Check sync status on either PC

```powershell
.\verify-sync.ps1
```

You'll see:
```
[i] Checking database files...
  universal_image_archive.db: 35.3 / 35.3 GB [100%]
  image_collection.db: 1.7 / 1.7 GB [100%]
  google_takeout_photos_2023.db: 3.9 / 3.9 GB [100%]

[OK] Total: 40.9 / 40.9 GB
[OK] Docker Ready
[OK] Git Status
[OK] Configuration

SUCCESS: All systems ready for development!
```

#### Continuous monitoring (updates every 60 seconds)

```powershell
.\verify-sync.ps1 -Monitor
```

Press Ctrl+C to stop.

---

## What Each Script Does

### setup-pc1-automated.ps1

**Purpose:** Initialize PC 1 with databases and Docker

**What it does:**
- Verifies Dockerfile, docker-compose.yml, requirements.txt exist
- Creates folder structure on OneDrive
- Copies 42GB database files to OneDrive
- Waits for OneDrive to sync (monitors every 60 seconds)
- Creates .env file with correct paths
- Initializes Git repository
- Creates first commit with: `"Initial commit: Docker setup and database configuration"`
- Builds Docker image from Dockerfile
- Shows real-time progress with speed and ETA

**Parameters:**
```powershell
.\setup-pc1-automated.ps1 -OneDrivePath "D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data"
```

**Output example:**
```
11:17:36 [i] Verifying paths...
11:17:36 [OK] Found: D:\Dev\TheTimeThen
11:17:36 [OK] Found: D:\Dev\TheTimeThen\Dockerfile
...
11:17:36 [..] Creating OneDrive folder structure...
11:17:36 [OK] Created: D:\Nvisions OneDrive\...\databases
11:17:36 [..] Copying universal_image_archive.db...
[####---] 25% - Copied: 10.3/40.9 GB (65 MB/s)
...
```

### setup-pc2-automated.ps1

**Purpose:** Clone code from GitHub and sync databases on PC 2

**What it does:**
- Prompts for GitHub repository URL
- Clones code from GitHub to local path
- Creates .env file with OneDrive paths
- Waits for OneDrive to download databases (monitors every 60 seconds)
- Verifies all 3 database files exist
- Builds Docker image
- Shows real-time download progress

**Parameters:**
```powershell
.\setup-pc2-automated.ps1 -GitHubRepo "https://github.com/user/repo.git"
```

Or run with no parameters and it will ask you to enter the URL.

**Output example:**
```
[i] GitHub repository URL required
Enter GitHub repository URL: https://github.com/user/repo.git
[OK] Repository cloned successfully
[..] Waiting for OneDrive download...
[############----------] 52% - Downloaded: 21.2/40.9 GB
...
```

### verify-sync.ps1

**Purpose:** Check synchronization status of all components

**What it checks:**
- Database file sizes (expected vs actual)
- Modification timestamps
- Docker installation and image
- Git repository status
- Configuration files (.env, .env.example)

**Modes:**
```powershell
# One-time check
.\verify-sync.ps1

# Continuous monitoring (updates every 60 seconds)
.\verify-sync.ps1 -Monitor

# Custom OneDrive path
.\verify-sync.ps1 -OneDrivePath "D:\Your\Path"
```

**Output example:**
```
[i] Checking database files...
  universal_image_archive.db: 35.3 / 35.3 GB [100%]
[OK] Docker Ready
[OK] Git Status
[OK] Configuration
SUCCESS: All systems ready for development!
```

---

## Progress Monitoring Features

### Real-Time Progress Bars

Every 60 seconds, you'll see updated bars like:

```
[#---------] 10%
[###-------] 30%
[#####-----] 50%
[#######---] 70%
[#########-] 90%
[##########] 100%
```

### Speed Monitoring

Shows current transfer speed in MB/s:
- `65 MB/s` = Excellent (typical for local network)
- `10-20 MB/s` = Good (typical for internet upload/download)
- `1-5 MB/s` = Slow (check your internet)
- `0.1 MB/s` = Very slow (possible network issue)

### Time Tracking

Timestamps on every message:
```
11:17:36 [OK] Setup complete
11:18:42 [..] Still waiting...
11:25:15 [!!] Error occurred
```

---

## Troubleshooting

### "Permission denied" or "Access is denied"

**Cause:** Script needs administrator privileges

**Fix:**
1. Right-click PowerShell
2. Click "Run as Administrator"
3. Run the script again

### "Docker: command not found"

**Cause:** Docker not installed or not in PATH

**Fix:**
1. Install Docker Desktop from docker.com
2. Add Docker to your PATH (restart PowerShell after installation)
3. Verify with: `docker --version`

### "OneDrive path not accessible"

**Cause:** OneDrive not running or path incorrect

**Fix:**
1. Open File Explorer
2. Verify `D:\Nvisions OneDrive\OneDrive\` exists
3. Start OneDrive if not running
4. Wait for it to fully load
5. Use correct path in script parameter

### "Git repository not found"

**Cause:** PC 1 didn't push to GitHub yet

**Fix:**
1. On PC 1, make sure you ran:
   ```powershell
   git remote add origin <URL>
   git push -u origin main
   ```
2. Verify repo is accessible on GitHub
3. Then run PC 2 setup

### Progress stuck at 0%

**Cause:** Transfer just starting or system busy

**Fix:**
- Wait 1-2 minutes for data to start transferring
- Check internet connection
- Check disk space (need ~50GB free)
- Check OneDrive is not syncing other files

---

## What Happens Under the Hood

### PC 1 Timeline

```
Start
  ├─ Verify files (2 sec)
  ├─ Create folders (5 sec)
  ├─ Copy 40.9 GB (10-15 min) ← Shows progress every second
  │   [###########-] 65% - Copied: 26.6/40.9 GB (66 MB/s)
  ├─ OneDrive sync (10-30 min) ← Shows progress every 60 sec
  │   [#############-------] 63% - Syncing...
  ├─ Create .env (10 sec)
  ├─ Git init (20 sec)
  ├─ Build Docker (10 min)
  └─ Complete!

Total: 60-90 minutes
```

### PC 2 Timeline

```
Start
  ├─ Clone from GitHub (2 min)
  ├─ Create .env (10 sec)
  ├─ OneDrive download (20-40 min) ← Shows progress every 60 sec
  │   [#################---] 83% - Downloaded: 34/40.9 GB
  ├─ Verify databases (5 sec)
  ├─ Build Docker (10 min)
  └─ Complete!

Total: 50-80 minutes
```

---

## Important Warnings

⚠️ **DO NOT close PowerShell** during setup - it will stop the transfer

⚠️ **DO NOT disconnect internet** - files must finish syncing

⚠️ **DO NOT start PC 2** until PC 1 shows green checkmarks in OneDrive

⚠️ **DO NOT unplug ethernet/WiFi** while copying or syncing files

⚠️ **WAIT for "PC 1 SETUP COMPLETE"** before pushing to GitHub

---

## Success Criteria

### PC 1 Complete When:
- ✅ Script shows "[OK] PC 1 SETUP COMPLETE!"
- ✅ File Explorer shows green checkmarks on all 3 databases
- ✅ Git shows "creating branch main..."
- ✅ You can push to GitHub successfully

### PC 2 Complete When:
- ✅ Script shows "[OK] PC 2 SETUP COMPLETE!"
- ✅ verify-sync.ps1 shows "SUCCESS: All systems ready!"
- ✅ File Explorer shows green checkmarks on all 3 databases
- ✅ Docker can start containers

### Full Setup Complete When:
- ✅ Both PCs show same code (via git)
- ✅ Both PCs see same databases (via OneDrive)
- ✅ Both PCs have identical Docker environment
- ✅ `verify-sync.ps1 -Monitor` shows all systems ready

---

## Next Steps After Setup

Once both PCs are set up:

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

3. **Verify containers are running:**
   ```powershell
   docker-compose ps
   ```

4. **Test database access:**
   ```powershell
   docker-compose exec timethen python check_db.py
   ```

5. **Check real-time sync:**
   ```powershell
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

**Ready to start? Run this:**

```powershell
cd D:\Dev\TheTimeThen
.\setup-pc1-automated.ps1
```

Good luck! 🚀
