// === Explore Page (rich card edition) ===
requireAuth();

const meUser = getUser();
let currentPage = 1;
let filters = {};
let activeQuickFilter = '';
let searchTimeout = null;

// ─── Helpers ───
function _truncate(s, n) {
    if (!s) return '';
    s = String(s).replace(/\s+/g, ' ').trim();
    return s.length > n ? s.slice(0, n - 1) + '…' : s;
}
function _flag(nationality) {
    if (nationality === 'thai') return '🇹🇭';
    if (nationality === 'taiwanese') return '🇹🇼';
    return '';
}

// ─── Hero stats ───
async function loadHeroStats() {
    try {
        // Use the explore endpoint itself with a tiny page to learn totals.
        const data = await api.get('/api/users/explore?page=1&per_page=1');
        const verifiedEl = document.getElementById('heroVerifiedCount');
        if (verifiedEl) verifiedEl.textContent = data.total > 999 ? `${Math.floor(data.total/100)/10}K` : (data.total || 0);
        // Online count: secondary cheap call
        const online = await api.get('/api/users/explore?page=1&per_page=1&is_online=true');
        const onlineEl = document.getElementById('heroOnlineCount');
        if (onlineEl) onlineEl.textContent = online.total || 0;
    } catch (_) {}
}

// ─── Premium banner visibility ───
function maybeShowPremiumBanner() {
    if (meUser && !meUser.is_subscribed) {
        document.getElementById('premiumBanner')?.classList.remove('hidden');
    }
}

// ─── User card render ───
function renderUserCard(u) {
    const interests = u.interests
        ? u.interests.split(',').map(t => t.trim()).filter(Boolean).slice(0, 3)
        : [];
    const tagsHtml = interests.length
        ? `<div class="user-card-tags">${interests.map(t => `<span class="user-card-tag">${escapeHtml(t)}</span>`).join('')}</div>`
        : '';
    const bioOneLine = _truncate(u.bio || '', 38);
    const flag = _flag(u.nationality);

    const photoHtml = u.avatar_url
        ? `<img src="${u.avatar_url}" class="user-card-img" alt="${escapeHtml(u.display_name)}" loading="lazy" decoding="async">`
        : `<div class="user-card-img-fallback">${avatarFallback(u.display_name)}</div>`;

    const verifiedBadge = u.is_verified
        ? '<span class="user-pill user-pill-verified" title="已驗證會員">✓ 已驗證</span>'
        : '';
    const onlineBadge = u.is_online
        ? '<span class="user-pill user-pill-online" title="目前在線"><span class="user-pill-dot"></span> 在線</span>'
        : '';

    return `
    <article class="user-card-rich" data-username="${u.username}" data-id="${u.id}">
        <div class="user-card-photo">
            ${photoHtml}
            <div class="user-card-pills">
                ${verifiedBadge}
                ${onlineBadge}
            </div>
            <div class="user-card-overlay">
                <div class="user-card-name">
                    ${escapeHtml(u.display_name)}${u.age ? ', ' + u.age : ''}
                </div>
                <div class="user-card-meta">
                    ${u.height ? u.height + ' cm' : ''}${u.height && u.location ? ' · ' : ''}${u.location ? escapeHtml(u.location) : ''} ${flag}
                </div>
                ${bioOneLine ? `<div class="user-card-bio">「${escapeHtml(bioOneLine)}」</div>` : ''}
            </div>
        </div>
        <div class="user-card-body">
            ${tagsHtml}
            <div class="user-card-actions">
                <a class="btn btn-secondary btn-sm" href="/profile/${u.username}">查看檔案</a>
                <a class="btn btn-primary btn-sm" href="/chat/${u.id}">打招呼</a>
            </div>
        </div>
    </article>`;
}

function escapeHtml(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ─── Main load ───
async function loadUsers(page = 1) {
    const grid = document.getElementById('userGrid');
    grid.innerHTML = Array.from({length: 6}, () => `
        <div class="user-card-rich">
            <div class="skeleton" style="aspect-ratio:3/4; border-radius:0;"></div>
            <div style="padding:0.9rem 1rem;">
                <div class="skeleton skeleton-line w-50"></div>
                <div class="skeleton skeleton-line w-90"></div>
            </div>
        </div>
    `).join('');

    let url = `/api/users/explore?page=${page}&per_page=12`;
    if (filters.min_age) url += `&min_age=${filters.min_age}`;
    if (filters.max_age) url += `&max_age=${filters.max_age}`;
    if (filters.min_height) url += `&min_height=${filters.min_height}`;
    if (filters.max_height) url += `&max_height=${filters.max_height}`;
    if (filters.location) url += `&location=${encodeURIComponent(filters.location)}`;
    if (filters.search) url += `&search=${encodeURIComponent(filters.search)}`;
    if (filters.is_online) url += `&is_online=true`;
    if (filters.sort_by) url += `&sort_by=${filters.sort_by}`;

    try {
        const data = await api.get(url);
        currentPage = page;
        const countEl = document.getElementById('resultCount');
        if (countEl) countEl.textContent = data.total ? `共找到 ${data.total} 位會員` : '';

        if (!data.users || data.users.length === 0) {
            grid.innerHTML = `
                <div style="grid-column:1/-1;">
                    <div class="empty-state-card">
                        <div class="empty-icon">🔍</div>
                        <div class="empty-title">沒有符合條件的會員</div>
                        <div class="empty-desc">試試調整篩選條件,或稍後再來看看</div>
                    </div>
                </div>`;
            document.getElementById('pagination').innerHTML = '';
            return;
        }

        // Optionally filter verified client-side (no backend param)
        let users = data.users;
        if (activeQuickFilter === 'verified') {
            users = users.filter(u => u.is_verified);
        }

        grid.innerHTML = users.map(renderUserCard).join('');

        // Pagination
        const pag = document.getElementById('pagination');
        let html = '';
        if (data.page > 1) html += `<button class="btn btn-secondary btn-sm" onclick="loadUsers(${data.page - 1})">← 上一頁</button>`;
        if (data.total_pages > 1) html += `<span class="text-muted" style="font-size:0.85rem">第 ${data.page} / ${data.total_pages} 頁</span>`;
        if (data.page < data.total_pages) html += `<button class="btn btn-secondary btn-sm" onclick="loadUsers(${data.page + 1})">下一頁 →</button>`;
        pag.innerHTML = html;
    } catch (err) {
        grid.innerHTML = `<div style="grid-column:1/-1;"><div class="empty-state-card"><div class="empty-icon">⚠️</div><div class="empty-title">載入失敗</div><div class="empty-desc">${err.message}</div></div></div>`;
    }
}

function quickFilter(type) {
    activeQuickFilter = type;
    document.querySelectorAll('#filterChips .chip').forEach(chip => {
        chip.classList.toggle('active', chip.dataset.filter === type);
    });
    delete filters.is_online;
    delete filters.sort_by;
    if (type === 'online') filters.is_online = true;
    else if (type === 'new') filters.sort_by = 'newest';
    loadUsers(1);
}

function toggleFilters() {
    document.getElementById('filterDrawer').classList.toggle('hidden');
}

function applyFilters() {
    filters.min_age = document.getElementById('filterMinAge').value || null;
    filters.max_age = document.getElementById('filterMaxAge').value || null;
    filters.min_height = document.getElementById('filterMinHeight').value || null;
    filters.max_height = document.getElementById('filterMaxHeight').value || null;
    filters.location = document.getElementById('filterLocation').value.trim() || null;
    loadUsers(1);
}

function resetFilters() {
    ['filterMinAge', 'filterMaxAge', 'filterMinHeight', 'filterMaxHeight', 'filterLocation'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    filters = {};
    activeQuickFilter = '';
    document.querySelectorAll('#filterChips .chip').forEach(chip => {
        chip.classList.toggle('active', chip.dataset.filter === '');
    });
    loadUsers(1);
}

// ─── Search debounce ───
document.getElementById('searchInput').addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        const val = e.target.value.trim();
        if (val) filters.search = val;
        else delete filters.search;
        loadUsers(1);
    }, 400);
});

// ─── Init ───
maybeShowPremiumBanner();
loadHeroStats();
loadUsers();
