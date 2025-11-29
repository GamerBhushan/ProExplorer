# routes.py
from flask import Blueprint, render_template, request, jsonify, Response, abort
import utils
import os
import mimetypes
import time

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    return render_template('index.html')

@bp.route('/api/browse')
def api_browse():
    path = request.args.get('path') or os.path.expanduser("~")
    
    if not os.path.exists(path):
        return jsonify({"error": "Path not found"}), 404

    # Breadcrumbs
    parts = path.split(os.sep)
    breadcrumbs = []
    acc = ""
    if utils.platform.system() != 'Windows':
        if path.startswith('/'):
            acc = "/"
            breadcrumbs.append({'name': 'Root', 'path': '/'})
    
    for part in parts:
        if not part: continue
        acc = os.path.join(acc, part)
        if utils.platform.system() == 'Windows' and len(acc)==2: acc += "\\"
        breadcrumbs.append({'name': part, 'path': acc})

    # Files
    files = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                info = utils.get_file_info(entry.path)
                if info: files.append(info)
    except PermissionError:
        return jsonify({"error": "Permission Denied"}), 403

    files.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

    # NEW: Get Storage Info for this path
    storage = utils.get_disk_usage(path)

    return jsonify({
        "current_path": path,
        "parent": os.path.dirname(path) if len(path) > 3 else None,
        "breadcrumbs": breadcrumbs,
        "drives": utils.get_system_drives(),
        "files": files,
        "storage": storage  # Sending storage data
    })


@bp.route('/download')
def download():
    path = request.args.get('path')
    inline = request.args.get('inline', 'false') == 'true'
    
    if not path or not os.path.exists(path): return abort(404)

    if os.path.isfile(path):
        size = os.path.getsize(path)
        mime, _ = mimetypes.guess_type(path)
        
        # Resumable Download Logic
        range_header = request.headers.get('Range', None)
        if range_header:
            byte1, byte2 = range_header.replace('bytes=', '').split('-')
            byte1 = int(byte1)
            byte2 = int(byte2) if byte2 else size - 1
            length = byte2 - byte1 + 1

            def stream_range():
                with open(path, 'rb') as f:
                    f.seek(byte1)
                    yield f.read(length)
            
            resp = Response(stream_range(), 206, mimetype=mime, direct_passthrough=True)
            resp.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{size}')
        else:
            def stream_file():
                with open(path, 'rb') as f:
                    while chunk := f.read(65536): yield chunk
            resp = Response(stream_file(), mimetype=mime)

        disposition = 'inline' if inline else f'attachment; filename="{os.path.basename(path)}"'
        resp.headers.add('Content-Disposition', disposition)
        resp.headers.add('Content-Length', str(size))
        resp.headers.add('Accept-Ranges', 'bytes')
        return resp
    
    return abort(400)

@bp.route('/api/action', methods=['POST'])
def action():
    data = request.json
    cmd = data.get('cmd')
    src = data.get('src')
    
    try:
        if cmd == 'delete':
            utils.executor.submit(utils.background_delete, src)
            return jsonify({"status": "deleted"})
        
        elif cmd == 'create_folder':
            os.makedirs(os.path.join(data.get('path'), data.get('name')), exist_ok=True)
            return jsonify({"status": "ok"})
            
        elif cmd == 'create_file':
            with open(os.path.join(data.get('path'), data.get('name')), 'w') as f: pass
            return jsonify({"status": "ok"})

        elif cmd == 'paste':
            dest = data.get('dest')
            mode = data.get('mode')
            fname = os.path.basename(src)
            final_path = os.path.join(dest, fname)
            
            # Auto-rename logic for conflicts
            if os.path.exists(final_path):
                base, ext = os.path.splitext(fname)
                final_path = os.path.join(dest, f"{base}_{int(time.time())}{ext}")

            task_id = str(uuid.uuid4())
            utils.executor.submit(utils.bg_copy_move, task_id, mode, src, final_path)
            return jsonify({"status": "started", "task_id": task_id})
        
        elif cmd == 'zip':
            dest_folder = os.path.dirname(src)
            zip_name = f"{os.path.basename(src)}.zip"
            zip_path = os.path.join(dest_folder, zip_name)
            
            task_id = str(uuid.uuid4())
            utils.executor.submit(utils.bg_zip_folder, task_id, src, zip_path)
            return jsonify({"status": "started", "task_id": task_id})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    return jsonify({"status": "ok"})

@bp.route('/api/task/<task_id>')
def check_task(task_id):
    task = utils.TASK_REGISTRY.get(task_id)
    if not task: return jsonify({"status": "unknown"}), 404
    return jsonify(task)

@bp.route('/api/terminal', methods=['POST'])
def terminal_exec():
    data = request.json
    cwd = data.get('cwd')
    cmd = data.get('cmd')
    output = utils.run_terminal_command(cmd, cwd)
    return jsonify(output)