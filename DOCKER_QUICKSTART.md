# Quick Start Guide for Multi-Machine Development

## One-Time Setup

### On PC 1 (Your primary development machine):

1. **Create shared folder:**
   ```powershell
   # Windows
   mkdir D:\Shared\TheTimeThen\data
   mkdir D:\Shared\TheTimeThen\output
   
   # Share it over network
   New-SmbShare -Name "TheTimeThen" -Path "D:\Shared\TheTimeThen" -FullAccess Everyone
   ```

2. **Initialize Git:**
   ```bash
   cd D:\Dev\TheTimeThen
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/thetimethen.git
   git push -u origin main
   ```

3. **Create .env file:**
   ```bash
   copy .env.example .env
   
   # Edit .env with your paths:
   # DB_VOLUME_PATH=Z:/TheTimeThen/data
   # OUTPUT_VOLUME_PATH=Z:/TheTimeThen/output
   ```

4. **Map network drive (Windows):**
   ```powershell
   net use Z: \\DESKTOP-PC1\TheTimeThen
   ```

5. **Build Docker image:**
   ```bash
   docker-compose build
   docker-compose up -d
   docker-compose exec thetimethen bash
   ```

### On PC 2 (Secondary machine):

1. **Clone from Git:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/thetimethen.git
   cd thetimethen
   ```

2. **Map same network drive:**
   ```powershell
   # Point to PC1's shared folder
   net use Z: \\DESKTOP-PC1\TheTimeThen
   ```

3. **Create .env:**
   ```bash
   copy .env.example .env
   # Use SAME paths as PC1 (if on same network)
   ```

4. **Build and run:**
   ```bash
   docker-compose build
   docker-compose up -d
   docker-compose exec thetimethen bash
   ```

## Daily Workflow

### After Code Changes (on any PC):

```bash
git add .
git commit -m "Description of changes"
git push origin main
```

### Before Running Scripts (on another PC):

```bash
git pull origin main
docker-compose build  # Only if requirements.txt changed
docker-compose down && docker-compose up -d
docker-compose exec thetimethen bash
```

The database is **already there** on shared storage!

## Commands Cheat Sheet

```bash
# Start container
docker-compose up -d

# Enter container shell
docker-compose exec thetimethen bash

# View logs
docker-compose logs -f

# Stop container
docker-compose down

# Rebuild image (after code changes)
docker-compose build

# Run script from host
docker-compose exec thetimethen python auto_extract_historical_photos.py "video.mp4"

# Check volume mounting
docker-compose exec thetimethen df -h /app/data

# Copy file from host to container
docker cp ./myfile.txt thetimethen-dev:/app/

# Copy file from container to host
docker cp thetimethen-dev:/app/output/result.txt ./
```

## If Shared Storage is Too Slow

Use **Syncthing** for local sync instead:

1. Install Syncthing on both PCs
2. Point both to folder: `D:\Dev\TheTimeThen\data`
3. Changes sync automatically in real-time
4. No network share needed

See: https://syncthing.net/

## Troubleshooting

**"Cannot connect to volume" or "Path not found":**
- Verify share is mounted: `net use` (Windows)
- Check path in .env is correct
- Make sure PC1 is online and share is accessible

**"Database is locked":**
- Only one PC should use container at a time
- Or use proper locking in code

**"Permission denied":**
```bash
docker-compose exec thetimethen chmod -R 777 /app/data
```

**Docker image is large:**
- Normal (~4GB for all dependencies)
- Build once, reuse
- Push to Docker Hub to skip rebuild on PC2

## Next Steps

1. Push initial commit to GitHub
2. Test on PC 2 by cloning and building
3. Make a small test change on PC 2, push
4. Pull on PC 1 and verify it works
5. Your setup is ready for daily development!
