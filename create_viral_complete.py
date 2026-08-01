#!/usr/bin/env python3
"""
Complete viral YouTube video creation pipeline with narration & music.

This is the main entry point that:
1. Creates video with mixed category images
2. Generates AI-powered narration
3. Mixes with background music
4. Outputs final polished video

Full workflow in one command!
"""

import argparse
import os
import sys
import subprocess
from datetime import datetime

def check_dependencies():
    """Check if required Python packages are installed."""
    missing = []
    
    try:
        import PIL
    except:
        missing.append("pillow")
    
    try:
        import numpy
    except:
        missing.append("numpy")
    
    try:
        import imageio
    except:
        missing.append("imageio")
    
    try:
        import edge_tts
    except:
        missing.append("edge-tts")
    
    # FFmpeg is external
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except:
        missing.append("ffmpeg (external tool)")
    
    if missing:
        print("❌ Missing dependencies:")
        for pkg in missing:
            if pkg == "ffmpeg (external tool)":
                print(f"   - {pkg}: Download from https://ffmpeg.org/download.html")
            else:
                print(f"   - {pkg}: pip install {pkg}")
        return False
    
    return True

def run_step(script, args, description):
    """Run a processing step."""
    print(f"\n{'='*80}")
    print(f"📍 Step: {description}")
    print(f"{'='*80}\n")
    
    cmd = [sys.executable, script] + args
    print(f"Running: {' '.join(cmd)}\n")
    
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n❌ Step failed: {description}")
        return False
    
    print(f"✅ Step completed: {description}")
    return True

def main():
    parser = argparse.ArgumentParser(
        description="Create complete viral YouTube video with narration and music"
    )
    parser.add_argument("--outdir", default="viral_final",
                       help="Output directory for final video")
    parser.add_argument("--total", type=int, default=85,
                       help="Number of images (85 = ~20 min)")
    parser.add_argument("--categories", nargs="+",
                       default=["Exploration", "Places", "Historical Events"],
                       help="Image categories to mix")
    parser.add_argument("--music", default=None,
                       help="Background music file path")
    parser.add_argument("--skip-audio", action="store_true",
                       help="Create video only (no narration/music)")
    parser.add_argument("--music-volume", type=float, default=0.3,
                       help="Background music volume (0-1, default: 0.3)")
    
    args = parser.parse_args()
    
    print(f"\n{'='*80}")
    print(f"🎥 VIRAL YOUTUBE VIDEO CREATOR")
    print(f"{'='*80}")
    print(f"Theme: Journeys & Frontiers: The Discovery of Our World")
    print(f"Categories: {', '.join(args.categories)}")
    print(f"Duration: ~20 minutes")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")
    
    # Check dependencies
    print("🔍 Checking dependencies...")
    if not check_dependencies():
        print("\n💡 Install missing packages and try again")
        sys.exit(1)
    print("✅ All dependencies available\n")
    
    # Create output directory
    os.makedirs(args.outdir, exist_ok=True)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    video_script = os.path.join(script_dir, "create_viral_contextual.py")
    audio_script = os.path.join(script_dir, "mix_audio_and_video.py")
    
    # Step 1: Create video with narration generation
    print("STEP 1️⃣  VIDEO & NARRATION GENERATION")
    print("="*80)
    
    video_args = [
        "--categories", *args.categories,
        "--total", str(args.total),
        "--outdir", args.outdir
    ]
    
    if args.skip_audio:
        video_args.append("--skip-audio")
    
    if not run_step(video_script, video_args, 
                    "Generate video with narration audio"):
        print("❌ Video creation failed")
        sys.exit(1)
    
    # Step 2: Mix audio if not skipped
    if not args.skip_audio:
        print("\n\nSTEP 2️⃣  AUDIO MIXING")
        print("="*80)
        
        video_file = os.path.join(args.outdir, "viral_video.mp4")
        narration_dir = os.path.join(args.outdir, "audio_narration")
        final_video = os.path.join(args.outdir, "viral_final_with_audio.mp4")
        
        audio_args = [
            "--video", video_file,
            "--narration", narration_dir,
            "--output", final_video,
            "--music-volume", str(args.music_volume)
        ]
        
        if args.music:
            audio_args.extend(["--music", args.music])
        
        if not run_step(audio_script, audio_args,
                       "Mix narration with background music"):
            print("⚠️  Audio mixing failed, using video without audio")
    
    # Final summary
    print(f"\n\n{'='*80}")
    print(f"✨ VIRAL VIDEO CREATION COMPLETE!")
    print(f"{'='*80}")
    
    if args.skip_audio:
        video_file = os.path.join(args.outdir, "viral_video.mp4")
        if os.path.exists(video_file):
            size_mb = os.path.getsize(video_file) / (1024*1024)
            print(f"📁 Output Video: {video_file}")
            print(f"📊 Size: {size_mb:.1f} MB")
    else:
        final_video = os.path.join(args.outdir, "viral_final_with_audio.mp4")
        if os.path.exists(final_video):
            size_mb = os.path.getsize(final_video) / (1024*1024)
            print(f"📁 Output Video: {final_video}")
            print(f"📊 Size: {size_mb:.1f} MB")
        else:
            video_file = os.path.join(args.outdir, "viral_video.mp4")
            if os.path.exists(video_file):
                size_mb = os.path.getsize(video_file) / (1024*1024)
                print(f"📁 Video (audio TBD): {video_file}")
                print(f"📊 Size: {size_mb:.1f} MB")
    
    print(f"\n📍 Output directory: {args.outdir}")
    print(f"⏱️  Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\n💡 Next steps:")
    print(f"   1. Add background music for full immersion")
    print(f"   2. Upload to YouTube")
    print(f"   3. Share with your audience!")
    print(f"\n🎵 Royalty-free music sources:")
    print(f"   - YouTube Audio Library")
    print(f"   - Free Music Archive (freemusicarchive.org)")
    print(f"   - Incompetech (incompetech.com)")
    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    main()
