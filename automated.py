import subprocess
import sys
import os

def run_script(script_name, args):
    """Run a Python script with the given arguments and return the exit code."""
    try:
        # Construct the command with python executable
        command = [sys.executable, script_name] + args
        print(f"Executing: {' '.join(command)}")
        
        # Run the script and capture output
        result = subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
            encoding='utf-8'  # Ensure UTF-8 encoding for subprocess
        )
        print(f"[SUCCESS] {script_name} completed successfully.")
        print(result.stdout)
        return 0
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to run {script_name}: {e}")
        print(f"STDERR: {e.stderr}")
        print(f"STDOUT: {e.stdout}")
        return e.returncode
    except FileNotFoundError:
        print(f"[ERROR] {script_name} not found.")
        return 1
    except Exception as e:
        print(f"[ERROR] Unexpected error running {script_name}: {e}")
        return 1

def main(output_dir):
    """Run VideoRandomCreate.py and thumbnail.py sequentially with the given output directory."""
    # Validate output directory
    if not os.path.isdir(output_dir):
        print(f"[ERROR] '{output_dir}' is not a valid directory.")
        sys.exit(1)
    
    # Track overall success
    all_success = True
    
    # Run VideoRandomCreate.py with a single output_dir
    video_script = "VideoRandomCreate.py"
    video_args = [output_dir]  # Single argument
    print(f"\nStarting {video_script}...")
    video_result = run_script(video_script, video_args)
    
    if video_result != 0:
        print(f"[WARNING] {video_script} failed with exit code {video_result}. Continuing to next script.")
        all_success = False
    
    # Run thumbnail.py with output_dir
    thumbnail_script = "thumbnail.py"
    thumbnail_args = [output_dir]
    print(f"\nStarting {thumbnail_script}...")
    thumbnail_result = run_script(thumbnail_script, thumbnail_args)
    
    if thumbnail_result != 0:
        print(f"[ERROR] {thumbnail_script} failed with exit code {thumbnail_result}.")
        all_success = False
    
    if all_success:
        print("\n[INFO] All scripts executed successfully.")
    else:
        print("\n[ERROR] One or more scripts failed. Check logs for details.")
        sys.exit(1)