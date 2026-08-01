# Implementation Checklist - Docker + Git Setup

## ✅ Files Created for Multi-Computer Development

- [x] **Dockerfile** - Container image with all dependencies (FFmpeg, Tesseract, Python packages)
- [x] **docker-compose.yml** - Service orchestration with volume mounts
- [x] **requirements.txt** - Python package dependencies
- [x] **.env.example** - Configuration template (commit this)
- [x] **.gitignore** - Exclude database, outputs, sensitive files
- [x] **README_DOCKER_SETUP.md** - Comprehensive setup guide (6700 words)
- [x] **DOCKER_QUICKSTART.md** - Quick reference for daily work
- [x] **SETUP_SUMMARY.md** - Visual overview and checklist

## 🚀 Quick Start - Next Steps

### Step 1: Initialize Git Repository (PC 1)

```bash
cd D:\Dev\TheTimeThen

# Initialize git
git init
git config user.email "your@email.com"
git config user.name "Your Name"

# Add all files (except those in .gitignore)
git add .
git commit -m "Initial commit: TheTimeThen project with Docker setup"

# Create remote (on GitHub.com first)
git remote add origin https://github.com/YOUR_USERNAME/thetimethen.git
git branch -M main
git push -u origin main
```

### Step 2: Set Up Shared Database Storage (PC 1)

**Option A: Windows Network Share (Recommended for Windows)**
```powershell
# Create shared folder
mkdir D:\Shared\TheTimeThen\data
mkdir D:\Shared\TheTimeThen\output

# Create SMB share (right-click folder → Share → Share with Everyone)
# Or via PowerShell:
New-SmbShare -Name "TheTimeThen" -Path "D:\Shared\TheTimeThen" -FullAccess Everyone

# Map drive
net use Z: \\YOUR-PC-NAME\TheTimeThen
dir Z:\  # Verify it works
```

**Option B: Syncthing (Peer-to-peer, works everywhere)**
- Install from https://syncthing.net/
- Create sync folder: D:\Sync\TheTimeThen\data
- Point both machines to same folder
- Syncs automatically in real-time

### Step 3: Create .env File (PC 1)

```bash
# Copy template
copy .env.example .env

# Edit .env with your actual paths:
```

**For Windows SMB share:**
```
DB_VOLUME_PATH=Z:/TheTimeThen/data
OUTPUT_VOLUME_PATH=Z:/TheTimeThen/output
OPENAI_API_KEY=sk-your-key-here
```

**For Linux/Docker on Linux:**
```
DB_VOLUME_PATH=/mnt/shared/TheTimeThen/data
OUTPUT_VOLUME_PATH=/mnt/shared/TheTimeThen/output
OPENAI_API_KEY=sk-your-key-here
```

### Step 4: Build and Test (PC 1)

```bash
# Build Docker image (2-5 minutes, one time)
docker-compose build

# Start container
docker-compose up -d

# Enter container shell
docker-compose exec thetimethen bash

# Inside container, verify everything works:
python --version                      # Should be Python 3.12
tesseract --version                   # Should be installed
ffprobe -version                      # Should be installed
ls /app/data/                         # Should see database (if copied)

# Exit container
exit
```

### Step 5: Clone on PC 2

```bash
# Clone from GitHub
git clone https://github.com/YOUR_USERNAME/thetimethen.git
cd thetimethen

# Map same network drive as PC 1
net use Z: \\PC1-NAME\TheTimeThen

# Copy .env template and configure (use same paths as PC 1!)
copy .env.example .env
# Edit .env with same shared storage paths

# Build (uses cached layers if PC 1 already built)
docker-compose build

# Start
docker-compose up -d

# Test
docker-compose exec thetimethen bash
ls /app/data/  # Database is already there from PC 1!
```

## 💾 Shared Storage Options Comparison

| Option | Speed | Setup | Cost | Requires |
|--------|-------|-------|------|----------|
| **Windows SMB Share** | Medium | Easy | Free | Network cable |
| **Syncthing** | Fast | Easy | Free | Both PCs online |
| **Google Drive** | Slow | Medium | Free | Internet |
| **NFS** | Very Fast | Medium | Free/$ | Linux/NAS |
| **Docker Registry** | N/A | Hard | Free/$ | Docker Hub |

**My recommendation for you:** Start with **Windows SMB share** (simplest), then upgrade to **Syncthing** if performance issues arise.

## 🔄 Daily Workflow After Setup

### Make changes on PC 1:
```bash
# Edit code
# Test locally
docker-compose exec thetimethen python auto_extract_historical_photos.py video.mp4

# Commit and push
git add .
git commit -m "Improve: better duplicate detection"
git push origin main
```

### Update PC 2:
```bash
# Pull latest code
git pull origin main

# Rebuild image (only if requirements.txt changed)
docker-compose build

# Restart container
docker-compose down && docker-compose up -d

# Database already exists on shared storage!
docker-compose exec thetimethen python insert_photos_with_ai_categories.py ...
```

## 🐛 Troubleshooting Common Issues

### "Cannot access network share"
```bash
# Windows - check if share is mounted
net use

# Try reconnecting
net use Z: /delete
net use Z: \\PC1\TheTimeThen
```

### "Database is locked"
- Only one container should write at a time
- Solution: Queue jobs with RabbitMQ/Redis for multiple users
- Or: Run scripts sequentially

### "Permission denied on /app/data"
```bash
# Inside container
sudo chown -R $(id -u):$(id -g) /app/data
chmod -R 755 /app/data
```

### "Docker image very large"
- Normal! ~4GB for all dependencies
- Build once, reuse
- Push to Docker Hub to avoid rebuilding on PC 2

### "Slow network performance"
- SMB: 10-50 MB/s (use NFS for better performance)
- Consider Syncthing for real-time local sync
- Or cache on local SSD + periodic sync to network

## 📋 Verification Checklist

After setup, verify each item:

- [ ] Git repository created and pushed to GitHub
- [ ] Network share created and mapped on both PCs
- [ ] Both .env files point to same shared paths
- [ ] `docker-compose build` completes successfully on PC 1
- [ ] Docker image can be pulled/built on PC 2
- [ ] Container starts: `docker-compose up -d`
- [ ] Database visible inside container: `docker-compose exec thetimethen ls /app/data`
- [ ] Can run script on PC 1: `docker-compose exec thetimethen python auto_extract_historical_photos.py`
- [ ] Can git commit on PC 1 and git pull on PC 2
- [ ] Code changes on PC 2 are visible in container on PC 1

## 📚 Documentation

- **SETUP_SUMMARY.md** - Overview and architecture
- **DOCKER_QUICKSTART.md** - Command reference
- **README_DOCKER_SETUP.md** - Detailed setup guide

Read these in order for best understanding!

## 🆘 If Something Goes Wrong

### Container won't start
```bash
docker-compose logs -f  # See error messages
docker-compose down
docker-compose up -d    # Try again
```

### Volume won't mount
```bash
# Check if path exists on host
ls ${DB_VOLUME_PATH}

# Check mounts in container
docker-compose exec thetimethen mount

# If missing, create it
mkdir -p ${DB_VOLUME_PATH}
```

### Git push fails
```bash
# Verify remote
git remote -v

# Add if missing
git remote add origin https://github.com/YOUR_USERNAME/thetimethen.git

# Force push if needed (careful!)
git push -u origin main
```

## ✨ Next Steps After Setup Works

1. **Test multi-machine workflow:**
   - Make change on PC 1 → push → pull on PC 2 → verify code updated

2. **Test database sync:**
   - Run extraction on PC 1 → database updated on shared storage → visible on PC 2

3. **Optimize performance:**
   - Profile which step is slowest (extraction? OCR? database writes?)
   - Consider Syncthing if SMB is too slow
   - Add caching layer if needed

4. **Scale to team:**
   - Set up message queue (RabbitMQ/Redis) for job management
   - Docker Compose with multiple services
   - Centralized logging (ELK stack)

---

**You're ready to start!** 🎉

Questions? Check the guides in order:
1. SETUP_SUMMARY.md (overview)
2. DOCKER_QUICKSTART.md (commands)
3. README_DOCKER_SETUP.md (details)
