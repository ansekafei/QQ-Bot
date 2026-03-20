// web/static/js/app.js
function toggleSidebar() {
    const sidebar = document.getElementById('app-sidebar');
    if(window.innerWidth <= 768) {
        if(sidebar.style.height === 'auto' && sidebar.scrollHeight > 100) sidebar.style.height = '60px'; 
        else sidebar.style.height = 'auto'; 
    } else {
        sidebar.classList.toggle('collapsed');
        localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
    }
}

document.addEventListener("DOMContentLoaded", () => {
    if (window.innerWidth > 768 && localStorage.getItem('sidebarCollapsed') === 'true') document.getElementById('app-sidebar').classList.add('collapsed');
});

window.addEventListener('resize', () => {
    const sidebar = document.getElementById('app-sidebar');
    if (window.innerWidth <= 768) { sidebar.classList.remove('collapsed'); sidebar.style.height = 'auto'; } 
    else { sidebar.style.height = ''; if (localStorage.getItem('sidebarCollapsed') === 'true') sidebar.classList.add('collapsed'); }
});

function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    let iconText = type === 'success' ? '[成功]' : type === 'error' ? '[错误]' : '[提示]';
    toast.innerHTML = `<span>${iconText}</span><span style="word-break: break-all;">${message}</span>`;
    container.appendChild(toast);
    requestAnimationFrame(() => { requestAnimationFrame(() => { toast.classList.add('show'); }); });
    setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 400); }, 3000);
}

function switchTab(id) {
    document.querySelectorAll('.nav-item').forEach(e => e.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(e => e.classList.remove('active'));
    event.currentTarget.classList.add('active');
    document.getElementById(id).classList.add('active');
    
    if(id === 'memory') loadMemory(); 
    if(id === 'env_settings' || id === 'git_sync') loadEnvData();
    if(id === 'stickers') loadStickers(); 
    if(id === 'code_editor') loadFileTree();
    if(id === 'schedule') loadSchedule();
    if(id === 'listen_scope') loadListenTargets();
}

async function safeFetch(url, options = {}) {
    try { const res = await fetch(url, options); if (!res.ok) throw new Error(`HTTP 错误: ${res.status}`); return await res.json(); } 
    catch (err) { showToast(`请求失败 [${url}]: ` + err.message, 'error'); throw err; }
}

async function testApiConnection(btn, gatewayIdx) {
    const originalText = btn.innerHTML;
    btn.disabled = true; btn.innerHTML = `正在探测网关 ${gatewayIdx}...`;
    const data = {
        gateway: gatewayIdx,
        api_key: document.getElementById('env-api-key').value.trim(),
        base_url: document.getElementById('env-base-url').value.trim(),
        api_key_2: document.getElementById('env-api-key-2').value.trim(),
        base_url_2: document.getElementById('env-base-url-2').value.trim()
    };
    try {
        const res = await fetch('/test_api', { method: 'POST', body: JSON.stringify(data) });
        const result = await res.json();
        showToast(result.msg, result.status === 'success' ? 'success' : 'error');
    } catch(e) { showToast("前端请求失败: " + e, 'error'); } 
    finally { btn.disabled = false; btn.innerHTML = originalText; }
}

window.modelsData = { 1: [], 2: [] };

async function loadModels() {
    try {
        const data = await safeFetch('/models');
        window.modelsData[1] = data.models_1 || [];
        window.modelsData[2] = data.models_2 || [];

        const initRow = (id, currentModel, currentGateway) => {
            const gwSel = document.getElementById(id + '-gateway-select');
            if(gwSel) gwSel.value = currentGateway || 1;
            updateModelOptions(id, currentModel);
        };

        initRow('chat', data.chat_model, data.chat_gateway);
        initRow('vision', data.vision_model, data.vision_gateway);
        initRow('summary', data.summary_model, data.summary_gateway);
        initRow('image', data.image_model, data.image_gateway);
        initRow('image_edit', data.image_edit_model, data.image_edit_gateway);
        
    } catch (e) {}
}

function updateModelOptions(target, preselectedModel = null) {
    const gwSel = document.getElementById(target + '-gateway-select');
    const modSel = document.getElementById(target + '-model-select');
    if(!gwSel || !modSel) return;
    
    const gwIdx = parseInt(gwSel.value) || 1;
    const opts = window.modelsData[gwIdx] || [];
    
    const currentSelected = preselectedModel || modSel.value;
    modSel.innerHTML = '';
    
    let hasCurrent = false;
    opts.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m; opt.textContent = m;
        if (m === currentSelected) { opt.selected = true; hasCurrent = true; }
        modSel.appendChild(opt);
    });
    
    if (currentSelected && !hasCurrent) {
        const opt = document.createElement('option');
        opt.value = currentSelected; opt.textContent = currentSelected;
        opt.selected = true;
        modSel.insertBefore(opt, modSel.firstChild);
    }
}

async function refreshModelsList(btn) {
    const origin = btn.innerHTML;
    btn.disabled = true; btn.innerHTML = "拉取双侧通道中...";
    await loadModels();
    showToast("双网关模型列表已同步刷新", "success");
    btn.disabled = false; btn.innerHTML = origin;
}

async function changeModel(target) {
    const m = document.getElementById(target + '-model-select').value;
    const g = parseInt(document.getElementById(target + '-gateway-select').value) || 1;
    await safeFetch('/set_model', { method: 'POST', body: JSON.stringify({ type: target, model: m, gateway: g }) });
    showToast(`已成功将 ${target} 引擎切换为网关 [${g}] 的 [${m}]`);
}

async function loadListenTargets() {
    try {
        const data = await safeFetch('/listen_targets');
        document.getElementById('whitelist-users').value = data.users || "";
        document.getElementById('whitelist-groups').value = data.groups || "";
    } catch(e) {}
}
async function saveListenTargets() {
    const data = { users: document.getElementById('whitelist-users').value, groups: document.getElementById('whitelist-groups').value };
    await safeFetch('/set_listen_targets', { method: 'POST', body: JSON.stringify(data) });
    showToast("监听规则已实时生效！");
}

async function loadProactiveConfig() {
    try {
        const data = await safeFetch('/proactive_config');
        document.getElementById('proactive-enabled').value = data.enabled.toString();
        document.getElementById('proactive-min').value = data.min_hours;
        document.getElementById('proactive-max').value = data.max_hours;
        document.getElementById('dnd-start').value = data.dnd_start;
        document.getElementById('dnd-end').value = data.dnd_end;
    } catch (e) {}
}
async function saveProactiveConfig() {
    const data = {
        enabled: document.getElementById('proactive-enabled').value === 'true',
        min_hours: parseFloat(document.getElementById('proactive-min').value) || 8,
        max_hours: parseFloat(document.getElementById('proactive-max').value) || 16,
        dnd_start: document.getElementById('dnd-start').value,
        dnd_end: document.getElementById('dnd-end').value
    };
    await safeFetch('/set_proactive_config', { method: 'POST', body: JSON.stringify(data) });
    showToast("主动搭话规则已更新生效！");
}

async function loadListenConfig() {
    try {
        const data = await safeFetch('/listen_config');
        document.getElementById('listen-timeout').value = data.timeout;
        document.getElementById('judge-enabled').value = data.judge_enabled.toString();
    } catch (e) {}
}
async function saveListenConfig() {
    const data = { timeout: parseFloat(document.getElementById('listen-timeout').value) || 8, judge_enabled: document.getElementById('judge-enabled').value === 'true' };
    await safeFetch('/set_listen_config', { method: 'POST', body: JSON.stringify(data) });
    showToast("倾听等待与裁判规则已保存！");
}

async function loadSchedule() {
    try {
        const data = await safeFetch('/schedule_data');
        const container = document.getElementById('schedule-container');
        let diaryHtml = "暂无今日日记，等待系统自动生成。";
        if (data.diary) {
            const lines = data.diary.split('\n').filter(line => line.trim() !== '');
            diaryHtml = lines.map(line => {
                const match = line.match(/^[【\[]?(\d{2}[:：]\d{2})[】\]]?\s*(.*)/);
                if (match) return `<div class="timeline-item"><div class="timeline-time">${match[1].replace('：', ':')}</div><div class="timeline-content">${match[2]}</div></div>`;
                return `<div class="timeline-item"><div class="timeline-content">${line}</div></div>`;
            }).join("");
        }
        let html = `<div class="diary-card"><h4 class="diary-card-title">今日时间轴日记</h4><div style="margin-top: 15px;">${diaryHtml}</div></div>`;
        html += `<table class="styled-table"><thead><tr><th style="min-width: 90px;">日期</th><th style="min-width: 70px;">起床</th><th style="min-width: 150px;">穿搭打扮</th><th style="min-width: 200px;">约定的事 / 待办</th></tr></thead><tbody>`;
        
        if(data.history && Object.keys(data.history).length > 0) {
            const dates = Object.keys(data.history).sort((a, b) => b.localeCompare(a));
            dates.forEach(date => {
                const info = data.history[date];
                let promisesHtml = `<span style="color: var(--text-muted); font-size: 13px;">无</span>`;
                if(info.promises && info.promises.length > 0) promisesHtml = info.promises.map(p => `<span class="promise-badge">${p}</span>`).join("");
                html += `<tr><td style="font-family: var(--font-mono); color: var(--text-muted);">${date.substring(5)}</td><td style="color: var(--success); font-weight: bold; font-family: var(--font-mono);">${info.wake_up_time || "-"}</td><td style="color: #d4d4d4; white-space: normal;">${info.outfit || "-"}</td><td style="white-space: normal;">${promisesHtml}</td></tr>`;
            });
        } else { html += `<tr><td colspan="4" style="text-align: center; padding: 30px; color: var(--text-muted);">暂无记录数据</td></tr>`; }
        html += `</tbody></table>`;
        container.innerHTML = html;
    } catch(e) {}
}

async function triggerSchedule(btn) {
    const origin = btn.innerHTML;
    btn.disabled = true; btn.innerHTML = "正在构思生成中...";
    try {
        const result = await safeFetch('/trigger_schedule', { method: 'POST' });
        showToast(result.msg, result.status === 'success' ? 'success' : 'error');
        await loadSchedule();
    } catch (e) {} finally { btn.disabled = false; btn.innerHTML = origin; }
}

async function triggerCleanPromises(btn) {
    const origin = btn.innerHTML;
    btn.disabled = true; btn.innerHTML = "正在分析清理中...";
    try {
        const result = await safeFetch('/trigger_clean_promises', { method: 'POST' });
        showToast(result.msg, result.status === 'success' ? 'success' : 'error');
        await loadSchedule();
    } catch (e) {} finally { btn.disabled = false; btn.innerHTML = origin; }
}

async function loadPromptsList() {
    try {
        const data = await safeFetch('/prompts_list');
        const sel = document.getElementById('prompt-file-selector'); sel.innerHTML = '';
        const memSel = document.getElementById('memory-char-selector'); if(memSel) memSel.innerHTML = '';
        
        data.list.forEach(f => {
            const opt = document.createElement('option'); opt.value = f;
            opt.textContent = f + (f === data.active ? ' (生效中)' : '');
            sel.appendChild(opt);
            
            if(memSel) {
                const optMem = document.createElement('option'); optMem.value = f;
                optMem.textContent = f + (f === data.active ? ' (当前出战角色)' : '');
                memSel.appendChild(optMem);
            }
        });
        sel.value = data.active;
        if(memSel) memSel.value = data.active;
        document.getElementById('prompt-active-status').textContent = `生效中: ${data.active}`;
        loadSpecificPrompt();
        
        if(document.getElementById('memory').classList.contains('active')) loadMemory();
    } catch(e) {}
}

async function loadSpecificPrompt() {
    const filename = document.getElementById('prompt-file-selector').value;
    if(!filename) return;
    try {
        const data = await safeFetch('/read_prompt', { method: 'POST', body: JSON.stringify({filename: filename}) });
        document.getElementById('prompt-editor').value = data.content || '';
    } catch(e){}
}
async function setActivePrompt() {
    const filename = document.getElementById('prompt-file-selector').value;
    if(!filename) return;
    await safeFetch('/set_active_prompt', { method: 'POST', body: JSON.stringify({filename: filename}) });
    showToast("角色卡已切换生效！"); loadPromptsList();
}
async function savePrompt() {
    const p = document.getElementById('prompt-editor').value;
    const filename = document.getElementById('prompt-file-selector').value;
    await safeFetch('/set_prompt', { method: 'POST', body: JSON.stringify({ filename: filename, prompt: p }) });
    showToast("角色卡内容已写入保存！");
}
async function createNewPrompt() {
    const name = prompt("请输入新角色卡的文件名 (无需加 .txt)：", "new_role");
    if(name) {
        await safeFetch('/create_prompt', { method: 'POST', body: JSON.stringify({filename: name}) });
        await loadPromptsList();
        document.getElementById('prompt-file-selector').value = name + (name.endsWith('.txt') ? '' : '.txt');
        loadSpecificPrompt();
    }
}
async function deletePrompt() {
    const filename = document.getElementById('prompt-file-selector').value;
    if(filename === 'default.txt') { showToast("默认底座不可删除！", 'warning'); return; }
    if(confirm(`确定要彻底删除 ${filename} 吗？`)) {
        await safeFetch('/delete_prompt', { method: 'POST', body: JSON.stringify({filename: filename}) });
        showToast("已删除", "success"); loadPromptsList();
    }
}

// 🌟 新增：表情包全选联动逻辑
function toggleEmotionSelect(headerCheckbox, emotion) {
    const checkboxes = document.querySelectorAll(`.sticker-checkbox[data-emotion="${emotion}"]`);
    checkboxes.forEach(cb => cb.checked = headerCheckbox.checked);
}

// 🌟 修改：注入复选框到 DOM
async function loadStickers() {
    try {
        const data = await safeFetch('/stickers_data');
        const container = document.getElementById('sticker-container'); container.innerHTML = '';
        let total = 0;
        for (const [emotion, ids] of Object.entries(data)) {
            if (ids.length === 0) continue;
            total += ids.length;
            let html = `<div style="background: var(--bg-dark); border: 1px solid var(--border-color); padding: 15px; border-radius: 8px;">`;
            
            // 加入全选复选框
            html += `<h4 style="margin-top: 0; margin-bottom: 12px; color: var(--warning); display:flex; justify-content:space-between; align-items:center;">
                        <span>${emotion} <span style="color: var(--text-muted); font-size: 13px;">${ids.length} 张</span></span>
                        <label style="font-size: 12px; cursor: pointer; display: flex; align-items: center; gap: 4px; color: var(--text-main); font-weight: normal;">
                            <input type="checkbox" onclick="toggleEmotionSelect(this, '${emotion}')" style="width: 14px; height: 14px;"> 全选
                        </label>
                     </h4>`;
                     
            html += `<ul style="list-style: none; padding: 0; margin: 0;">`;
            ids.forEach(item => {
                const parts = item.split('|'); const id = parts[0]; const extra = parts.length > 1 ? parts[1] : '';
                let previewHtml = extra.startsWith('http') ? `<img src="${extra}" referrerpolicy="no-referrer" style="width: 40px; height: 40px; object-fit: cover; border-radius: 4px; border: 1px solid #444;" onclick="window.open('${extra}')">` : `<span style="font-size: 20px; width: 40px; display: inline-block; text-align: center;">${extra}</span>`;
                
                // 加入单个复选框
                html += `<li style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px dashed #333; padding: 8px 0;">
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <input type="checkbox" class="sticker-checkbox" data-emotion="${emotion}" data-item="${item}" style="width: 16px; height: 16px; cursor: pointer; flex-shrink: 0; margin: 0;">
                                ${previewHtml}
                                <span title="${id}" style="font-size: 12px; color: #777; font-family: var(--font-mono);">${id.substring(0, 8)}...</span>
                            </div>
                            <button onclick="deleteSticker('${emotion}', '${item}')" class="danger-btn" style="padding: 4px 8px; font-size: 12px; border-radius: 4px; margin-left:0; width: auto !important; min-width: unset;">删除</button>
                         </li>`;
            });
            html += `</ul></div>`; container.innerHTML += html;
        }
        if (total === 0) container.innerHTML = `<div style="color: var(--text-muted);">图鉴空空如也，快去发几个表情包学习吧！</div>`;
    } catch (e) {}
}

async function deleteSticker(emotion, item_string) {
    if(confirm(`确定要把这个从 [${emotion}] 图鉴中删除吗？`)) {
        await safeFetch('/delete_sticker', { method: 'POST', body: JSON.stringify({ emotion: emotion, file_id: item_string }) });
        await loadStickers(); showToast("已移出图鉴");
    }
}

// 🌟 新增：批量删除选中请求
async function deleteSelectedStickers() {
    const checkboxes = document.querySelectorAll('.sticker-checkbox:checked');
    if (checkboxes.length === 0) {
        showToast("请先勾选要删除的表情包", "warning");
        return;
    }
    
    if (confirm(`确定要彻底删除选中的 ${checkboxes.length} 个表情包吗？`)) {
        const itemsToDelete = Array.from(checkboxes).map(cb => ({
            emotion: cb.getAttribute('data-emotion'),
            file_id: cb.getAttribute('data-item')
        }));

        try {
            await safeFetch('/delete_stickers_batch', {
                method: 'POST',
                body: JSON.stringify({ items: itemsToDelete })
            });
            showToast(`成功批量删除 ${checkboxes.length} 个表情包`, "success");
            await loadStickers();
        } catch (e) {
            // safeFetch 内部已经处理了 Toast 弹窗
        }
    }
}

window.currentSelectedFile = "";

async function createNewFile() {
    const filepath = prompt("请输入新建文件的相对路径及文件名\n(例如: bot/tools/new_tool.py 或 test.txt):");
    if(!filepath) return;
    try {
        const res = await fetch('/create_file', { method: 'POST', body: JSON.stringify({filename: filepath}) });
        const data = await res.json();
        if(data.status === 'success') {
            showToast("文件创建成功！");
            await loadFileTree();
            window.currentSelectedFile = filepath;
            document.getElementById('current-edit-file').textContent = window.innerWidth <= 768 ? filepath.split('/').pop() : filepath;
            document.getElementById('code-editor-area').value = "";
        } else { showToast("创建失败：" + data.msg, 'error'); }
    } catch (e) { showToast("网络请求异常", 'error'); }
}

async function loadFileTree() {
    try { const data = await safeFetch('/files_list'); renderFileTree(data.files); } catch (e) {}
}
function renderFileTree(files) {
    const container = document.getElementById('file-tree-container'); container.innerHTML = '';
    const root = {};
    files.forEach(file => {
        const parts = file.split('/'); let current = root;
        for (let i = 0; i < parts.length; i++) {
            const part = parts[i];
            if (!current[part]) { current[part] = (i === parts.length - 1) ? { __path: file } : {}; }
            current = current[part];
        }
    });
    function buildDOM(node, parentEl) {
        const keys = Object.keys(node).filter(k => k !== '__path').sort((a, b) => {
            const aIsDir = !node[a].__path; const bIsDir = !node[b].__path;
            return aIsDir === bIsDir ? a.localeCompare(b) : (aIsDir ? -1 : 1);
        });
        keys.forEach(key => {
            const childNode = node[key];
            if (childNode.__path) {
                const fileEl = document.createElement('div'); fileEl.className = 'tree-file'; fileEl.textContent = key;
                fileEl.onclick = () => {
                    document.querySelectorAll('.tree-file').forEach(el => el.classList.remove('selected'));
                    fileEl.classList.add('selected'); window.currentSelectedFile = childNode.__path;
                    const displayPath = window.innerWidth <= 768 ? childNode.__path.split('/').pop() : childNode.__path;
                    document.getElementById('current-edit-file').textContent = displayPath;
                    loadFileContent(childNode.__path);
                };
                parentEl.appendChild(fileEl);
            } else {
                const folderContainer = document.createElement('div');
                const folderLabel = document.createElement('div'); folderLabel.className = 'tree-folder'; folderLabel.textContent = key;
                const childrenContainer = document.createElement('div'); childrenContainer.className = 'tree-children'; 
                folderLabel.onclick = () => { folderLabel.classList.toggle('open'); childrenContainer.classList.toggle('open'); };
                folderContainer.appendChild(folderLabel); folderContainer.appendChild(childrenContainer); parentEl.appendChild(folderContainer);
                buildDOM(childNode, childrenContainer);
            }
        });
    }
    buildDOM(root, container);
}
async function loadFileContent(filename) {
    const editor = document.getElementById('code-editor-area');
    if(!filename) { editor.value = ''; return; }
    try {
        const res = await fetch('/read_file', { method: 'POST', body: JSON.stringify({filename: filename}) });
        const data = await res.json();
        if(data.status === 'success') { editor.value = data.content; } 
        else { showToast("读取失败：" + data.msg, 'error'); }
    } catch (e) { showToast("读取网络异常", 'error'); }
}

async function saveFile(restart) {
    const filename = window.currentSelectedFile;
    if(!filename) { showToast("请先在上方选择要编辑的文件！", 'warning'); return; }
    const content = document.getElementById('code-editor-area').value;
    try {
        const res = await fetch('/save_file', { method: 'POST', body: JSON.stringify({filename: filename, content: content}) });
        const data = await res.json();
        if(data.status === 'success') {
            if(restart) {
                window.isRestarting = true;
                showToast("保存成功，引擎正在热重启，请等待 10 秒...", "warning");
                await fetch('/restart', { method: 'POST' });
                setTimeout(() => location.reload(), 10000); 
            } else { showToast("代码覆写保存成功！"); }
        } else { showToast("保存失败：" + data.msg, 'error'); }
    } catch (e) { showToast("保存请求异常", 'error'); }
}

document.addEventListener('DOMContentLoaded', () => {
    const textarea = document.getElementById('code-editor-area');
    if(textarea) {
        textarea.addEventListener('keydown', function(e) {
            if (e.key == 'Tab') {
                e.preventDefault(); const start = this.selectionStart; const end = this.selectionEnd;
                this.value = this.value.substring(0, start) + "    " + this.value.substring(end);
                this.selectionStart = this.selectionEnd = start + 4;
            }
        });
    }
});

async function loadEnvData() {
    try {
        const data = await safeFetch('/env_data');
        const proxyInput = document.getElementById('env-git-proxy');
        if(proxyInput) proxyInput.value = data.GIT_PROXY || "";
        
        document.getElementById('env-webui-username').value = data.WEBUI_USERNAME || ""; 
        document.getElementById('env-webui-password').value = data.WEBUI_PASSWORD || "";
        document.getElementById('env-cq-ws-url').value = data.CQ_WS_URL || "ws://napcat:3001";
        document.getElementById('env-cq-token').value = data.CQ_TOKEN || "";
        document.getElementById('env-api-key').value = data.API_KEY || "";
        document.getElementById('env-base-url').value = data.BASE_URL || "http://new-api:3000/v1";
        document.getElementById('env-api-key-2').value = data.API_KEY_2 || "";
        document.getElementById('env-base-url-2').value = data.BASE_URL_2 || "http://llm-gateway:8000/v2";
        document.getElementById('env-serpapi-key').value = data.SERPAPI_KEY || "";
        
        const ghUser = document.getElementById('env-github-username');
        const ghToken = document.getElementById('env-github-token');
        const ghRepo = document.getElementById('env-github-repo');
        if(ghUser) ghUser.value = data.GITHUB_USERNAME || "";
        if(ghToken) ghToken.value = data.GITHUB_TOKEN || "";
        if(ghRepo) ghRepo.value = data.GITHUB_REPO || "";
    } catch (e) {}
}

async function saveEnvData(btn) {
    btn.disabled = true; btn.innerHTML = "持久化保存并重启中...";
    const proxyInput = document.getElementById('env-git-proxy');
    const ghUser = document.getElementById('env-github-username');
    const ghToken = document.getElementById('env-github-token');
    const ghRepo = document.getElementById('env-github-repo');
    
    const envData = {
        GIT_PROXY: proxyInput ? proxyInput.value.trim() : "",
        WEBUI_USERNAME: document.getElementById('env-webui-username').value.trim(), 
        WEBUI_PASSWORD: document.getElementById('env-webui-password').value.trim(),
        CQ_WS_URL: document.getElementById('env-cq-ws-url').value.trim(),
        CQ_TOKEN: document.getElementById('env-cq-token').value.trim(),
        API_KEY: document.getElementById('env-api-key').value.trim(),
        BASE_URL: document.getElementById('env-base-url').value.trim(),
        API_KEY_2: document.getElementById('env-api-key-2').value.trim(),
        BASE_URL_2: document.getElementById('env-base-url-2').value.trim(),
        SERPAPI_KEY: document.getElementById('env-serpapi-key').value.trim(),
        GITHUB_USERNAME: ghUser ? ghUser.value.trim() : "",
        GITHUB_TOKEN: ghToken ? ghToken.value.trim() : "",
        GITHUB_REPO: ghRepo ? ghRepo.value.trim() : ""
    };
    try {
        await fetch('/set_env', { method: 'POST', body: JSON.stringify(envData) });
        window.isRestarting = true;
        showToast("配置与凭证已分离并安全写入，正在重启引擎，请等待 10 秒！", 'success');
        await fetch('/restart', { method: 'POST' });
        setTimeout(() => { location.reload(); }, 10000);
    } catch(e){ showToast("保存失败", 'error'); btn.disabled = false; btn.innerHTML = "保存配置并热重启"; }
}

async function standaloneRestart(btn) {
    if(confirm("确定要立即热重启 AI 核心引擎吗？\n(对话服务会短暂中断)")) {
        btn.disabled = true; btn.innerHTML = "正在重启...";
        try {
            window.isRestarting = true;
            await fetch('/restart', { method: 'POST' });
            showToast("重启指令已下达，请等待 10 秒...", "warning");
            setTimeout(() => { location.reload(); }, 10000);
        } catch(e) { btn.disabled = false; btn.innerHTML = "强制热重启"; }
    }
}

window.isHoveringLogs = false; 
window.logMode = 'compact';
window.isRestarting = false; 

async function loadLogs() {
    if (window.isRestarting) return; 
    if (window.isHoveringLogs || window.getSelection().toString().length > 0) return; 
    await fetchLogs();
}

async function forceLoadLogs() {
    const ul = document.getElementById('logs');
    ul.innerHTML = '<li style="color: #888;">正在切换日志模式，请稍候...</li>';
    await fetchLogs();
}

async function fetchLogs() {
    try {
        const logs = await safeFetch('/logs?mode=' + window.logMode); 
        const ul = document.getElementById('logs'); 
        if (ul.children.length === logs.length && logs.length > 0 && ul.lastChild && ul.lastChild.textContent === logs[logs.length - 1]) return; 
        ul.innerHTML = '';
        logs.forEach(l => { const li = document.createElement('li'); li.textContent = l; ul.appendChild(li); });
        const logBox = document.querySelector('.log-box');
        if (logBox) logBox.scrollTop = logBox.scrollHeight;
    } catch (e) {}
}

function getSelectedMemChar() {
    const sel = document.getElementById('memory-char-selector');
    return sel ? sel.value : "";
}

async function loadMemory() {
    try {
        const charName = getSelectedMemChar();
        const data = await safeFetch('/memory_data', { method: 'POST', body: JSON.stringify({ char_name: charName }) });
        document.getElementById('core-mem-editor').value = data.core || "";
        document.getElementById('short-mem-editor').value = data.short || "[]";
        const longMem = document.getElementById('long-mem-viewer');
        longMem.value = data.long || ""; longMem.scrollTop = longMem.scrollHeight; 
    } catch(e) {}
}

async function saveCoreMemory() {
    const p = document.getElementById('core-mem-editor').value;
    await safeFetch('/set_core_memory', { method: 'POST', body: JSON.stringify({ memory: p, char_name: getSelectedMemChar() }) });
    showToast('核心潜意识写入成功！');
}

async function triggerSummary(btn) {
    const origin = btn.innerHTML;
    btn.disabled = true; btn.innerHTML = "整理中...";
    try {
        const result = await safeFetch('/trigger_summary', { method: 'POST', body: JSON.stringify({ char_name: getSelectedMemChar() }) });
        showToast(result.msg, result.status === 'success' ? 'success' : 'error');
        await loadMemory();
    } catch(e){} finally { btn.disabled = false; btn.innerHTML = origin; }
}

async function saveShortMemory() {
    try {
        const raw = document.getElementById('short-mem-editor').value; JSON.parse(raw); 
        await fetch('/set_memory', { method: 'POST', body: JSON.stringify({ memory: raw, char_name: getSelectedMemChar() }) });
        showToast('短期记忆链覆写成功！');
    } catch (e) { showToast("保存失败！请确保数据是合法的 JSON 格式。", 'error'); }
}

async function clearShortMemory() {
    if(confirm("确定清空短期上下文吗？")) {
        document.getElementById('short-mem-editor').value = "[]"; await saveShortMemory();
    }
}

async function clearLongMemory() {
    if(confirm("警告：此操作将永久清空历史聊天记录流水账！确定继续吗？")) {
        await safeFetch('/clear_long_memory', { method: 'POST', body: JSON.stringify({ char_name: getSelectedMemChar() }) });
        showToast('长期档案已销毁', 'warning'); await loadMemory();
    }
}

async function triggerGit(action, btnElement) {
    let confirmMsg = "";
    let endpoint = "";
    let btnText = "";

    if (action === 'push') {
        confirmMsg = "确定要将当前所有更改同步到云端的 main (迭代) 分支吗？";
        endpoint = '/git_push';
        btnText = '☁️ 同步中...';
    } else if (action === 'publish') {
        confirmMsg = "确定要把当前完美运行的状态，强制发布为云端的 stable (稳定) 分支吗？";
        endpoint = '/git_publish_stable';
        btnText = '🏷️ 发布中...';
    } else if (action === 'restore') {
        confirmMsg = "⚠️ 严重警告：此操作将抹除本地所有未提交的修改，强制将代码覆盖还原为云端的 stable (稳定) 版本！\n\n确定执行吗？";
        endpoint = '/git_restore_stable';
        btnText = '⏪ 恢复覆盖中...';
    } else if (action === 'rollback') {
        confirmMsg = "⚠️ 警告：放弃当前未提交的所有修改，回退到本地代码的上一个纯净状态？";
        endpoint = '/git_rollback';
        btnText = '⏪ 撤销中...';
    }

    if (!confirm(confirmMsg)) return;

    const originText = btnElement.innerHTML;
    btnElement.disabled = true;
    btnElement.innerHTML = btnText;

    try {
        const commitInput = document.getElementById('git-commit-msg');
        const commitMsg = commitInput ? commitInput.value : "";

        const res = await fetch(endpoint, { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(action === 'push' ? { commit_message: commitMsg } : {})
        });
        const data = await res.json();
        
        if (data.status === 'success') {
            showToast(data.msg, 'success');
            if (action === 'push' && commitInput) commitInput.value = ''; 
            if (action === 'restore' || action === 'rollback') {
                await loadFileTree();
                const editor = document.getElementById('code-editor-area');
                if(editor) editor.value = "// 代码结构已发生变更，请从左侧重新选择文件查看。\n// ⚠️ 强烈建议您立即点击下方的【强制热重启】以应用旧版代码引擎。";
                showToast("版本恢复成功，请手动强制热重启系统！", "warning");
            }
        } else {
            alert(data.msg); 
        }
    } catch (e) {
        showToast("Git 引擎请求异常", 'error');
    } finally {
        btnElement.disabled = false; 
        btnElement.innerHTML = originText;
    }
}

window.onload = () => { 
    loadModels(); loadProactiveConfig(); loadListenConfig(); loadPromptsList(); loadLogs(); loadStickers(); loadSchedule(); loadListenTargets();
    setInterval(loadLogs, 1500); 
};