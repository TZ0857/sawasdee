// === Gatherings Page ===
requireAuth();

const TYPE_LABELS = {
    meal: '🍜 飯局',
    karaoke: '🎤 KTV',
    drinks: '🥂 小酌',
    coffee: '☕ 咖啡',
    movie: '🎬 電影',
    nightlife: '🌙 夜生活',
    travel: '✈️ 旅行',
};

let currentTab = 'explore';
let currentType = '';
let countdownInterval = null;

// === Load gatherings ===
async function loadGatherings() {
    const grid = document.getElementById('gatheringGrid');
    const empty = document.getElementById('gatheringEmpty');
    grid.innerHTML = '<div class="flex-center" style="grid-column:1/-1;padding:4rem;"><div class="spinner"></div></div>';
    empty.classList.add('hidden');

    try {
        let url = `/api/gatherings?tab=${currentTab}`;
        if (currentType) url += `&type=${currentType}`;
        const data = await api.get(url);
        const gatherings = data.gatherings || [];

        if (gatherings.length === 0) {
            grid.innerHTML = '';
            empty.classList.remove('hidden');
            return;
        }

        grid.innerHTML = gatherings.map(g => renderCard(g)).join('');
        startCountdowns();
    } catch (err) {
        grid.innerHTML = '<p style="grid-column:1/-1;text-align:center;color:var(--text-muted)">載入失敗</p>';
    }
}

// === Render a gathering card ===
function renderCard(g) {
    const now = Date.now();
    const expiresAt = new Date(g.expires_at + 'Z').getTime();
    const createdAt = new Date(g.created_at + 'Z').getTime();
    const total = expiresAt - createdAt;
    const remaining = expiresAt - now;
    const pct = Math.max(0, Math.min(100, (remaining / total) * 100));
    const isExpired = remaining <= 0 || !g.is_active;
    const isFull = g.current_slots >= g.max_slots;

    let barClass = 'g-bar-ok';
    if (pct <= 10) barClass = 'g-bar-danger';
    else if (pct <= 30) barClass = 'g-bar-warn';

    const membersHtml = g.members.map(m =>
        `<img src="${m.avatar_url || ''}" alt="${m.display_name}" class="g-member-avatar" title="${m.display_name}" onerror="this.style.display='none'">`
    ).join('');

    let actionBtn = '';
    if (isExpired) {
        actionBtn = '<div class="g-expired-label">局已結束 · 自動關閉</div>';
    } else if (g.is_host) {
        actionBtn = `<button class="btn btn-ghost btn-sm g-action-btn" onclick="deleteGathering('${g.id}')">刪除</button>`;
    } else if (g.is_member) {
        actionBtn = `<button class="btn btn-ghost btn-sm g-action-btn" onclick="leaveGathering('${g.id}')">退出</button>`;
    } else if (isFull) {
        actionBtn = '<button class="btn btn-secondary btn-sm g-action-btn" disabled>已額滿</button>';
    } else {
        actionBtn = `<button class="btn btn-primary btn-sm g-action-btn" onclick="joinGathering('${g.id}')">加入</button>`;
    }

    return `
    <div class="g-card ${isExpired ? 'g-card-expired' : ''}" data-id="${g.id}" data-expires="${g.expires_at}" data-created="${g.created_at}" data-active="${g.is_active}">
        <div class="g-progress">
            <div class="g-progress-bar ${barClass}" style="width:${isExpired ? 0 : pct}%"></div>
        </div>
        <div class="g-card-body">
            <div class="g-card-top">
                <span class="g-type-badge">${TYPE_LABELS[g.type] || g.type}</span>
                <span class="g-countdown ${barClass}" data-expires="${g.expires_at}">${isExpired ? '已結束' : ''}</span>
            </div>
            <h3 class="g-title">${escapeHtml(g.title)}</h3>
            <div class="g-info">
                <span>📍 ${escapeHtml(g.location)}</span>
                <span>👥 ${g.current_slots}/${g.max_slots}</span>
            </div>
            <div class="g-host">
                <img src="${g.host.avatar_url || ''}" alt="" class="g-host-avatar" onerror="this.style.display='none'">
                <span>${escapeHtml(g.host.display_name)} 發起</span>
            </div>
            <div class="g-members">${membersHtml}</div>
            <div class="g-actions">${actionBtn}</div>
        </div>
    </div>`;
}

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

// === Countdowns ===
function startCountdowns() {
    if (countdownInterval) clearInterval(countdownInterval);
    updateCountdowns();
    countdownInterval = setInterval(updateCountdowns, 1000);
}

function updateCountdowns() {
    const els = document.querySelectorAll('.g-countdown[data-expires]');
    const now = Date.now();
    els.forEach(el => {
        const card = el.closest('.g-card');
        const expiresAt = new Date(el.dataset.expires + 'Z').getTime();
        const createdAt = new Date(card.dataset.created + 'Z').getTime();
        const total = expiresAt - createdAt;
        const remaining = expiresAt - now;
        const pct = Math.max(0, Math.min(100, (remaining / total) * 100));

        if (remaining <= 0) {
            el.textContent = '已結束';
            el.className = 'g-countdown g-bar-danger';
            card.classList.add('g-card-expired');
            const bar = card.querySelector('.g-progress-bar');
            if (bar) bar.style.width = '0%';
            return;
        }

        const h = Math.floor(remaining / 3600000);
        const m = Math.floor((remaining % 3600000) / 60000);
        const s = Math.floor((remaining % 60000) / 1000);
        el.textContent = `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;

        let barClass = 'g-bar-ok';
        if (pct <= 10) barClass = 'g-bar-danger';
        else if (pct <= 30) barClass = 'g-bar-warn';

        el.className = `g-countdown ${barClass}`;
        const bar = card.querySelector('.g-progress-bar');
        if (bar) {
            bar.style.width = pct + '%';
            bar.className = `g-progress-bar ${barClass}`;
        }
    });
}

// === Tab & Filter ===
function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.g-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.tab === tab);
    });
    loadGatherings();
}

function filterType(type) {
    currentType = type;
    document.querySelectorAll('.g-filter').forEach(f => {
        f.classList.toggle('active', f.dataset.type === type);
    });
    loadGatherings();
}

// === Actions ===
async function joinGathering(id) {
    try {
        await api.post(`/api/gatherings/${id}/join`);
        showToast('已加入！', 'success');
        loadGatherings();
    } catch (err) {
        showToast(err.message || '加入失敗', 'error');
    }
}

async function leaveGathering(id) {
    if (!confirm('確定要退出這個局嗎？')) return;
    try {
        await api.delete(`/api/gatherings/${id}/leave`);
        showToast('已退出', 'success');
        loadGatherings();
    } catch (err) {
        showToast(err.message || '退出失敗', 'error');
    }
}

async function deleteGathering(id) {
    if (!confirm('確定要刪除這個局嗎？')) return;
    try {
        await api.delete(`/api/gatherings/${id}`);
        showToast('已刪除', 'success');
        loadGatherings();
    } catch (err) {
        showToast(err.message || '刪除失敗', 'error');
    }
}

// === Create Modal ===
function openCreateModal() {
    document.getElementById('createModal').classList.remove('hidden');
}

function closeCreateModal() {
    document.getElementById('createModal').classList.add('hidden');
}

document.getElementById('createForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.textContent = '發起中...';
    try {
        await api.post('/api/gatherings', {
            type: document.getElementById('gType').value,
            title: document.getElementById('gTitle').value,
            location: document.getElementById('gLocation').value,
            max_slots: parseInt(document.getElementById('gSlots').value),
            duration_hours: parseInt(document.getElementById('gDuration').value),
        });
        showToast('組局成功！', 'success');
        closeCreateModal();
        e.target.reset();
        loadGatherings();
    } catch (err) {
        showToast(err.message || '發起失敗', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '發起！';
    }
});

// Close modal on overlay click
document.getElementById('createModal').addEventListener('click', (e) => {
    if (e.target.id === 'createModal') closeCreateModal();
});

// Quick create from inspiration cards
function quickCreate(type, title) {
    openCreateModal();
    document.getElementById('gType').value = type;
    document.getElementById('gTitle').value = title;
    document.getElementById('gTitle').focus();
}

// Init
loadGatherings();
