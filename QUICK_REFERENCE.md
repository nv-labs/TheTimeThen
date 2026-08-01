# TheTimeThen Setup - Quick Reference Card

## 📍 Storage Structure

```
D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data\
├── data/
│   ├── universal_image_archive.db    (36 GB)
│   ├── image_collection.db            (1.7 GB)
│   └── google_takeout_photos_2023.db  (4 GB)
├── output/
│   └── Processing results
└── logs/
    └── Application logs
```

**Total: ~42 GB**

---

## 🖥️ PC 1 - Setup Commands (Copy & Paste)

### Step 1: Create OneDrive Folder
```powershell
mkdir "D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data\data"
mkdir "D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data\output"
mkdir "D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data\logs"
```

### Step 2: Copy Databases to OneDrive
```powershell
cd D:\Dev\TheTimeThen

copy universal_image_archive.db "D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data\data\"
copy image_collection.db "D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data\data\"
copy google_takeout_photos_2023.db "D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data\data\"

# Verify (wait until all files are copied)
dir "D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data\data\" *.db
```

⏳ **Wait for OneDrive to sync (green checkmark in File Explorer)** - could take 10-30 min

### Step 3: Create .env File
```powershell
cd D:\Dev\TheTimeThen
copy .env.example .env
notepad .env
```

**Paste this content (should already be there):**
```
DB_VOLUME_PATH=D:/Nvisions OneDrive/OneDrive/TheTimeThen-Data/data
OUTPUT_VOLUME_PATH=D:/Nvisions OneDrive/OneDrive/TheTimeThen-Data/output
OPENAI_API_KEY=sk-your-key-here
```

**Save (Ctrl+S), Close (Alt+F4)**

### Step 4: Build Docker Image
```powershell
cd D:\Dev\TheTimeThen
docker-compose build
```

⏳ **Takes 5-10 minutes first time**

### Step 5: Start Container & Verify
```powershell
docker-compose up -d
docker-compose exec thetimethen bash -c "ls -lh /app/data/*.db"
```

**Should show all 3 databases ✅**

### Step 6: Initialize Git & Push
```powershell
cd D:\Dev\TheTimeThen

git init
git config user.email "your@email.com"
git config user.name "Your Name"

git add .
git status  # Verify .env and .db files NOT listed

git commit -m "Initial commit: TheTimeThen with Docker setup"

# Go to GitHub.com, create empty repo, then:
git remote add origin https://github.com/YOUR_USERNAME/thetimethen.git
git branch -M main
git push -u origin main
```

---

## 🖥️ PC 2 - Setup Commands (Copy & Paste)

### Step 1: Clone from GitHub
```powershell
cd D:\Dev
git clone https://github.com/YOUR_USERNAME/thetimethen.git
cd thetimethen
```

### Step 2: Wait for OneDrive Sync
⏳ **Wait 20-40 minutes for 42GB to download to PC 2**

**Check progress:**
```powershell
dir "D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data\data\" *.db
```

**Wait until you see all 3 files with green checkmarks in File Explorer**

### Step 3: Create .env File
```powershell
cd D:\Dev\thetimethen
copy .env.example .env
notepad .env
```

**Use SAME content as PC 1:**
```
DB_VOLUME_PATH=D:/Nvisions OneDrive/OneDrive/TheTimeThen-Data/data
OUTPUT_VOLUME_PATH=D:/Nvisions OneDrive/OneDrive/TheTimeThen-Data/output
OPENAI_API_KEY=sk-your-key-here
```

**Save and close**

### Step 4: Build & Start
```powershell
cd D:\Dev\thetimethen
docker-compose build
docker-compose up -d
```

### Step 5: Verify Databases
```powershell
docker-compose exec thetimethen bash -c "ls -lh /app/data/*.db"
```

**Should show all 3 databases ✅**

---

## 📋 Daily Workflow

### Make Changes on PC 1:
```powershell
cd D:\Dev\TheTimeThen

# Edit code...
# Test it...
docker-compose exec thetimethen python auto_extract_historical_photos.py "video.mp4"

# When happy, commit and push
git add .
git commit -m "What changed"
git push origin main
```

### Run on PC 2:
```powershell
cd D:\Dev\thetimethen

# Get latest code
git pull origin main

# Rebuild (only needed if requirements.txt changed)
docker-compose build

# Restart container
docker-compose down && docker-compose up -d

# Database is already there (OneDrive synced it)!
# Just run your script
docker-compose exec thetimethen python insert_photos_with_ai_categories.py ...
```

---

## 🔧 Common Commands

```bash
# Enter container shell
docker-compose exec thetimethen bash

# Run Python script inside container
docker-compose exec thetimethen python script.py

# Check logs
docker-compose logs -f

# Stop container
docker-compose down

# Rebuild image
docker-compose build

# Check if database is readable
docker-compose exec thetimethen python -c "
import sqlite3
for db in ['/app/data/image_collection.db']:
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM sqlite_master WHERE type=\"table\"')
    print(f'{db}: OK ({cursor.fetchone()[0]} tables)')
"

# Check disk space
docker-compose exec thetimethen df -h /app/
```

---

## ⚠️ Important Notes

### Database Consistency
- ✅ Only ONE container should write at a time
- ✅ Reading from both simultaneously is fine
- ⚠️ Wait 5-10 seconds after writing before other PC accesses database
- ⚠️ OneDrive must finish syncing before other PC sees changes

### OneDrive Sync
- Check sync status in File Explorer (green checkmark = synced)
- Don't access files during sync
- If synced shows "error", right-click → Sync
- Large files (42GB) can take 30+ minutes on slower internet

### Git
- ✅ Code syncs instantly via GitHub
- ✅ Never commit databases or .env to Git
- ✅ Always pull before making changes

### Docker
- First build: 5-10 minutes
- Subsequent builds: 1-2 minutes (cached layers)
- Image size: ~4GB (includes all dependencies)

---

## 🚨 Troubleshooting

### "Database is locked"
```
✓ Only one container should write
✓ Wait 5 seconds between operations
✓ Check OneDrive sync finished
```

### "File not found" error
```
✓ Check OneDrive path: D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data\data\
✓ Wait for sync to complete (green checkmark)
✓ Verify .env has correct paths
```

### "Permission denied"
```bash
docker-compose exec thetimethen chmod -R 755 /app/data
```

### "OneDrive not syncing"
```
✓ Check OneDrive icon in system tray
✓ Open File Explorer → navigate to folder
✓ Right-click folder → Sync
✓ Check internet connection
```

### "Docker build fails"
```powershell
docker-compose down
docker system prune
docker-compose build --no-cache
```

---

## ✅ Verification Checklist

After setup on each PC:

- [ ] Databases copied/synced (all 3 files present)
- [ ] OneDrive shows green checkmark (synced)
- [ ] .env file created with correct paths
- [ ] Docker image built
- [ ] Container running: `docker-compose ps`
- [ ] Databases visible in container: `docker-compose exec thetimethen ls /app/data/`
- [ ] Can query database: no errors

---

## 📞 Quick Help

| Problem | Solution |
|---------|----------|
| "Can't see databases on PC 2" | Wait for OneDrive sync, check File Explorer |
| "Database is locked" | Wait 10 seconds, ensure only 1 container writing |
| "Docker won't start" | Run `docker-compose down && docker-compose up -d` |
| "Can't push to GitHub" | Check git remote: `git remote -v` |
| "Code not updating on PC 2" | Run `git pull origin main` |

---

## 📖 Full Documentation

Read these files in order for complete details:
1. `00_START_HERE.md` - Overview
2. `SETUP_SUMMARY.md` - Architecture
3. `STEP_BY_STEP_SETUP.md` - Detailed steps (the long version)
4. `DOCKER_QUICKSTART.md` - Daily commands

**This card:** Quick copy-paste for experienced users

---

**Questions?** Check the detailed docs or the section above. You've got this! 💪
