// === Profile Page ===
requireAuth();

let profileData = null;
const currentUser = getUser();

function switchTab(tab) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.profile-tab').forEach(el => el.classList.remove('active'));
    document.getElementById('tab' + tab.charAt(0).toUpperCase() + tab.slice(1)).classList.remove('hidden');
    document.querySelector(`[data-tab="${tab}"]`).classList.add('active');

    if (tab === 'albums') loadAlbums();
    if (tab === 'posts') loadProfilePosts();
}

async function loadProfile() {
    try {
        // Find user by username — use explore endpoint and filter
        const data = await api.get('/api/users/me');
        if (data.username === profileUsername) {
            profileData = data;
        } else {
            // Search in explore or use direct lookup
            // We'll try the explore endpoint with a workaround
            const res = await fetch(`/api/users/explore?page=1&per_page=50`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
            });
            const exploreData = await res.json();
            profileData = exploreData.users?.find(u => u.username === profileUsername);
            if (!profileData) {
                // It might be the current user
                profileData = data;
            }
        }

        renderProfile();
    } catch (err) {
        showToast('載入個人資料失敗', 'error');
    }
}

function renderProfile() {
    if (!profileData) return;
    const isOwner = profileData.username === currentUser.username;

    // Avatar
    const avatarEl = document.getElementById('profileAvatar');
    if (profileData.avatar_url) {
        avatarEl.outerHTML = `<img src="${profileData.avatar_url}" class="profile-avatar" id="profileAvatar" alt="">`;
    } else {
        avatarEl.textContent = avatarFallback(profileData.display_name);
    }

    // Cover
    if (profileData.cover_url) {
        document.getElementById('profileCover').outerHTML =
            `<img src="${profileData.cover_url}" class="profile-cover" id="profileCover" alt="">`;
    }

    // Info
    document.getElementById('profileName').textContent = profileData.display_name;
    let meta = [];
    if (profileData.age) meta.push(profileData.age + ' 歲');
    if (profileData.location) meta.push(profileData.location);
    if (profileData.nationality === 'thai') meta.push('🇹🇭 泰國');
    if (profileData.nationality === 'taiwanese') meta.push('🇹🇼 台灣');
    document.getElementById('profileMeta').textContent = meta.join(' · ');

    // Actions
    const actions = document.getElementById('profileActions');
    if (isOwner) {
        actions.innerHTML = `
            <a href="/settings" class="btn btn-secondary btn-sm">編輯資料</a>
            <label class="btn btn-ghost btn-sm" style="cursor:pointer">
                更換頭貼
                <input type="file" accept="image/*" style="display:none" onchange="uploadAvatar(this)">
            </label>
        `;
        document.getElementById('createAlbumBtn').classList.remove('hidden');
    } else {
        actions.innerHTML = `
            <a href="/chat/${profileData.id}" class="btn btn-primary btn-sm">傳訊息</a>
        `;
    }

    // Details
    const details = document.getElementById('profileDetails');
    let detailHtml = '<div style="display:grid; grid-template-columns:1fr 1fr; gap:1rem;">';
    const fields = [
        { label: '身高', value: profileData.height ? profileData.height + ' cm' : '-' },
        { label: '體重', value: profileData.weight ? profileData.weight + ' kg' : '-' },
    ];
    if (profileData.gender === 'female' && profileData.cup_size) {
        fields.push({ label: '罩杯', value: profileData.cup_size });
    }
    fields.forEach(f => {
        detailHtml += `<div><div class="text-muted" style="font-size:0.8rem">${f.label}</div><div style="font-weight:600">${f.value}</div></div>`;
    });
    detailHtml += '</div>';
    if (profileData.interests) {
        detailHtml += `<div class="mt-3"><div class="text-muted" style="font-size:0.8rem; margin-bottom:0.5rem">興趣</div>
            <div style="display:flex; flex-wrap:wrap; gap:0.4rem;">${profileData.interests.split(',').map(i => `<span style="background:var(--bg-elevated); padding:0.3rem 0.8rem; border-radius:var(--radius-full); font-size:0.85rem;">${i.trim()}</span>`).join('')}</div></div>`;
    }
    if (profileData.bio) {
        detailHtml += `<div class="mt-3"><div class="text-muted" style="font-size:0.8rem; margin-bottom:0.5rem">自我介紹</div><p style="line-height:1.6">${profileData.bio}</p></div>`;
    }
    details.innerHTML = detailHtml;
}

async function uploadAvatar(input) {
    const file = input.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
        const data = await api.post('/api/users/me/avatar', formData, true);
        const user = getUser();
        user.avatar_url = data.avatar_url;
        localStorage.setItem('user', JSON.stringify(user));
        showToast('頭貼已更新', 'success');
        loadProfile();
    } catch (err) {
        showToast('上傳失敗', 'error');
    }
}

async function loadAlbums() {
    if (!profileData) return;
    try {
        const data = await api.get(`/api/albums/user/${profileData.id}`);
        const grid = document.getElementById('albumGrid');
        if (data.albums.length === 0) {
            grid.innerHTML = '<div class="text-muted" style="padding:2rem;">還沒有相簿</div>';
            return;
        }
        grid.innerHTML = data.albums.map(a => `
            <div class="album-card" onclick="viewAlbum('${a.id}', ${a.has_access}, '${a.album_type}')">
                <div style="width:100%;height:100%;background:var(--bg-elevated);display:flex;align-items:center;justify-content:center;">
                    ${a.cover_url ? `<img src="${a.cover_url}" alt="">` : `<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" stroke-width="1"><rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>`}
                </div>
                ${a.album_type === 'private' ? '<div class="album-private-badge">🔒 私密</div>' : ''}
                <div class="album-overlay">
                    <div class="album-title">${a.title}</div>
                    <div class="album-count">${a.photo_count} 張照片</div>
                </div>
            </div>
        `).join('');
    } catch (err) {
        document.getElementById('albumGrid').innerHTML = '<div class="text-muted">載入失敗</div>';
    }
}

async function viewAlbum(albumId, hasAccess, albumType) {
    if (albumType === 'private' && !hasAccess) {
        if (confirm('這是私密相簿，要申請觀看權限嗎？')) {
            try {
                await api.post(`/api/albums/${albumId}/request-access`);
                showToast('已送出申請！', 'success');
            } catch (err) {
                showToast(err.message || '申請失敗', 'error');
            }
        }
        return;
    }

    try {
        const data = await api.get(`/api/albums/${albumId}/photos`);
        const modal = document.getElementById('photoViewerModal');
        const modalContent = modal.querySelector('.modal');
        modalContent.style.maxWidth = '800px';
        modalContent.innerHTML = `
            <button class="modal-close" onclick="closeModal('photoViewerModal')" style="position:absolute;top:1rem;right:1rem;z-index:1">×</button>
            <div class="photo-grid" style="padding:1rem;">
                ${data.photos.map(p => `<img src="${p.image_url}" alt="${p.caption}" onclick="viewPhoto('${p.image_url}')">`).join('')}
            </div>
        `;
        if (data.photos.length === 0) {
            modalContent.innerHTML += '<p class="text-muted text-center" style="padding:2rem">相簿是空的</p>';
        }
        modal.classList.add('active');
    } catch (err) {
        showToast('無法開啟相簿', 'error');
    }
}

function viewPhoto(url) {
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.95);z-index:3001;display:flex;align-items:center;justify-content:center;cursor:pointer;';
    overlay.innerHTML = `<img src="${url}" style="max-width:90%;max-height:90%;object-fit:contain;border-radius:12px;">`;
    overlay.onclick = () => overlay.remove();
    document.body.appendChild(overlay);
}

function showCreateAlbum() {
    document.getElementById('createAlbumModal').classList.add('active');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('active');
}

async function createAlbum() {
    const title = document.getElementById('albumTitle').value.trim();
    if (!title) return showToast('請輸入相簿名稱', 'error');

    const formData = new FormData();
    formData.append('title', title);
    formData.append('album_type', document.getElementById('albumType').value);

    try {
        await api.post('/api/albums', formData, true);
        closeModal('createAlbumModal');
        showToast('相簿已建立！', 'success');
        loadAlbums();
    } catch (err) {
        showToast(err.message || '建立失敗', 'error');
    }
}

async function loadProfilePosts() {
    // For now show a placeholder - profile posts can be loaded similarly to feed
    document.getElementById('profilePosts').innerHTML = '<div class="text-muted text-center" style="padding:2rem;">此會員的動態</div>';
}

loadProfile();
