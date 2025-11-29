import os
import sys
import shutil
import zipfile
import io
import platform
import string
import mimetypes
import datetime
import threading
import concurrent.futures
from flask import Flask, Response, render_template_string, request, abort, redirect, url_for, session, flash, jsonify

# ==========================================
# CONFIGURATION & SETUP
# ==========================================

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Thread Pool for heavy I/O operations to prevent blocking
executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

# ==========================================
# CORE UTILITIES
# ==========================================

def get_system_drives():
    """
    Cross-platform drive detection.
    """
    drives = []
    system = platform.system()
    
    if system == 'Windows':
        # Standard Windows Drives
        for letter in string.ascii_uppercase:
            path = f"{letter}:\\"
            if os.path.exists(path):
                drives.append({
                    'name': f"Local Disk ({letter}:)",
                    'path': path,
                    'icon': 'fa-hard-drive'
                })
    else:
        # Linux / Unix / macOS
        drives.append({'name': 'Root (/)', 'path': '/', 'icon': 'fa-hdd'})
        drives.append({'name': 'Home', 'path': os.path.expanduser("~"), 'icon': 'fa-house-user'})
        
        # Attempt to find mounted media on Linux
        for mount_point in ['/media', '/mnt', '/Volumes']:
            if os.path.exists(mount_point):
                try:
                    for entry in os.listdir(mount_point):
                        full_path = os.path.join(mount_point, entry)
                        if os.path.isdir(full_path):
                            drives.append({
                                'name': entry,
                                'path': full_path,
                                'icon': 'fa-usb'
                            })
                except PermissionError:
                    pass
    return drives

def get_file_info(path):
    """
    Returns detailed file info for UI.
    """
    try:
        stat = os.stat(path)
        is_dir = os.path.isdir(path)
        
        # Human readable size
        size = stat.st_size
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                size_str = f"{size:.1f} {unit}"
                break
            size /= 1024
        else:
            size_str = f"{size:.1f} PB"

        # Icon logic
        icon = "fa-file"
        if is_dir:
            icon = "fa-folder"
        else:
            ext = os.path.splitext(path)[1].lower()
            icons = {
                '.py': 'fa-python', '.js': 'fa-js', '.html': 'fa-html5', '.css': 'fa-css3',
                '.jpg': 'fa-image', '.png': 'fa-image', '.gif': 'fa-image',
                '.mp4': 'fa-film', '.mp3': 'fa-music', '.zip': 'fa-file-zipper',
                '.pdf': 'fa-file-pdf', '.txt': 'fa-file-lines', '.exe': 'fa-window-maximize'
            }
            icon = icons.get(ext, 'fa-file')

        return {
            "name": os.path.basename(path),
            "path": path,
            "is_dir": is_dir,
            "size": size_str,
            "mtime": datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
            "icon": icon
        }
    except FileNotFoundError:
        return None

def is_subpath(path, parent):
    """Checks if path is a subpath of parent (for sidebar active state)."""
    try:
        path = os.path.abspath(path)
        parent = os.path.abspath(parent)
        return path == parent or path.startswith(parent + os.sep)
    except:
        return False

# ==========================================
# HTML / CSS / JS TEMPLATE
# ==========================================

TEMPLATE = """
<!doctype html>
<html lang="en" data-theme="light">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ProFileManager</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --bg-app: #f3f4f6;
            --bg-panel: #ffffff;
            --bg-hover: #f1f5f9;
            --bg-selected: #e0e7ff;
            --border-color: #e2e8f0;
            --text-primary: #1e293b;
            --text-secondary: #64748b;
            --accent: #3b82f6;
            --danger: #ef4444;
            --shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);
        }

        [data-theme="dark"] {
            --bg-app: #0f172a;
            --bg-panel: #1e293b;
            --bg-hover: #334155;
            --bg-selected: #1e3a8a;
            --border-color: #334155;
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --shadow: 0 4px 6px -1px rgb(0 0 0 / 0.5);
        }

        * { box-sizing: border-box; outline: none; }
        body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: var(--bg-app); color: var(--text-primary); height: 100vh; overflow: hidden; display: flex; flex-direction: column; }
        a { text-decoration: none; color: inherit; }

        /* --- NAVBAR --- */
        .navbar { height: 60px; background: var(--bg-panel); border-bottom: 1px solid var(--border-color); display: flex; align-items: center; justify-content: space-between; padding: 0 20px; z-index: 10; }
        .brand { font-weight: 700; font-size: 1.2rem; display: flex; align-items: center; gap: 10px; color: var(--accent); }
        .nav-tools { display: flex; gap: 15px; align-items: center; }
        .theme-btn { background: none; border: 1px solid var(--border-color); padding: 8px; border-radius: 8px; cursor: pointer; color: var(--text-primary); transition: 0.2s; }
        .theme-btn:hover { background: var(--bg-hover); }

        /* --- LAYOUT --- */
        .layout { display: flex; flex: 1; overflow: hidden; }
        
        /* --- SIDEBAR --- */
        .sidebar { width: 260px; background: var(--bg-panel); border-right: 1px solid var(--border-color); display: flex; flex-direction: column; overflow-y: auto; transition: transform 0.3s; }
        .sidebar-section { padding: 15px 0; }
        .section-header { padding: 0 20px 10px; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); font-weight: 600; }
        .nav-item { display: flex; align-items: center; gap: 12px; padding: 10px 20px; cursor: pointer; color: var(--text-secondary); transition: 0.15s; font-size: 0.95rem; }
        .nav-item:hover { background-color: var(--bg-hover); color: var(--text-primary); }
        .nav-item.active { background-color: var(--bg-selected); color: var(--accent); border-right: 3px solid var(--accent); }
        .nav-item i { width: 20px; text-align: center; }

        /* --- MAIN CONTENT --- */
        .main { flex: 1; display: flex; flex-direction: column; background: var(--bg-app); position: relative; }
        
        /* Breadcrumbs */
        .address-bar { padding: 10px 20px; background: var(--bg-app); display: flex; gap: 8px; align-items: center; overflow-x: auto; white-space: nowrap; border-bottom: 1px solid var(--border-color); }
        .crumb { padding: 4px 8px; border-radius: 4px; color: var(--text-secondary); font-size: 0.9rem; transition: 0.2s; }
        .crumb:hover { background: var(--bg-hover); color: var(--text-primary); }
        .crumb.current { font-weight: 600; color: var(--text-primary); cursor: default; }
        .separator { color: var(--text-secondary); font-size: 0.8rem; }

        /* File Grid */
        .file-view { flex: 1; padding: 20px; overflow-y: auto; }
        .grid-container { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 15px; }
        
        .file-card { 
            background: transparent; 
            border: 1px solid transparent; 
            border-radius: 8px; 
            padding: 15px 5px; 
            display: flex; 
            flex-direction: column; 
            align-items: center; 
            text-align: center; 
            cursor: pointer; 
            transition: 0.2s; 
            user-select: none;
            position: relative;
        }
        .file-card:hover { background-color: var(--bg-hover); }
        .file-card.selected { background-color: var(--bg-selected); border-color: var(--accent); }
        
        .icon-box { font-size: 2.5rem; margin-bottom: 10px; color: var(--text-secondary); transition: color 0.2s; }
        .file-card.selected .icon-box { color: var(--accent); }
        .icon-box.fa-folder { color: #fbbf24; } /* Folder Color */
        
        .file-name { font-size: 0.85rem; line-height: 1.3; word-break: break-word; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; color: var(--text-primary); }

        /* --- CONTEXT MENU (Right Click) --- */
        .context-menu {
            position: absolute; 
            display: none; 
            background: var(--bg-panel); 
            border: 1px solid var(--border-color); 
            border-radius: 8px; 
            box-shadow: var(--shadow); 
            width: 200px; 
            z-index: 1000; 
            padding: 5px 0;
        }
        .context-item { padding: 8px 15px; font-size: 0.9rem; cursor: pointer; display: flex; align-items: center; gap: 10px; color: var(--text-primary); transition: 0.1s; }
        .context-item:hover { background: var(--accent); color: white; }
        .context-item.danger:hover { background: var(--danger); }
        .context-divider { height: 1px; background: var(--border-color); margin: 4px 0; }

        /* --- FLOATING STATUS / CLIPBOARD --- */
        .status-bar {
            position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%);
            background: var(--text-primary); color: var(--bg-panel);
            padding: 10px 20px; border-radius: 50px; 
            display: flex; align-items: center; gap: 15px; 
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
            z-index: 900;
            opacity: 0; pointer-events: none; transition: 0.3s;
        }
        .status-bar.show { opacity: 1; pointer-events: auto; }
        .status-btn { background: none; border: none; color: inherit; cursor: pointer; font-weight: 600; }
        
        /* --- RESPONSIVE --- */
        @media (max-width: 768px) {
            .sidebar { position: absolute; height: 100%; transform: translateX(-100%); z-index: 50; box-shadow: var(--shadow); }
            .sidebar.open { transform: translateX(0); }
            .grid-container { grid-template-columns: repeat(auto-fill, minmax(90px, 1fr)); }
            .navbar { padding: 0 10px; }
            .address-bar { font-size: 0.8rem; }
        }
    </style>
</head>
<body>

    <div class="navbar">
        <div class="brand">
            <button class="theme-btn" style="border:none; margin-right:10px;" onclick="toggleSidebar()">
                <i class="fa-solid fa-bars"></i>
            </button>
            <i class="fa-solid fa-folder-tree"></i> ProFile
        </div>
        <div class="nav-tools">
            <button class="theme-btn" onclick="toggleTheme()">
                <i id="themeIcon" class="fa-solid fa-moon"></i>
            </button>
        </div>
    </div>

    <div class="layout">
        <div class="sidebar" id="sidebar">
            <div class="sidebar-section">
                <div class="section-header">Drives & Devices</div>
                {% for drive in drives %}
                <a href="{{ url_for('browse', path=drive.path) }}" 
                   class="nav-item {% if current_path.startswith(drive.path) %}active{% endif %}">
                    <i class="fa-solid {{ drive.icon }}"></i>
                    <span>{{ drive.name }}</span>
                </a>
                {% endfor %}
            </div>
            
            <div class="sidebar-section">
                <div class="section-header">Shortcuts</div>
                <a href="{{ url_for('browse', path=home_dir) }}" class="nav-item {% if current_path == home_dir %}active{% endif %}">
                    <i class="fa-solid fa-house"></i> Home
                </a>
            </div>

            {% if clipboard %}
            <div class="sidebar-section">
                <div class="section-header">Clipboard</div>
                <div class="nav-item" style="cursor: default; color: var(--accent);">
                    <i class="fa-solid fa-paste"></i> 
                    <span style="font-size:0.8rem; text-overflow: ellipsis; overflow:hidden; white-space:nowrap;">
                        {{ clipboard.action|upper }}: {{ clipboard.name }}
                    </span>
                </div>
                <div style="padding: 0 20px; display:flex; gap:5px;">
                    <form action="{{ url_for('paste') }}" method="POST" style="width:100%">
                        <input type="hidden" name="dest" value="{{ current_path }}">
                        <button type="submit" class="theme-btn" style="width:100%; font-size:0.8rem; background: var(--accent); color:white; border:none;">Paste Here</button>
                    </form>
                    <form action="{{ url_for('clear_clipboard') }}" method="POST">
                        <input type="hidden" name="ret" value="{{ current_path }}">
                        <button type="submit" class="theme-btn" style="font-size:0.8rem; color: var(--danger); border-color: var(--danger);"><i class="fa-solid fa-xmark"></i></button>
                    </form>
                </div>
            </div>
            {% endif %}
        </div>

        <div class="main" id="mainArea" onclick="deselectAll(event)">
            
            <div class="address-bar">
                {% for crumb in breadcrumbs %}
                    {% if not loop.first %}<span class="separator">/</span>{% endif %}
                    <a href="{{ url_for('browse', path=crumb.path) }}" class="crumb {% if loop.last %}current{% endif %}">
                        {{ crumb.name }}
                    </a>
                {% endfor %}
            </div>

            <div class="file-view">
                <div class="grid-container">
                    {% if parent %}
                    <div class="file-card" ondblclick="window.location.href='{{ url_for('browse', path=parent) }}'">
                        <i class="fa-solid fa-turn-up icon-box"></i>
                        <div class="file-name">..</div>
                    </div>
                    {% endif %}

                    {% for f in files %}
                    <div class="file-card" 
                         data-path="{{ f.path }}" 
                         data-name="{{ f.name }}"
                         data-type="{{ 'folder' if f.is_dir else 'file' }}"
                         onclick="selectItem(this, event)"
                         ondblclick="openItem('{{ f.path }}', {{ 'true' if f.is_dir else 'false' }})"
                         oncontextmenu="showContext(event, this)">
                        <i class="fa-solid {{ f.icon }} icon-box"></i>
                        <div class="file-name">{{ f.name }}</div>
                    </div>
                    {% endfor %}
                </div>
                
                {% if not files and not parent %}
                <div style="text-align:center; margin-top:50px; color: var(--text-secondary);">
                    <i class="fa-regular fa-folder-open" style="font-size:4rem; margin-bottom:15px; opacity:0.5;"></i>
                    <p>This folder is empty</p>
                </div>
                {% endif %}
            </div>

            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                <div class="status-bar show" id="toast" style="background: {% if messages[0][0]=='error' %}var(--danger){% else %}var(--text-primary){% endif %}">
                    <i class="fa-solid fa-info-circle"></i>
                    <span>{{ messages[0][1] }}</span>
                    <button class="status-btn" onclick="document.getElementById('toast').classList.remove('show')">OK</button>
                </div>
                {% endif %}
            {% endwith %}

        </div>
    </div>

    <div class="context-menu" id="contextMenu">
        <div class="context-item" onclick="triggerAction('open')"><i class="fa-solid fa-arrow-up-right-from-square"></i> Open</div>
        <div class="context-divider"></div>
        <div class="context-item" onclick="triggerAction('copy')"><i class="fa-solid fa-copy"></i> Copy</div>
        <div class="context-item" onclick="triggerAction('cut')"><i class="fa-solid fa-scissors"></i> Cut</div>
        <div class="context-divider"></div>
        <div class="context-item" onclick="triggerAction('download')"><i class="fa-solid fa-download"></i> Download</div>
        <div class="context-divider"></div>
        <div class="context-item danger" onclick="triggerAction('delete')"><i class="fa-solid fa-trash"></i> Delete</div>
    </div>

    <form id="actionForm" method="POST" style="display:none;">
        <input type="hidden" name="path" id="formPath">
        <input type="hidden" name="ret" value="{{ current_path }}">
    </form>

    <script>
        let selectedPath = null;
        let selectedIsDir = false;
        const contextMenu = document.getElementById('contextMenu');
        const form = document.getElementById('actionForm');
        const formPath = document.getElementById('formPath');

        // --- Theme Logic ---
        function toggleTheme() {
            const html = document.documentElement;
            const current = html.getAttribute('data-theme');
            const next = current === 'light' ? 'dark' : 'light';
            html.setAttribute('data-theme', next);
            document.getElementById('themeIcon').className = next === 'light' ? 'fa-solid fa-moon' : 'fa-solid fa-sun';
            localStorage.setItem('theme', next);
        }
        (function(){
            const saved = localStorage.getItem('theme') || 'light';
            document.documentElement.setAttribute('data-theme', saved);
            document.getElementById('themeIcon').className = saved === 'light' ? 'fa-solid fa-moon' : 'fa-solid fa-sun';
            // Auto-hide toast
            setTimeout(() => {
                const toast = document.getElementById('toast');
                if(toast) toast.classList.remove('show');
            }, 4000);
        })();

        // --- Sidebar Logic ---
        function toggleSidebar() {
            document.getElementById('sidebar').classList.toggle('open');
        }

        // --- Selection Logic ---
        function deselectAll(e) {
            if (e.target.closest('.file-card') || e.target.closest('.context-menu')) return;
            document.querySelectorAll('.file-card').forEach(el => el.classList.remove('selected'));
            contextMenu.style.display = 'none';
            selectedPath = null;
        }

        function selectItem(el, e) {
            e.stopPropagation();
            document.querySelectorAll('.file-card').forEach(c => c.classList.remove('selected'));
            el.classList.add('selected');
            selectedPath = el.getAttribute('data-path');
            selectedIsDir = el.getAttribute('data-type') === 'folder';
            contextMenu.style.display = 'none';
        }

        function openItem(path, isDir) {
            if(isDir) {
                window.location.href = "{{ url_for('browse') }}?path=" + encodeURIComponent(path);
            } else {
                window.location.href = "{{ url_for('download') }}?path=" + encodeURIComponent(path);
            }
        }

        // --- Context Menu Logic ---
        function showContext(e, el) {
            e.preventDefault();
            e.stopPropagation();
            selectItem(el, e); // Select item first
            
            const menuWidth = 200;
            const menuHeight = 250;
            let x = e.pageX;
            let y = e.pageY;

            if (x + menuWidth > window.innerWidth) x -= menuWidth;
            if (y + menuHeight > window.innerHeight) y -= menuHeight;

            contextMenu.style.left = x + 'px';
            contextMenu.style.top = y + 'px';
            contextMenu.style.display = 'block';
        }

        // --- Action Triggers ---
        function triggerAction(action) {
            if(!selectedPath) return;
            
            formPath.value = selectedPath;

            if (action === 'open') {
                openItem(selectedPath, selectedIsDir);
            } 
            else if (action === 'download') {
                window.location.href = "{{ url_for('download') }}?path=" + encodeURIComponent(selectedPath);
            }
            else if (action === 'delete') {
                if(confirm('Are you sure you want to permanently delete this?')) {
                    form.action = "{{ url_for('delete_item') }}";
                    form.submit();
                }
            }
            else if (action === 'copy' || action === 'cut') {
                form.action = "{{ url_for('clipboard_add') }}?type=" + action;
                form.submit();
            }
            contextMenu.style.display = 'none';
        }

        // Hide context menu on click anywhere else
        document.addEventListener('click', () => {
            contextMenu.style.display = 'none';
        });
    </script>
</body>
</html>
"""

# ==========================================
# BACKEND ROUTES
# ==========================================

@app.route('/')
def index():
    return redirect(url_for('browse', path=os.path.expanduser("~")))

@app.route('/browse')
def browse():
    path = request.args.get('path')
    
    if not path or not os.path.exists(path):
        return redirect(url_for('index'))

    if os.path.isfile(path):
        return redirect(url_for('download', path=path))

    # Breadcrumbs logic
    breadcrumbs = []
    parts = path.split(os.sep)
    current_acc = ""
    
    # Handle Windows vs Linux root
    if platform.system() == 'Windows':
        # parts[0] is "C:"
        pass
    else:
        if path.startswith('/'):
            current_acc = "/"
            breadcrumbs.append({'name': 'Root', 'path': '/'})

    for part in parts:
        if not part: continue
        current_acc = os.path.join(current_acc, part)
        if platform.system() == 'Windows' and len(current_acc) == 2: # Fix C: to C:\
             current_acc += "\\"
        breadcrumbs.append({'name': part, 'path': current_acc})

    files_data = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                info = get_file_info(entry.path)
                if info:
                    files_data.append(info)
    except PermissionError:
        flash("Permission Denied", "error")
        return redirect(url_for('browse', path=os.path.dirname(path)))

    # Sort: Folders first, then alphabetical
    files_data.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

    # Clipboard State
    clipboard = None
    if 'clipboard_path' in session:
        clipboard = {
            'path': session['clipboard_path'],
            'action': session.get('clipboard_action'),
            'name': os.path.basename(session['clipboard_path'])
        }

    return render_template_string(
        TEMPLATE,
        files=files_data,
        current_path=path,
        parent=os.path.dirname(path) if len(path) > 3 else None,
        drives=get_system_drives(),
        home_dir=os.path.expanduser("~"),
        breadcrumbs=breadcrumbs,
        clipboard=clipboard
    )

# ==========================================
# FILE OPERATIONS (Threaded Wrapper)
# ==========================================

@app.route('/download')
def download():
    path = request.args.get('path')
    if not path or not os.path.exists(path):
        abort(404)

    if os.path.isfile(path):
        # Determine MIME
        mime, _ = mimetypes.guess_type(path)
        mime = mime or 'application/octet-stream'
        
        # Stream file generator
        def generate():
            with open(path, "rb") as f:
                while chunk := f.read(4096 * 4): # 16KB chunks
                    yield chunk
        
        return Response(generate(), mimetype=mime, headers={
            "Content-Disposition": f'attachment; filename="{os.path.basename(path)}"'
        })
    
    elif os.path.isdir(path):
        # Zip folder using ThreadPoolExecutor (Simulated synchronous wait for safety in simple app)
        # In a real large-scale app, this would return a task ID. 
        # Here we stream the zip creation.
        
        def zip_stream():
            mem_file = io.BytesIO()
            with zipfile.ZipFile(mem_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(path):
                    for file in files:
                        p = os.path.join(root, file)
                        arcname = os.path.relpath(p, os.path.dirname(path))
                        try:
                            zf.write(p, arcname)
                        except: pass
            mem_file.seek(0)
            while chunk := mem_file.read(4096):
                yield chunk
                
        return Response(zip_stream(), mimetype="application/zip", headers={
            "Content-Disposition": f'attachment; filename="{os.path.basename(path)}.zip"'
        })

@app.route('/action/clipboard_add', methods=['POST'])
def clipboard_add():
    path = request.form.get('path')
    action_type = request.args.get('type') # copy or cut
    ret = request.form.get('ret')
    
    session['clipboard_path'] = path
    session['clipboard_action'] = action_type
    
    flash(f"Selected for {action_type}: {os.path.basename(path)}", "info")
    return redirect(url_for('browse', path=ret))

@app.route('/action/clear_clipboard', methods=['POST'])
def clear_clipboard():
    session.pop('clipboard_path', None)
    session.pop('clipboard_action', None)
    return redirect(url_for('browse', path=request.form.get('ret')))

@app.route('/action/paste', methods=['POST'])
def paste():
    src = session.get('clipboard_path')
    action = session.get('clipboard_action')
    dest_dir = request.form.get('dest')
    
    if not src or not os.path.exists(src):
        flash("Source not found", "error")
        return redirect(url_for('browse', path=dest_dir))

    dest_path = os.path.join(dest_dir, os.path.basename(src))
    
    # Rename if exists
    if os.path.exists(dest_path):
        base, ext = os.path.splitext(os.path.basename(src))
        dest_path = os.path.join(dest_dir, f"{base}_copy{ext}")

    # Define thread function
    def run_paste():
        try:
            if action == 'cut':
                shutil.move(src, dest_path)
            else:
                if os.path.isdir(src):
                    shutil.copytree(src, dest_path)
                else:
                    shutil.copy2(src, dest_path)
        except Exception as e:
            print(f"Paste error: {e}")

    # Submit to thread pool
    future = executor.submit(run_paste)
    
    # Wait for completion (simplifies UI logic for this single-file script)
    # If this was a huge file, we would use AJAX polling, but requested "Simple File"
    future.result() 

    if action == 'cut':
        session.pop('clipboard_path', None)

    flash("File operation completed", "success")
    return redirect(url_for('browse', path=dest_dir))

@app.route('/action/delete', methods=['POST'])
def delete_item():
    path = request.form.get('path')
    ret = request.form.get('ret')
    
    def run_delete():
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except: pass

    future = executor.submit(run_delete)
    future.result()
    
    flash("Item deleted", "success")
    return redirect(url_for('browse', path=ret))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"--- ProFileManager Started on http://localhost:{port} ---")
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)