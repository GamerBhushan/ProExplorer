# utils.py
import os
import platform
import string
import shutil
import zipfile
import datetime
import concurrent.futures
import subprocess
import uuid
import time

# Global Thread Pool & Task Registry
executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
TASK_REGISTRY = {} 



def get_disk_usage(path):
    """Calculates storage usage for the drive containing 'path'"""
    try:
        total, used, free = shutil.disk_usage(path)
        
        # Convert to GB
        total_gb = total / (1024**3)
        used_gb = used / (1024**3)
        percent = (used / total) * 100
        
        return {
            "total": f"{total_gb:.1f} GB",
            "used": f"{used_gb:.1f} GB",
            "percent": round(percent),
            "free": f"{free / (1024**3):.1f} GB"
        }
    except:
        return {"total": "0 GB", "used": "0 GB", "percent": 0}

def get_system_drives():
    drives = []
    system = platform.system()
    
    if system == 'Windows':
        for letter in string.ascii_uppercase:
            path = f"{letter}:\\"
            if os.path.exists(path):
                drives.append({'name': f"Local Disk ({letter}:)", 'path': path, 'icon': 'fa-hard-drive'})
    else:
        drives.append({'name': 'Root', 'path': '/', 'icon': 'fa-hdd'})
        drives.append({'name': 'Home', 'path': os.path.expanduser("~"), 'icon': 'fa-house-user'})
        if system == 'Linux':
             for mount in ['/media', '/mnt', '/run/media']:
                if os.path.exists(mount):
                    try:
                        for entry in os.listdir(mount):
                            drives.append({'name': entry, 'path': os.path.join(mount, entry), 'icon': 'fa-usb'})
                    except: pass
    return drives

def get_file_info(path):
    try:
        stat = os.stat(path)
        is_dir = os.path.isdir(path)
        size = stat.st_size
        
        # Smart Size
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024: break
            size /= 1024
        size_str = f"{size:.1f} {unit}"

        # Icon & Type Logic
        ext = os.path.splitext(path)[1].lower()
        file_type = "File"
        icon = "fa-file"
        
        if is_dir:
            icon = "fa-folder"
            file_type = "Folder"
        elif ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
            icon = "fa-image"
            file_type = "image"
        elif ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm']:
            icon = "fa-film"
            file_type = "video"
        elif ext in ['.mp3', '.wav']:
            icon = "fa-music"
            file_type = "audio"
        elif ext in ['.zip', '.rar', '.7z', '.tar', '.gz']:
            icon = "fa-file-zipper"
            file_type = "archive"
        elif ext in ['.py', '.js', '.html', '.css', '.json', '.c', '.cpp', '.java']:
            icon = "fa-code"
            file_type = "code"
        elif ext == '.pdf':
            icon = "fa-file-pdf"
            file_type = "pdf"

        return {
            "name": os.path.basename(path),
            "path": path,
            "is_dir": is_dir,
            "size": size_str,
            "raw_size": stat.st_size,
            "mtime": datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
            "icon": icon,
            "type": file_type
        }
    except (FileNotFoundError, PermissionError):
        return None

# --- Background Task Logic ---

def update_task(task_id, progress, status="running", message=""):
    TASK_REGISTRY[task_id] = {'progress': progress, 'status': status, 'message': message}

def bg_zip_folder(task_id, src_path, dest_path):
    try:
        update_task(task_id, 0, "running", "Calculating size...")
        
        total_size = 0
        for root, dirs, files in os.walk(src_path):
            for file in files:
                try: total_size += os.path.getsize(os.path.join(root, file))
                except: pass
        
        # Prevent division by zero for empty folders
        if total_size == 0: total_size = 1

        processed_size = 0
        with zipfile.ZipFile(dest_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(src_path):
                for file in files:
                    abs_path = os.path.join(root, file)
                    rel_path = os.path.relpath(abs_path, os.path.dirname(src_path))
                    zf.write(abs_path, rel_path)
                    
                    processed_size += os.path.getsize(abs_path)
                    progress = int((processed_size / total_size) * 100)
                    update_task(task_id, progress, "running", f"Zipping {file}...")
        
        update_task(task_id, 100, "completed", "Zip created successfully")
    except Exception as e:
        update_task(task_id, 0, "error", str(e))

def bg_copy_move(task_id, mode, src, dest):
    try:
        if mode == 'cut':
            shutil.move(src, dest)
            msg = "Moved"
        else:
            if os.path.isdir(src):
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)
            msg = "Copied"
        update_task(task_id, 100, "completed", f"{msg} successfully")
    except Exception as e:
        update_task(task_id, 0, "error", str(e))

def run_terminal_command(cmd, cwd):
    """Executes a terminal command and returns output"""
    try:
        if not os.path.exists(cwd):
            return {"stderr": "Directory not found", "stdout": ""}

        result = subprocess.run(
            cmd, 
            cwd=cwd, 
            shell=True, 
            capture_output=True, 
            text=True,
            timeout=10
        )
        return {"stdout": result.stdout, "stderr": result.stderr}
    except Exception as e:
        return {"stderr": str(e), "stdout": ""}