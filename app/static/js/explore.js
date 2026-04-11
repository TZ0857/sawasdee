// === Explore Page ===
requireAuth();

let currentPage = 1;
let filters = {};

async function loadUsers(page = 1) {
    const grid = document.getElementById('userGrid');
    grid.innerHTML = '<div class="flex-center" style="grid-column:1/-1; padding:4rem;"><div class="spinner"></div></div>';

    let url = `/api/users/explore?page=${page}&per_page=12`;
    if (filters.min_age) url += `&min_age=${filters.min_age}`;
    if (filters.max_age) url += `&max_age=${filters.max_age}`;
    if (filters.min_height) url += `&min_height=${filters.min_height}`;
    if (filters.max_height) url += `&max_height=${filters.max_height}`;

    try {
        const data = await api.get(url);
        currentPage = page;

        if (data.users.length === 0) {
            grid.innerHTML = '<div class="text-center text-muted" style="grid-column:1/-1; padding:4rem;">目前沒有符合條件的會員</div>';
            document.getElementById('pagination').innerHTML = '';
            return;
        }

        grid.innerHTML = data.users.map(u => `
            <div class="card user-card" onclick="window.location.href='/profile/${u.username}'">
                ${u.is_online ? '<div class="online-dot"></div>' : ''}
                <div style="width:100%; aspect-ratio:3/4; background:var(--gradient-rose); display:flex; align-items:center; justify-content:center; border-radius:var(--radius-lg) var(--radius-lg) 0 0;">
                    ${u.avatar_url
                        ? `<img src="${u.avatar_url}" class="card-img" alt="${u.display_name}">`
                        : `<span style="font-size:4rem; color:#fff; font-family:var(--font-heading)">${avatarFallback(u.display_name)}</span>`
                    }
                </div>
                <div class="card-overlay">
                    <div class="card-name">${u.display_name}${u.age ? ', ' + u.age : ''}</div>
                    <div class="card-meta">
                        ${u.height ? u.height + ' cm' : ''}
                        ${u.location ? ' · ' + u.location : ''}
                    </div>
                </div>
            </div>
        `).join('');

        // Pagination
        const pag = document.getElementById('pagination');
        let html = '';
        if (data.page > 1) html += `<button class="btn btn-secondary btn-sm" onclick="loadUsers(${data.page - 1})">← 上一頁</button>`;
        html += `<span class="text-muted" style="font-size:0.9rem">第 ${data.page} / ${data.total_pages} 頁</span>`;
        if (data.page < data.total_pages) html += `<button class="btn btn-secondary btn-sm" onclick="loadUsers(${data.page + 1})">下一頁 →</button>`;
        pag.innerHTML = html;
    } catch (err) {
        grid.innerHTML = `<div class="text-center text-muted" style="grid-column:1/-1; padding:4rem;">載入失敗：${err.message}</div>`;
    }
}

function toggleFilters() {
    document.getElementById('filterBar').classList.toggle('hidden');
}

function applyFilters() {
    filters = {
        min_age: document.getElementById('filterMinAge').value || null,
        max_age: document.getElementById('filterMaxAge').value || null,
        min_height: document.getElementById('filterMinHeight').value || null,
        max_height: document.getElementById('filterMaxHeight').value || null,
    };
    loadUsers(1);
}

function resetFilters() {
    document.getElementById('filterMinAge').value = '';
    document.getElementById('filterMaxAge').value = '';
    document.getElementById('filterMinHeight').value = '';
    document.getElementById('filterMaxHeight').value = '';
    filters = {};
    loadUsers(1);
}

loadUsers();
