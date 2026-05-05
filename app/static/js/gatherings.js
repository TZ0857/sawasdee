// === Gatherings Page ===
requireAuth();

// Keep this in sync with backend GATHERING_TYPES (app/routers/gatherings.py).
const TYPE_LABELS = {
    meal: '🍜 飯局',
    drinks: '🥂 小酌',
    karaoke: '🎤 KTV',
    movie: '🎬 電影',
    nightlife: '🌙 夜生活',
};

let currentTab = 'explore';
let currentType = '';
let countdownInterval = null;

// === Load gatherings ===
async function loadGatherings() {
    const grid = document.getElementById('gatheringGrid');
    const empty = document.getElementById('gatheringEmpty');
    grid.innerHTML = Array.from({length: 4}, () => '<div class="g-card"><div class="skeleton skeleton-grid-card" style="height:240px;"></div></div>').join('');
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

/* === Date helpers ===
   Backend stores datetimes as naive UTC; isoformat() omits the Z, so we
   append it before parsing. Display always uses the user's local tz.
*/
const WEEK_LABEL = ['日', '一', '二', '三', '四', '五', '六'];

function parseUtc(iso) {
    if (!iso) return null;
    return new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
}

function formatEventTime(date) {
    // → "5/4 (週三) 21:00"
    const m = date.getMonth() + 1;
    const d = date.getDate();
    const w = WEEK_LABEL[date.getDay()];
    const hh = String(date.getHours()).padStart(2, '0');
    const mm = String(date.getMinutes()).padStart(2, '0');
    return `${m}/${d} (週${w}) ${hh}:${mm}`;
}

function formatRemaining(ms) {
    if (ms <= 0) return '已開始';
    const totalMin = Math.floor(ms / 60000);
    const days = Math.floor(totalMin / 1440);
    const hours = Math.floor((totalMin % 1440) / 60);
    const mins = totalMin % 60;
    if (days > 0) return `${days} 天 ${hours} 小時後`;
    if (hours > 0) return `${hours} 小時 ${mins} 分後`;
    if (mins > 0) return `${mins} 分鐘後`;
    return '即將開始';
}

// === Render a gathering card ===
function renderCard(g) {
    const now = Date.now();
    const eventDate = parseUtc(g.event_at || g.expires_at);
    const eventAt = eventDate ? eventDate.getTime() : 0;
    const createdAt = parseUtc(g.created_at).getTime();
    const total = Math.max(1, eventAt - createdAt);
    const remaining = eventAt - now;
    const pct = Math.max(0, Math.min(100, (remaining / total) * 100));
    const isPast = remaining <= 0 || !g.is_active;
    const isFull = g.current_slots >= g.max_slots;

    let barClass = 'g-bar-ok';
    if (pct <= 10) barClass = 'g-bar-danger';
    else if (pct <= 30) barClass = 'g-bar-warn';

    const membersHtml = g.members.map(m =>
        `<img src="${m.avatar_url || ''}" alt="${m.display_name}" class="g-member-avatar" title="${m.display_name}" loading="lazy" decoding="async" onerror="this.style.display='none'">`
    ).join('');

    // Optimistic-pending tracker: lets the UI stay on "已申請" even if a
    // subsequent grid reload races against the DB commit and momentarily
    // returns my_request_status:null. Cleared once the server confirms
    // pending (or marks approved/rejected).
    if (g.my_request_status === 'pending') {
        _optimisticPending.delete(g.id);   // server caught up
    }
    const optimistic = _optimisticPending.has(g.id);

    let actionBtn = '';
    if (isPast) {
        actionBtn = '<div class="g-expired-label">局已開始 · 自動關閉</div>';
    } else if (g.is_host) {
        actionBtn = `
            <a href="/gatherings/${g.id}/chat" class="btn btn-secondary btn-sm g-action-btn">💬 聊天</a>
            <button class="btn btn-ghost btn-sm g-action-btn" onclick="deleteGathering('${g.id}')">刪除</button>
        `;
    } else if (g.is_member) {
        // Server says I'm a member → host already approved, drop optimism.
        _optimisticPending.delete(g.id);
        actionBtn = `
            <a href="/gatherings/${g.id}/chat" class="btn btn-secondary btn-sm g-action-btn">💬 聊天</a>
            <button class="btn btn-ghost btn-sm g-action-btn" onclick="leaveGathering('${g.id}')">退出</button>
        `;
    } else if (g.my_request_status === 'pending' || optimistic) {
        actionBtn = '<button class="btn btn-pending btn-sm g-action-btn" disabled>已申請</button>';
    } else if (g.my_request_status === 'rejected') {
        actionBtn = `<button class="btn btn-secondary btn-sm g-action-btn" onclick="openApplyModal('${g.id}', \`${escapeAttr(g.title)}\`)">重新申請</button>`;
    } else if (isFull) {
        actionBtn = '<button class="btn btn-secondary btn-sm g-action-btn" disabled>已額滿</button>';
    } else {
        actionBtn = `<button class="btn btn-primary btn-sm g-action-btn" onclick="openApplyModal('${g.id}', \`${escapeAttr(g.title)}\`)">申請加入</button>`;
    }

    const eventStr = eventDate ? formatEventTime(eventDate) : '';

    return `
    <div class="g-card ${isPast ? 'g-card-expired' : ''}" data-id="${g.id}" data-event="${g.event_at || g.expires_at}" data-created="${g.created_at}" data-active="${g.is_active}">
        <div class="g-progress">
            <div class="g-progress-bar ${barClass}" style="width:${isPast ? 0 : pct}%"></div>
        </div>
        <div class="g-card-body">
            <div class="g-card-top">
                <span class="g-type-badge">${TYPE_LABELS[g.type] || g.type}</span>
                <span class="g-countdown ${barClass}" data-event="${g.event_at || g.expires_at}">${isPast ? '已開始' : formatRemaining(remaining)}</span>
            </div>
            <h3 class="g-title">${escapeHtml(g.title)}</h3>
            <div class="g-event-time">🗓 ${eventStr}</div>
            <div class="g-info">
                <span>📍 ${escapeHtml(g.location)}</span>
                <span>👥 ${g.current_slots}/${g.max_slots}</span>
            </div>
            <div class="g-host">
                <img src="${g.host.avatar_url || ''}" alt="" class="g-host-avatar" loading="lazy" decoding="async" onerror="this.style.display='none'">
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
function escapeAttr(s) {
    return String(s == null ? '' : s).replace(/`/g, '\\`').replace(/'/g, "\\'");
}

// === Countdowns ===
// Updates ONCE per minute (not once per second). Card text is in
// "X 小時 Y 分後" / "X 天 Y 小時後" granularity — there's no visible change
// per second except in the final 60s window, which we handle separately.
function startCountdowns() {
    if (countdownInterval) clearInterval(countdownInterval);
    updateCountdowns();
    countdownInterval = setInterval(updateCountdowns, 60_000);
    // Re-tick whenever the tab returns to foreground so stale countdowns
    // catch up immediately.
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') updateCountdowns();
    });
}

function updateCountdowns() {
    const els = document.querySelectorAll('.g-countdown[data-event]');
    const now = Date.now();
    els.forEach(el => {
        const card = el.closest('.g-card');
        if (!card) return;
        const eventAt = parseUtc(el.dataset.event).getTime();
        const createdAt = parseUtc(card.dataset.created).getTime();
        const total = Math.max(1, eventAt - createdAt);
        const remaining = eventAt - now;
        const pct = Math.max(0, Math.min(100, (remaining / total) * 100));

        if (remaining <= 0) {
            el.textContent = '已開始';
            el.className = 'g-countdown g-bar-danger';
            card.classList.add('g-card-expired');
            const bar = card.querySelector('.g-progress-bar');
            if (bar) bar.style.width = '0%';
            return;
        }

        let barClass = 'g-bar-ok';
        if (pct <= 10) barClass = 'g-bar-danger';
        else if (pct <= 30) barClass = 'g-bar-warn';

        el.textContent = formatRemaining(remaining);
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
    if (tab === 'mine') loadIncomingRequests();
    else document.getElementById('incomingPanel').classList.add('hidden');
}

// === Incoming requests (host approval panel, only on 我的局) ===
async function loadIncomingRequests() {
    const panel = document.getElementById('incomingPanel');
    try {
        const data = await api.get('/api/gatherings/requests/incoming');
        const reqs = data.requests || [];
        updateMineBadge(reqs.length);
        if (reqs.length === 0) {
            panel.innerHTML = '';
            panel.classList.add('hidden');
            return;
        }
        panel.classList.remove('hidden');
        panel.innerHTML = `
            <div class="card" style="border-color:var(--gold-dark);">
                <div class="card-body">
                    <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.7rem;">
                        <span style="font-size:1.1rem;">🔔</span>
                        <strong>有 ${reqs.length} 個申請等你審核</strong>
                    </div>
                    ${reqs.map(r => renderIncomingRow(r)).join('')}
                </div>
            </div>
        `;
    } catch (err) {
        panel.innerHTML = '';
        panel.classList.add('hidden');
    }
}

function renderIncomingRow(r) {
    const ageStr = r.applicant.age ? `${r.applicant.age} 歲` : '';
    const msg = r.message ? `<div class="g-incoming-msg">「${escapeHtml(r.message)}」</div>` : '';
    return `
        <div class="g-incoming-row">
            <img src="${escapeHtml(r.applicant.avatar_url || '')}" alt="" class="g-incoming-avatar" loading="lazy" decoding="async">
            <div style="flex:1; min-width:0;">
                <div><strong>${escapeHtml(r.applicant.display_name)}</strong>${ageStr ? ` <span class="text-muted">· ${ageStr}</span>` : ''}</div>
                <div class="text-muted" style="font-size:0.78rem;">想加入「${escapeHtml(r.gathering.title)}」</div>
                ${msg}
            </div>
            <div class="g-incoming-actions">
                <button class="btn btn-primary btn-sm" onclick="approveReq('${r.id}')">同意</button>
                <button class="btn btn-ghost btn-sm" onclick="rejectReq('${r.id}')" style="color:var(--danger);">拒絕</button>
            </div>
        </div>
    `;
}

async function approveReq(rid) {
    try {
        await api.post(`/api/gatherings/requests/${rid}/approve`);
        showToast('已同意,聊天室已加入對方', 'success');
        loadIncomingRequests();
        loadGatherings();
        updateNavbarBadge();
    } catch (err) {
        showToast(err.message || '同意失敗', 'error');
    }
}

async function rejectReq(rid) {
    if (!confirm('確定拒絕這個申請?')) return;
    try {
        await api.post(`/api/gatherings/requests/${rid}/reject`);
        showToast('已拒絕', 'success');
        loadIncomingRequests();
        updateNavbarBadge();
    } catch (err) {
        showToast(err.message || '拒絕失敗', 'error');
    }
}

function updateMineBadge(n) {
    const badge = document.getElementById('mineTabBadge');
    if (!badge) return;
    if (n > 0) {
        badge.textContent = n > 99 ? '99+' : String(n);
        badge.classList.remove('hidden');
    } else {
        badge.classList.add('hidden');
    }
}

async function updateNavbarBadge() {
    try {
        const data = await api.get('/api/gatherings/requests/pending-count');
        const navBadge = document.querySelector('[data-page="gatherings"] .nav-badge')
                       || document.querySelector('[data-page="gatherings"] .badge');
        const n = data.count || 0;
        if (navBadge) {
            if (n > 0) {
                navBadge.textContent = n > 9 ? '9+' : String(n);
                navBadge.classList.remove('hidden');
            } else {
                navBadge.classList.add('hidden');
            }
        }
    } catch (e) { /* ignore */ }
}

function filterType(type) {
    currentType = type;
    document.querySelectorAll('.g-filter').forEach(f => {
        f.classList.toggle('active', f.dataset.type === type);
    });
    loadGatherings();
}

// === Apply flow ===
let applyingGatheringId = null;

function openApplyModal(id, title) {
    applyingGatheringId = id;
    document.getElementById('applyTargetSummary').textContent = `要申請加入「${title}」`;
    document.getElementById('applyMessage').value = '';
    document.getElementById('applyModal').classList.remove('hidden');
}

function closeApplyModal() {
    document.getElementById('applyModal').classList.add('hidden');
    applyingGatheringId = null;
}

// Set of gathering IDs the user just applied to. Persists across
// loadGatherings() reruns so a stale GET (returning my_request_status:null
// before the apply commit replicates) cannot revert the button to "申請加入".
// Cleared in renderCard once the server confirms pending / approved / etc.
const _optimisticPending = new Set();

function _swapCardActionToPending(gid) {
    _optimisticPending.add(gid);
    const card = document.querySelector(`.g-card[data-id="${gid}"]`);
    if (!card) return;
    const actions = card.querySelector('.g-actions');
    if (!actions) return;
    actions.innerHTML = '<button class="btn btn-pending btn-sm g-action-btn" disabled>已申請</button>';
}

document.getElementById('applyForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!applyingGatheringId) return;
    const gid = applyingGatheringId;
    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    const message = document.getElementById('applyMessage').value.trim();

    // Flip the button state right away. The optimistic Set keeps it that way
    // even if the next loadGatherings() races the DB commit.
    _swapCardActionToPending(gid);
    closeApplyModal();
    showToast('已送出申請,等對方審核', 'success');

    try {
        await api.post(`/api/gatherings/${gid}/apply`, { message });
        // Background refresh so members count, pending badge etc. stay accurate.
        loadGatherings();
    } catch (err) {
        // Real failure — roll back the optimism and tell the user.
        _optimisticPending.delete(gid);
        showToast(err.message || '申請失敗', 'error');
        loadGatherings();
    } finally {
        btn.disabled = false;
    }
});

// Click outside applyModal closes it
document.getElementById('applyModal').addEventListener('click', (e) => {
    if (e.target.id === 'applyModal') closeApplyModal();
});

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

/* Default event time = ~3h from now, rounded UP to the next 30-min slot. */
function defaultEventLocalString(offsetHours = 3) {
    const d = new Date(Date.now() + offsetHours * 3600 * 1000);
    // Round up to next 30-min boundary
    const m = d.getMinutes();
    if (m === 0 || m === 30) {
        // Already aligned — keep as is
    } else if (m < 30) {
        d.setMinutes(30);
    } else {
        d.setMinutes(0);
        d.setHours(d.getHours() + 1);
    }
    d.setSeconds(0); d.setMilliseconds(0);
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function minEventLocalString() {
    // Earliest selectable time = now + 30min, since backend enforces this.
    const d = new Date(Date.now() + 30 * 60 * 1000);
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

document.getElementById('createForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.textContent = '發起中...';

    const eventLocal = document.getElementById('gEventAt').value;  // 'YYYY-MM-DDTHH:mm' (local)
    if (!eventLocal) {
        showToast('請選擇局的時間', 'error');
        btn.disabled = false;
        btn.textContent = '發起！';
        return;
    }
    const eventAtIso = new Date(eventLocal).toISOString();

    try {
        await api.post('/api/gatherings', {
            type: document.getElementById('gType').value,
            title: document.getElementById('gTitle').value,
            location: document.getElementById('gLocation').value,
            max_slots: parseInt(document.getElementById('gSlots').value),
            event_at: eventAtIso,
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
    // Different categories get different sensible defaults
    const offsets = { meal: 4, drinks: 6, karaoke: 8, movie: 5, nightlife: 9 };
    document.getElementById('gEventAt').value = defaultEventLocalString(offsets[type] ?? 3);
    document.getElementById('gTitle').focus();
}

/* When opening the create modal, pre-fill sensible time + min boundary. */
const _originalOpenModal = openCreateModal;
openCreateModal = function() {
    const input = document.getElementById('gEventAt');
    if (input) {
        if (!input.value) input.value = defaultEventLocalString(3);
        input.min = minEventLocalString();
    }
    _originalOpenModal();
};

// Init
loadGatherings();
// Load pending count quietly so the 我的局 tab badge is up to date even
// before the user clicks into that tab. The panel itself only renders
// when on the 我的局 tab.
(async () => {
    try {
        const data = await api.get('/api/gatherings/requests/pending-count');
        updateMineBadge(data.count || 0);
    } catch (e) { /* ignore */ }
})();
