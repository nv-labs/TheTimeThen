# TheTimeThen Multi-Computer Development Setup - Summary

## What You Need

✅ **Git** - For version controlling code changes
✅ **Docker** - For consistent environment across machines  
✅ **Shared Storage** - For shared database (SMB/NFS/Cloud)

## Files Created

```
D:\Dev\TheTimeThen\
├── Dockerfile              ← Container image definition
├── docker-compose.yml      ← Container orchestration
├── requirements.txt        ← Python dependencies
├── .env.example           ← Template config (commit this)
├── .gitignore             ← What NOT to commit
├── README_DOCKER_SETUP.md ← Detailed setup guide
└── DOCKER_QUICKSTART.md   ← Quick reference
```

## How It Works

### PC 1 (Development)
```
┌─────────────────────────────┐
│ Local: D:\Dev\TheTimeThen   │
│ - Edit code                 │
│ - Git push                  │
│ - Docker builds image       │
│ - Container reads/writes DB │
└────────────┬────────────────┘
             │ git push
             ▼
         ┌────────┐
         │ GitHub │
         └────┬───┘
              │ git pull
             ▲
┌────────────┴────────────────┐
│ PC 2 (Testing)              │
│ - Git pull latest code      │
│ - Docker builds image       │
│ - Container reads/writes DB │
└─────────────────────────────┘
```

**BUT the database is shared:**
```
         ┌─────────────────────┐
         │  Shared Storage     │
         │  (Network/Cloud)    │
         │                     │
         │ image_collection.db │
         │ /data/*             │
         │ /output/*           │
         └────────┬────────────┘
                  │
        ┌─────────┴──────────┐
        │                    │
    ┌───▼──────┐        ┌───▼──────┐
    │   PC 1   │        │   PC 2   │
    │ Mounted  │        │ Mounted  │
    │ as Z:\   │        │ as Z:\   │
    └──────────┘        └──────────┘
```

## Recommended Approach for You

### **Simplest (for Windows Network):**
```
PC 1: Create SMB share → D:\Shared\TheTimeThen
PC 2: Map network drive → net use Z: \\PC1\TheTimeThen
Both: docker-compose.yml uses Z:\TheTimeThen\data
```

**Pros:** No extra software, works on any LAN
**Cons:** Slightly slower than local, PC1 must stay online

### **Best (for Active Development):**
```
Use Syncthing (free, peer-to-peer)
Syncs: D:\Dev\TheTimeThen\data
Real-time sync, works everywhere, no central server
```

**Pros:** Fast, real-time, works anywhere, peer-to-peer
**Cons:** Need to install Syncthing

### **Production Ready (for Teams):**
```
Docker Registry + NFS Storage
Push images to registry
All machines pull from registry
NFS for faster shared storage
```

## Step-by-Step Quick Start

### PC 1 - Initial Setup (15 minutes)

```bash
# 1. Create shared folder and Git repo
mkdir D:\Shared\TheTimeThen\{data,output}
New-SmbShare -Name "TheTimeThen" -Path "D:\Shared\TheTimeThen" -FullAccess Everyone

cd D:\Dev\TheTimeThen
git init
git add .
git commit -m "Initial commit"

# 2. Create .env
copy .env.example .env
# Edit: DB_VOLUME_PATH=Z:/TheTimeThen/data

# 3. Map drive and test
net use Z: \\DESKTOP-YOURPC\TheTimeThen
dir Z:\

# 4. Build and run
docker-compose build
docker-compose up -d

# 5. Push to GitHub (create repo first on github.com)
git remote add origin https://github.com/yourname/thetimethen.git
git branch -M main
git push -u origin main
```

### PC 2 - Clone Setup (10 minutes)

```bash
# 1. Clone from GitHub
git clone https://github.com/yourname/thetimethen.git
cd thetimethen

# 2. Create .env
copy .env.example .env
# Use SAME shared paths as PC 1

# 3. Map same drive
net use Z: \\DESKTOP-YOURPC\TheTimeThen

# 4. Build and run
docker-compose build
docker-compose up -d

# Database already exists on shared storage!
```

## Daily Workflow

**After editing code on PC 1:**
```bash
git add .
git commit -m "Feature: improve duplicate detection"
git push origin main
```

**Before running on PC 2:**
```bash
git pull origin main
docker-compose build  # Only if requirements.txt changed
docker-compose down && docker-compose up -d

# Database is already there!
docker-compose exec thetimethen python insert_photos_with_ai_categories.py ...
```

## Important Notes

⚠️ **Database Consistency**
- Only run one container at a time accessing the DB
- SQLite can handle read-only from multiple sources
- But serializes writes to avoid corruption
- Solution: Queue processing via message broker (RabbitMQ/Redis) for teams

⚠️ **Network Performance**
- SMB on LAN: ~10-50 MB/s
- NFS on LAN: ~50-200 MB/s
- Syncthing on LAN: ~50-100 MB/s
- For large databases, consider local SSD cache

⚠️ **Don't Commit to Git**
- Database files (image_collection.db)
- Output artifacts (images, PDFs)
- .env file (environment variables)
- Large video files

**All covered in .gitignore!**

## Verification Checklist

After setup, verify:

- [ ] PC 1 can write to `D:\Shared\TheTimeThen\data\`
- [ ] PC 2 can access shared folder via network drive
- [ ] Both .env files point to same shared paths
- [ ] `docker-compose build` completes on both PCs
- [ ] Database file visible in `/app/data/` inside container
- [ ] Can run script on PC 1 and see results on PC 2
- [ ] Can git commit on PC 1 and git pull on PC 2
- [ ] Code changes from PC 2 appear in container on PC 1

## Get Help

- **Docker docs**: https://docs.docker.com/
- **Docker Compose**: https://docs.docker.com/compose/
- **Git**: https://git-scm.com/book/en/v2
- **Syncthing**: https://syncthing.net/
- **Network shares**: https://docs.microsoft.com/en-us/windows-server/storage/file-server/file-server-smb-overview

## File Reference

| File | Purpose | Commit to Git? |
|------|---------|---|
| `Dockerfile` | Container image | YES |
| `docker-compose.yml` | Services config | YES |
| `requirements.txt` | Python packages | YES |
| `.env` | Local config | NO |
| `.env.example` | Config template | YES |
| `.gitignore` | Ignore patterns | YES |
| `image_collection.db` | Database | NO |
| `/data/*` | Shared storage | NO |
| `/output/*` | Processing output | NO |

---

**Ready to start?** → See `DOCKER_QUICKSTART.md` for step-by-step commands
