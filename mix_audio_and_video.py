#!/usr/bin/env python3
"""
Audio mixing utility: Combines TTS narration with background music and video.

This script:
1. Takes individual narration audio files
2. Concatenates them into a single narration track
3. Mixes with background music (at lower volume)
4. Combines final audio with video

Usage:
    python mix_audio_and_video.py --video viral_video.mp4 --narration audio_narration/ --music background.mp3 --output final_video.mp4
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

def get_ffmpeg_path():
    """Get FFmpeg path (tries to find in system)."""
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return 'ffmpeg'
    except:
        # Try common paths
        paths = [
            "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
            "C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe",
            "ffmpeg"
        ]
        for path in paths:
            if os.path.exists(path):
                return path
        return None

def concatenate_audio_files(audio_files, output_file):
    """Concatenate multiple audio files into one."""
    if not audio_files:
        print("❌ No audio files to concatenate")
        return False
    
    # Create concat file list
    concat_file = output_file + ".concat.txt"
    with open(concat_file, 'w') as f:
        for audio in audio_files:
            if os.path.exists(audio):
                f.write(f"file '{os.path.abspath(audio)}'\n")
    
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        print("❌ FFmpeg not found. Install from: https://ffmpeg.org/download.html")
        return False
    
    print(f"🎵 Concatenating {len(audio_files)} audio segments...")
    try:
        result = subprocess.run([
            ffmpeg, '-f', 'concat', '-safe', '0',
            '-i', concat_file,
            '-c', 'copy',
            output_file
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ Narration concatenated: {output_file}")
            os.remove(concat_file)
            return True
        else:
            print(f"❌ FFmpeg error: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error concatenating audio: {e}")
        return False

def mix_narration_and_music(narration_file, music_file, output_file, music_volume=0.3):
    """Mix narration (foreground) with background music (softer)."""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        print("❌ FFmpeg not found")
        return False
    
    print(f"🎵 Mixing narration with background music...")
    try:
        result = subprocess.run([
            ffmpeg,
            '-i', narration_file,
            '-i', music_file,
            '-filter_complex',
            f'[0]aformat=sample_rates=44100:channel_layouts=stereo[a1];'
            f'[1]aformat=sample_rates=44100:channel_layouts=stereo,volume={music_volume}[a2];'
            f'[a1][a2]amix=inputs=2:duration=first[out]',
            '-map', '[out]',
            '-c:a', 'aac',
            output_file
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ Audio mixed: {output_file}")
            return True
        else:
            print(f"❌ FFmpeg error: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error mixing audio: {e}")
        return False

def combine_video_and_audio(video_file, audio_file, output_file):
    """Combine video with audio track."""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        print("❌ FFmpeg not found")
        return False
    
    print(f"🎬 Combining video with audio...")
    try:
        result = subprocess.run([
            ffmpeg,
            '-i', video_file,
            '-i', audio_file,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-map', '0:v:0',
            '-map', '1:a:0',
            output_file
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ Final video created: {output_file}")
            return True
        else:
            print(f"❌ FFmpeg error: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error combining video and audio: {e}")
        return False

def create_silent_audio(duration_seconds, output_file):
    """Create a silent MP3 file."""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        print("❌ FFmpeg not found")
        return False
    
    try:
        result = subprocess.run([
            ffmpeg,
            '-f', 'lavfi', '-i', f'anullsrc=r=44100:cl=stereo',
            '-t', str(duration_seconds),
            '-q:a', '9',
            '-acodec', 'libmp3lame',
            output_file
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            return True
        return False
    except:
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Mix narration audio with background music and combine with video"
    )
    parser.add_argument("--video", required=True,
                       help="Input video file (viral_video.mp4)")
    parser.add_argument("--narration", required=True,
                       help="Directory with narration files or single narration file")
    parser.add_argument("--music", default=None,
                       help="Background music file (optional)")
    parser.add_argument("--output", default="final_viral_video.mp4",
                       help="Output video file")
    parser.add_argument("--music-volume", type=float, default=0.3,
                       help="Background music volume (0.0-1.0, default: 0.3 = 30%)")
    
    args = parser.parse_args()
    
    # Validate inputs
    if not os.path.exists(args.video):
        print(f"❌ Video file not found: {args.video}")
        sys.exit(1)
    
    print(f"\n{'='*80}")
    print(f"🎵 Audio Mixing & Video Finalization")
    print(f"{'='*80}")
    print(f"🎬 Video:   {args.video}")
    print(f"🎙️  Narration: {args.narration}")
    print(f"🎵 Music:   {args.music if args.music else '(none)'}")
    print(f"📁 Output:  {args.output}")
    print(f"{'='*80}\n")
    
    # Get audio files
    narration_dir = args.narration
    audio_files = []
    
    if os.path.isdir(narration_dir):
        audio_files = sorted([
            os.path.join(narration_dir, f) 
            for f in os.listdir(narration_dir)
            if f.endswith(('.mp3', '.wav', '.aac', '.m4a'))
        ])
        if not audio_files:
            print(f"❌ No audio files found in: {narration_dir}")
            sys.exit(1)
        print(f"📂 Found {len(audio_files)} narration segments")
    elif os.path.isfile(narration_dir):
        audio_files = [narration_dir]
        print(f"📂 Using single narration file")
    else:
        print(f"❌ Narration path not found: {narration_dir}")
        sys.exit(1)
    
    # Create temp directory
    temp_dir = os.path.join(os.path.dirname(args.output), ".temp_audio")
    os.makedirs(temp_dir, exist_ok=True)
    
    # Step 1: Concatenate narration files
    full_narration = os.path.join(temp_dir, "narration_full.mp3")
    if len(audio_files) > 1:
        if not concatenate_audio_files(audio_files, full_narration):
            print("❌ Failed to concatenate audio")
            sys.exit(1)
    else:
        full_narration = audio_files[0]
    
    # Step 2: Mix with background music if provided
    final_audio = full_narration
    if args.music and os.path.exists(args.music):
        mixed_audio = os.path.join(temp_dir, "mixed_audio.mp3")
        if not mix_narration_and_music(full_narration, args.music, mixed_audio, args.music_volume):
            print("⚠️  Failed to mix audio, using narration only")
        else:
            final_audio = mixed_audio
    else:
        if args.music:
            print(f"⚠️  Music file not found: {args.music}")
        else:
            print(f"ℹ️  No background music file provided")
    
    # Step 3: Combine video and audio
    if not combine_video_and_audio(args.video, final_audio, args.output):
        print("❌ Failed to create final video")
        sys.exit(1)
    
    # Cleanup
    if os.path.exists(temp_dir):
        import shutil
        shutil.rmtree(temp_dir)
    
    print(f"\n{'='*80}")
    print(f"✨ Final video ready!")
    print(f"   Output: {args.output}")
    if os.path.exists(args.output):
        size_mb = os.path.getsize(args.output) / (1024*1024)
        print(f"   Size: {size_mb:.1f} MB")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
