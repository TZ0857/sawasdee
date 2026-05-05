// === Explore Page ===
requireAuth();

let currentPage = 1;
let filters = {};
let activeQuickFilter = '';
let searchTimeout = null;

async function loadUsers(page = 1) {
    const grid = document.getElementById('userGrid');
    // Skeleton card grid feels ~2× faster than a centered spinner
    grid.innerHTML = Array.from({length: 6}, () => `
        <div class="user-card">
            <div class="skeleton skeleton-grid-card"></div>
        </div>
    `).join('');

    let url = `/api/users/explore?page=${page}&per_page=12`;
    if (filters.min_age) url += `&min_age=${filters.min_age}`;
    if (filters.max_age) url += `&max_age=${filters.max_age}`;
    if (filters.min_height) url += `&min_height=${filters.min_height}`;
    if (filters.max_height) url += `&max_height=${filters.max_height}`;
    if (filters.search) url += `&search=${encodeURIComponent(filters.search)}`;
    if (filters.is_online) url += `&is_online=true`;
    if (filters.sort_by) url += `&sort_by=${filters.sort_by}`;

    try {
        const data = await api.get(url);
        currentPage = page;

        if (data.users.length === 0) {
            grid.innerHTML = `
                <div style="grid-column:1/-1;">
                    <div class="empty-state-card">
                        <div class="empty-icon">🔍</div>
                        <div class="empty-title">沒有符合條件的會員</div>
                        <div class="empty-desc">試試調整篩選條件，或稍後再來看看</div>
                    </div>
                </div>`;
            document.getElementById('pagination').innerHTML = '';
            return;
        }

        grid.innerHTML = data.users.map(u => {
            const interests = u.interests ? u.interests.split(',').slice(0, 3) : [];
            const tagsHtml = interests.length > 0
                ? `<div class="card-tags">${interests.map(t => `<span class="card-tag">${t.trim()}</span>`).join('')}</div>`
                : '';

            return `
            <div class="user-card" onclick="window.location.href='/profile/${u.username}'">
                ${u.is_online ? '<div class="online-dot"></div>' : ''}
                <div class="card-img-wrap">
                    ${u.avatar_url
                        ? `<img src="${u.avatar_url}" class="card-img" alt="${u.display_name}" loading="lazy" decoding="async">`
                        : `<div class="card-img-fallback">${avatarFallback(u.display_name)}</div>`
                    }
                </div>
                <div class="card-overlay">
                    <div class="card-name">${u.display_name}${u.age ? ', ' + u.age : ''}${u.is_verified ? ' <span class="verified-badge">✓</span>' : ''}</div>
                    <div class="card-meta">
                        ${u.height ? u.height + ' cm' : ''}${u.location ? ' · ' + u.location : ''}
                    </div>
                    ${tagsHtml}
                </div>
            </div>`;
        }).join('');

        // Pagination
        const pag = document.getElementById('pagination');
        let html = '';
        if (data.page > 1) html += `<button class="btn btn-secondary btn-sm" onclick="loadUsers(${data.page - 1})">← 上一頁</button>`;
        html += `<span class="text-muted" style="font-size:0.85rem">第 ${data.page} / ${data.total_pages} 頁</span>`;
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
    document.getElementById('filterBar').classList.toggle('hidden');
}

function applyFilters() {
    filters.min_age = document.getElementById('filterMinAge').value || null;
    filters.max_age = document.getElementById('filterMaxAge').value || null;
    filters.min_height = document.getElementById('filterMinHeight').value || null;
    filters.max_height = document.getElementById('filterMaxHeight').value || null;
    loadUsers(1);
}

function resetFilters() {
    document.getElementById('filterMinAge').value = '';
    document.getElementById('filterMaxAge').value = '';
    document.getElementById('filterMinHeight').value = '';
    document.getElementById('filterMaxHeight').value = '';
    filters = {};
    activeQuickFilter = '';
    document.querySelectorAll('#filterChips .chip').forEach(chip => {
        chip.classList.toggle('active', chip.dataset.filter === '');
    });
    loadUsers(1);
}

// Search with debounce
document.getElementById('searchInput').addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        const val = e.target.value.trim();
        if (val) filters.search = val;
        else delete filters.search;
        loadUsers(1);
    }, 400);
});

loadUsers();
