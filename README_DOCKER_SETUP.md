# TheTimeThen Multi-Machine Development Setup

This guide explains how to set up TheTimeThen for development across multiple computers using Git + Docker.

## Architecture

- **Code**: Version controlled in Git (GitHub/GitLab)
- **Database**: Shared via network storage or synchronized
- **Container**: Docker runs on each machine with same environment
- **Consistency**: All machines use identical Python environment

## Prerequisites

### All Machines
- Docker Desktop installed
- Docker Compose installed
- Git installed
- Access to shared network storage (SMB/NFS/Google Drive/Syncthing)

### For Shared Storage Options

**Option 1: Windows Network Share (Simplest for Windows)**
- Set up SMB share on one PC or NAS
- Map as network drive: `\\server\share\TheTimeThen`

**Option 2: Linux/NAS NFS Share**
- NFS is faster than SMB
- Mount: `mount -t nfs server:/export /mnt/shared`

**Option 3: Google Drive / Dropbox (Cloud sync)**
- No infrastructure needed
- Slower but works anywhere
- Use rclone or native client

**Option 4: Syncthing (Peer-to-peer sync)**
- Real-time sync between machines
- No central server required
- Best for active development

## Setup Steps

### 1. Initialize Git Repository

On your development PC:

```bash
cd D:\Dev\TheTimeThen
git init
git config user.email "your@email.com"
git config user.name "Your Name"
git add .
git commit -m "Initial commit: TheTimeThen project"

# Push to GitHub (or GitLab)
git remote add origin https://github.com/yourusername/thetimethen.git
git branch -M main
git push -u origin main
```

**Create .gitignore:**
```
# Don't commit the database (it will be on shared storage)
image_collection.db
image_collection.db-*

# Don't commit output/processing artifacts
output/
output-ready/
Output/
*.jpg
*.png
*.mp4

# Python cache
__pycache__/
*.pyc
*.pyo
*.egg-info/
.pytest_cache/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Environment
.env
.env.local
```

### 2. Set Up Shared Database Storage

**For SMB (Windows):**
```powershell
# On PC1, create shared folder
$folderPath = "D:\Shared\TheTimeThen"
New-Item -ItemType Directory -Force $folderPath

# Share it (right-click → Properties → Sharing → Share → Add "Everyone")
# Or via PowerShell
New-SmbShare -Name "TheTimeThen" -Path $folderPath -FullAccess @("Everyone")

# On PC2, map network drive
New-PSDrive -Name "Z" -PSProvider FileSystem -Root "\\PC1\TheTimeThen"
```

**For Google Drive + rclone (Cloud):**
```bash
# Install rclone
# Configure Google Drive remote
rclone config

# Create folder
mkdir ~/mounted_drive

# Mount
rclone mount remote:TheTimeThen ~/mounted_drive &
```

### 3. Create .env File (Per Machine)

On each machine, create `.env` in the project root:

```bash
# PC 1 (Windows example)
DB_VOLUME_PATH=Z:/TheTimeThen/data
OUTPUT_VOLUME_PATH=Z:/TheTimeThen/output
OPENAI_API_KEY=sk-your-key-here

# PC 2 (Windows example)
DB_VOLUME_PATH=//192.168.1.100/TheTimeThen/data
OUTPUT_VOLUME_PATH=//192.168.1.100/TheTimeThen/output
OPENAI_API_KEY=sk-your-key-here

# Linux example
DB_VOLUME_PATH=/mnt/shared/TheTimeThen/data
OUTPUT_VOLUME_PATH=/mnt/shared/TheTimeThen/output
OPENAI_API_KEY=sk-your-key-here
```

**Don't commit .env to Git!** Add to .gitignore

### 4. Build and Run Container

**First time setup:**
```bash
# Clone on PC 2
git clone https://github.com/yourusername/thetimethen.git
cd thetimethen

# Build image (takes 2-5 minutes)
docker-compose build

# Run container (it will mount shared volume and stay alive)
docker-compose up -d

# Enter container shell
docker-compose exec thetimethen /bin/bash
```

**Inside container:**
```bash
# Run your scripts
python auto_extract_historical_photos.py "video.mp4"

# Check that database is readable from shared volume
ls -la /app/data/

# Verify output is saved to shared location
ls -la /app/output/
```

**Stop container:**
```bash
docker-compose down  # Stops but preserves volumes
docker-compose down -v  # Also removes volumes (be careful!)
```

### 5. Daily Development Workflow

**On PC 1 (make changes):**
```bash
# Make code changes
# Test locally
docker-compose exec thetimethen python auto_extract_historical_photos.py "video.mp4"

# Commit and push
git add .
git commit -m "Fix duplicate detection in auto_extract"
git push origin main
```

**On PC 2 (pull updates):**
```bash
# Pull latest code
git pull origin main

# Rebuild image (if dependencies changed)
docker-compose build

# Restart container with new code
docker-compose down
docker-compose up -d

# Database is already there in shared storage!
docker-compose exec thetimethen python insert_photos_with_ai_categories.py data output-ready extracted_text_cleaned.txt
```

## Troubleshooting

### Database Lock Issues
If you get "database is locked" errors:
- Only run one container at a time on database
- Wait for previous container to finish
- Use connection timeouts: `sqlite3.connect(db, timeout=30)`

### Permission Denied on Shared Volume
```bash
# Inside container, fix permissions
sudo chown -R $(id -u):$(id -g) /app/data
chmod -R 755 /app/data
```

### Slow Performance on Network Share
- SMB slower than NFS
- Consider local SSD cache + periodic sync
- Or run processing locally, sync results afterward

### Volume Not Mounted
```bash
# Check mounts inside container
docker-compose exec thetimethen mount

# Verify path exists on host
ls ${DB_VOLUME_PATH}
```

## Production Considerations

For multiple machines actively developing:

1. **Use Git branches** for features
   ```bash
   git checkout -b feature/new-feature
   # make changes
   git push origin feature/new-feature
   ```

2. **Database backups**
   ```bash
   # Inside container
   cp /app/data/image_collection.db /app/data/image_collection.db.backup
   ```

3. **Docker registry** (optional)
   - Tag image: `docker tag thetimethen:latest myregistry/thetimethen:latest`
   - Push: `docker push myregistry/thetimethen:latest`
   - Pull on PC2: `docker pull myregistry/thetimethen:latest`

## Summary of Files

Create in your project root:
- ✅ `Dockerfile` - Container image definition
- ✅ `docker-compose.yml` - Service orchestration
- ✅ `requirements.txt` - Python dependencies
- ✅ `.gitignore` - Exclude files from Git
- ✅ `README_DOCKER_SETUP.md` - This guide
- ✅ `.env` - Per-machine configuration (don't commit)
- ✅ `.env.example` - Template for .env (commit this)

Create `.env.example`:
```
DB_VOLUME_PATH=/path/to/shared/data
OUTPUT_VOLUME_PATH=/path/to/shared/output
OPENAI_API_KEY=sk-your-key-here
```
