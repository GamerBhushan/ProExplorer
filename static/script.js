// script.js
class AppState {
    constructor() {
        this.tabs = [];
        this.activeTabId = null;
        this.clipboard = null; 
        this.selectedFile = null;
        this.rightClickedTabId = null; // Track which tab was right-clicked
        
        // Init
        this.addTab(); // This loads drives automatically via navigate -> loadDrives call removed from ctor to avoid double fetch
        this.setupTerminal();
    }

    // --- Tab System ---
    addTab(path = null) {
        const id = 'tab_' + Date.now();
        const tab = { id, path: path || 'Home', name: 'Home' };
        this.tabs.push(tab);
        this.renderTabs();
        this.activateTab(id, path);
    }

    closeTab(id, e) {
        if(e) e.stopPropagation();
        if(this.tabs.length <= 1) return;
        
        const idx = this.tabs.findIndex(t => t.id === id);
        this.tabs.splice(idx, 1);
        
        if(this.activeTabId === id) {
            const next = this.tabs[idx] || this.tabs[idx-1];
            this.activeTabId = next.id;
            this.navigate(next.path, false); // Don't refresh UI fully, just switch state
        }
        this.renderTabs();
    }

    activateTab(id, pathOverride = null) {
        this.activeTabId = id;
        this.renderTabs();
        
        const tab = this.tabs.find(t => t.id === id);
        this.navigate(pathOverride || tab.path);
    }

    renderTabs() {
        const strip = document.getElementById('tabStrip');
        strip.innerHTML = '';
        this.tabs.forEach(t => {
            const el = document.createElement('div');
            el.className = `tab ${t.id === this.activeTabId ? 'active' : ''}`;
            el.innerHTML = `<span>${t.name}</span> <i class="fa-solid fa-xmark" onclick="app.closeTab('${t.id}', event)"></i>`;
            
            // Left click to select
            el.onclick = () => this.activateTab(t.id);
            
            // Right click context menu
            el.oncontextmenu = (e) => {
                e.preventDefault();
                this.rightClickedTabId = t.id;
                showTabContextMenu(e);
            };
            
            strip.appendChild(el);
        });
        
        const add = document.createElement('button');
        add.className = 'icon-btn';
        add.innerHTML = '<i class="fa-solid fa-plus"></i>';
        add.onclick = () => this.addTab();
        strip.appendChild(add);
    }

    // --- Tab Actions (Context Menu) ---
    tabAction(action) {
        document.getElementById('tabContextMenu').style.display = 'none';
        const targetId = this.rightClickedTabId;

        if (action === 'close') {
            this.closeTab(targetId, null);
        }
        else if (action === 'close-others') {
            this.tabs = this.tabs.filter(t => t.id === targetId);
            this.activateTab(targetId);
        }
        else if (action === 'close-all') {
            // Reset to a single new Home tab
            this.tabs = [];
            this.addTab();
        }
    }

    // --- Navigation ---
    async navigate(path, updateUI = true) {
        const url = path && path !== 'Home' ? `/api/browse?path=${encodeURIComponent(path)}` : '/api/browse';
        
        try {
            const res = await fetch(url);
            const data = await res.json();
            
            if(data.error) {
                this.showToast("Error: " + data.error);
                return;
            }

            // Update Tab State
            const tab = this.tabs.find(t => t.id === this.activeTabId);
            if(tab) {
                tab.path = data.current_path;
                tab.name = data.current_path === data.parent ? 'Root' : data.current_path.split(/[\\/]/).pop() || 'Drive';
            }

            if(updateUI) {
                this.renderTabs();
                this.renderBreadcrumbs(data.breadcrumbs);
                this.renderFiles(data.files, data.parent);
                this.updateSidebar(data.drives, data.current_path);
                this.updateStorage(data.storage);
            }

        } catch(e) { console.error(e); }
    }

    updateSidebar(drives, currentPath) {
        const list = document.getElementById('driveList');
        // Only rebuild if empty or changed (optimization)
        if(list.children.length === 0 || list.children.length !== drives.length) {
            list.innerHTML = '';
            drives.forEach(d => {
                const div = document.createElement('div');
                div.className = 'nav-item';
                div.innerHTML = `<i class="fa-solid ${d.icon}"></i> ${d.name}`;
                div.onclick = () => this.navigate(d.path);
                div.setAttribute('data-path', d.path); 
                list.appendChild(div);
            });
        }
        
        // Update Highlighting
        document.querySelectorAll('.nav-item').forEach(el => {
            el.classList.remove('active');
            const dPath = el.getAttribute('data-path');
            if(dPath && currentPath.startsWith(dPath)) {
                el.classList.add('active');
            }
        });
    }

    updateStorage(data) {
        if(!data) return;
        const fill = document.getElementById('storageFill');
        const text = document.getElementById('storageText');
        fill.style.width = `${data.percent}%`;
        
        // Color coding based on usage
        if (data.percent > 90) fill.style.backgroundColor = '#d93025'; // Red
        else fill.style.backgroundColor = 'var(--primary)';

        text.innerText = `${data.used} used of ${data.total}`;
    }

    renderFiles(files, parent) {
        const grid = document.getElementById('fileGrid');
        grid.innerHTML = '';

        if(parent) {
            const back = document.createElement('div');
            back.className = 'file-card';
            back.innerHTML = `<div class="file-icon"><i class="fa-solid fa-arrow-turn-up"></i></div><div class="file-name">..</div>`;
            back.ondblclick = () => this.navigate(parent);
            // Right click on ".." shows create options/paste, not file options
            back.oncontextmenu = (e) => { e.stopPropagation(); showContextMenu(e, null); };
            grid.appendChild(back);
        }

        files.forEach(f => {
            const el = document.createElement('div');
            el.className = 'file-card';
            el.innerHTML = `<div class="file-icon"><i class="fa-solid ${f.icon}"></i></div><div class="file-name">${f.name}</div>`;
            
            el.onclick = (e) => {
                e.stopPropagation();
                document.querySelectorAll('.file-card').forEach(c => c.classList.remove('selected'));
                el.classList.add('selected');
                this.selectedFile = f;
            };

            el.ondblclick = () => f.is_dir ? this.navigate(f.path) : this.openFile(f);
            el.oncontextmenu = (e) => showContextMenu(e, f);
            
            grid.appendChild(el);
        });
    }

    renderBreadcrumbs(crumbs) {
        const bc = document.getElementById('breadcrumbs');
        bc.innerHTML = '';
        crumbs.forEach((c, i) => {
            if(i > 0) bc.innerHTML += '<i class="fa-solid fa-angle-right" style="font-size:12px; color:var(--text-sub); margin:0 5px;"></i>';
            const sp = document.createElement('span');
            sp.className = 'crumb';
            sp.innerText = c.name;
            // Explicitly bind the path to the click
            sp.onclick = () => { console.log("Nav to", c.path); this.navigate(c.path); };
            bc.appendChild(sp);
        });
    }

    // --- Actions ---
    openFile(file) {
        const encoded = encodeURIComponent(file.path);
        if(file.type === 'video') {
            document.getElementById('mediaContainer').innerHTML = `
                <video controls autoplay style="max-width:100%; max-height:80vh;">
                    <source src="/download?path=${encoded}&inline=true" type="video/mp4">
                </video>`;
            document.getElementById('mediaModal').style.display = 'flex';
        } else if(file.type === 'image') {
            document.getElementById('mediaContainer').innerHTML = `<img src="/download?path=${encoded}&inline=true" style="max-width:100%; max-height:90vh;">`;
            document.getElementById('mediaModal').style.display = 'flex';
        } else {
            window.location.href = `/download?path=${encoded}`;
        }
    }

    ctxAction(action) {
        document.getElementById('contextMenu').style.display = 'none';
        
        if (action === 'paste') {
            if(!this.clipboard) return;
            const currentTab = this.tabs.find(t => t.id === this.activeTabId);
            this.apiPost('/api/action', {
                cmd: 'paste', src: this.clipboard.path, dest: currentTab.path, mode: this.clipboard.mode
            }, (res) => {
                 if(res.task_id) this.trackTask(res.task_id, "Pasting...");
                 if(this.clipboard.mode === 'cut') this.clipboard = null;
            });
            return;
        }

        const file = this.selectedFile;
        if (!file) return;

        if(action === 'copy' || action === 'cut') {
            this.clipboard = { path: file.path, mode: action };
            this.showToast(`${action === 'copy' ? 'Copied' : 'Cut'} ${file.name}`);
        } else if(action === 'delete') {
            if(confirm('Delete ' + file.name + '?')) {
                this.apiPost('/api/action', { cmd: 'delete', src: file.path }, () => this.refresh());
            }
        } else if(action === 'zip') {
            this.apiPost('/api/action', { cmd: 'zip', src: file.path }, (res) => {
                if(res.task_id) this.trackTask(res.task_id, "Zipping...");
            });
        } else if(action === 'download') {
            window.location.href = `/download?path=${encodeURIComponent(file.path)}`;
        } else if(action === 'open') {
            file.is_dir ? this.navigate(file.path) : this.openFile(file);
        }
    }

    create(type) {
        document.getElementById('createMenu').style.display = 'none';
        const name = prompt(`Enter ${type} name:`);
        if(!name) return;
        const currentPath = this.tabs.find(t => t.id === this.activeTabId).path;
        
        this.apiPost('/api/action', {
            cmd: type === 'folder' ? 'create_folder' : 'create_file',
            path: currentPath, name: name
        }, () => this.refresh());
    }

    // ... (Keep apiPost, setupTerminal, trackTask, showToast, toggleTheme) ...
    async apiPost(url, body, cb) {
        try {
            const res = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
            const data = await res.json();
            if(cb) cb(data);
        } catch(e) { console.error(e); }
    }

    setupTerminal() {
        const input = document.getElementById('termInput');
        input.addEventListener('keypress', async (e) => {
            if(e.key === 'Enter') {
                const cmd = input.value;
                const outDiv = document.getElementById('termOutput');
                outDiv.innerHTML += `<div><span style="color:#0f0">$</span> ${cmd}</div>`;
                input.value = '';
                const cwd = this.tabs.find(t => t.id === this.activeTabId).path;
                const res = await fetch('/api/terminal', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ cmd, cwd })
                });
                const data = await res.json();
                if(data.stdout) outDiv.innerHTML += `<div>${data.stdout}</div>`;
                if(data.stderr) outDiv.innerHTML += `<div style="color:var(--danger)">${data.stderr}</div>`;
                outDiv.scrollTop = outDiv.scrollHeight;
            }
        });
    }

    trackTask(taskId, label) {
        this.showToast(`${label} started...`);
        const interval = setInterval(async () => {
            const res = await fetch(`/api/task/${taskId}`);
            const data = await res.json();
            if(data.status === 'completed') {
                clearInterval(interval);
                this.showToast(`${label} Completed!`);
                this.refresh();
            } else if(data.status === 'error') {
                clearInterval(interval);
                this.showToast("Error: " + data.message);
            }
        }, 1000);
    }

    showToast(msg) {
        const t = document.createElement('div');
        t.style.cssText = `position:fixed; bottom:30px; left:50%; transform:translateX(-50%); background:var(--text-main); color:var(--bg-app); padding:12px 24px; border-radius:30px; font-size:14px; font-weight:500; box-shadow: 0 4px 12px rgba(0,0,0,0.2); z-index:5000;`;
        t.innerText = msg;
        document.body.appendChild(t);
        setTimeout(() => t.remove(), 3000);
    }
    
    // Feature: Open Terminal
    openTerminal() {
        document.getElementById('terminalOverlay').style.display = 'flex';
        document.getElementById('termInput').focus();
    }
    
    toggleTheme() {
        const html = document.documentElement;
        html.setAttribute('data-theme', html.getAttribute('data-theme') === 'light' ? 'dark' : 'light');
    }
}

// --- GLOBAL UI HANDLERS ---

function showContextMenu(e, file, isCreate = false) {
    e.preventDefault();
    e.stopPropagation();
    
    // Hide all menus first
    document.querySelectorAll('.context-menu').forEach(m => m.style.display = 'none');

    // "New" Button Logic
    if (isCreate) {
        const menu = document.getElementById('createMenu');
        // Position relative to click target (button) or mouse if provided
        const rect = e.target.getBoundingClientRect();
        menu.style.left = `${rect.left}px`;
        menu.style.top = `${rect.bottom + 5}px`;
        menu.style.display = 'block';
        return;
    }

    // Main File/Space Menu Logic
    const menu = document.getElementById('contextMenu');
    let x = e.pageX;
    let y = e.pageY;
    if (x + 200 > window.innerWidth) x = window.innerWidth - 210;
    if (y + 300 > window.innerHeight) y = window.innerHeight - 310;
    
    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    menu.style.display = 'block';

    if (file) {
        // Right-clicked a file
        app.selectedFile = file;
        document.getElementById('file-options').style.display = 'block';
    } else {
        // Right-clicked empty space
        app.selectedFile = null;
        document.getElementById('file-options').style.display = 'none';
    }

    // Show paste if clipboard has something
    document.getElementById('paste-option').style.display = app.clipboard ? 'block' : 'none';
}

function showTabContextMenu(e) {
    e.preventDefault();
    document.querySelectorAll('.context-menu').forEach(m => m.style.display = 'none');
    
    const menu = document.getElementById('tabContextMenu');
    menu.style.left = `${e.pageX}px`;
    menu.style.top = `${e.pageY}px`;
    menu.style.display = 'block';
}

function handleAreaContext(e) {
    if(e.target.closest('.file-card')) return; 
    showContextMenu(e, null); 
}

function closeMedia() {
    document.getElementById('mediaModal').style.display = 'none';
    document.getElementById('mediaContainer').innerHTML = ''; 
}

document.addEventListener('click', () => {
    document.querySelectorAll('.context-menu').forEach(m => m.style.display = 'none');
});

const app = new AppState();