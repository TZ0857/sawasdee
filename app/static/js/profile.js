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
        // /api/users/{id_or_username} now accepts both — single round trip.
        profileData = await api.get(`/api/users/${encodeURIComponent(profileUsername)}`);
        renderProfile();
    } catch (err) {
        showToast('找不到這位會員', 'error');
        document.getElementById('profileName').textContent = '找不到此會員';
        document.getElementById('profileMeta').textContent = '請回探索頁尋找其他會員。';
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

    // Verified badge
    const verifiedBadge = document.getElementById('verifiedBadge');
    if (verifiedBadge) {
        if (profileData.is_verified) verifiedBadge.classList.remove('hidden');
        else verifiedBadge.classList.add('hidden');
    }
    // Premium badge
    const premiumBadge = document.getElementById('premiumBadge');
    if (premiumBadge) {
        if (profileData.is_subscribed) premiumBadge.classList.remove('hidden');
        else premiumBadge.classList.add('hidden');
    }

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
            <button class="btn btn-ghost btn-sm" id="blockBtn" onclick="toggleBlock()" style="opacity:0.7;">
                <span id="blockBtnLabel">封鎖</span>
            </button>
        `;
        // Hydrate block status
        api.get(`/api/blocks/check/${profileData.id}`).then(r => {
            const lbl = document.getElementById('blockBtnLabel');
            if (lbl) lbl.textContent = r.is_blocked ? '解除封鎖' : '封鎖';
        }).catch(() => {});
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

async function toggleBlock() {
    const id = profileData && profileData.id;
    if (!id) return;
    const lbl = document.getElementById('blockBtnLabel');
    const isBlocked = lbl && lbl.textContent.includes('解除');
    try {
        if (isBlocked) {
            await api.delete(`/api/blocks/${id}`);
            showToast('已解除封鎖', 'success');
            if (lbl) lbl.textContent = '封鎖';
        } else {
            if (!confirm('封鎖後對方將無法傳訊息給你,你也不會在探索頁看到這個人。確定?')) return;
            await api.post(`/api/blocks/${id}`);
            showToast('已封鎖', 'success');
            if (lbl) lbl.textContent = '解除封鎖';
        }
    } catch (e) {
        showToast('操作失敗:' + (e.message || ''), 'error');
    }
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

/* ============================================================
   ALBUMS
   ============================================================ */

let openAlbum = null;   // currently-open album object in the viewer
const MAX_PHOTOS = 20;

async function loadAlbums() {
    if (!profileData) return;
    const isOwner = profileData.username === currentUser.username;

    // For owners, also load pending access requests
    if (isOwner) {
        renderPendingRequestsPanel();
    }

    try {
        const data = await api.get(`/api/albums/user/${profileData.id}`);
        const grid = document.getElementById('albumGrid');
        if (!data.albums || data.albums.length === 0) {
            grid.innerHTML = `<div class="text-muted" style="padding:2rem; text-align:center;">${isOwner ? '還沒有相簿,點右上角「建立相簿」開始收集你的時刻 ✨' : '這位會員還沒有相簿'}</div>`;
            return;
        }
        grid.innerHTML = data.albums.map(a => renderAlbumCard(a)).join('');
    } catch (err) {
        document.getElementById('albumGrid').innerHTML = '<div class="text-muted">載入失敗</div>';
    }
}

function renderAlbumCard(a) {
    const cover = a.cover_url
        ? `<img src="${escapeAttr(a.cover_url)}" alt="" loading="lazy" decoding="async" onerror="this.outerHTML='<div class=&quot;album-cover-fallback&quot;>📷</div>'">`
        : `<div class="album-cover-fallback">📷</div>`;

    let badge = '';
    if (a.album_type === 'private') {
        if (a.is_owner) badge = '<div class="album-private-badge">🔒 私密</div>';
        else if (a.has_access) badge = '<div class="album-private-badge" style="background:rgba(48,160,90,0.85);">✓ 已通過</div>';
        else if (a.request_status === 'pending') badge = '<div class="album-private-badge" style="background:rgba(160,140,90,0.85);">⏳ 審核中</div>';
        else if (a.request_status === 'rejected') badge = '<div class="album-private-badge" style="background:rgba(160,90,90,0.85);">✗ 未通過</div>';
        else badge = '<div class="album-private-badge">🔒 私密</div>';
    }

    return `
        <div class="album-card" onclick='openAlbumViewer(${JSON.stringify(a)})'>
            <div class="album-cover-wrap">${cover}</div>
            ${badge}
            <div class="album-overlay">
                <div class="album-title">${escapeHtmlA(a.title)}</div>
                <div class="album-count">${a.photo_count} 張照片</div>
            </div>
        </div>
    `;
}

function escapeHtmlA(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function escapeAttr(s) { return escapeHtmlA(s); }

async function openAlbumViewer(album) {
    openAlbum = album;
    const isOwner = !!album.is_owner;
    const isPrivate = album.album_type === 'private';

    // Private albums the viewer doesn't have access to → show request UI instead
    if (!isOwner && isPrivate && !album.has_access) {
        return openPrivateAccessGate(album);
    }

    // Open viewer with photos
    let photos = [];
    try {
        const data = await api.get(`/api/albums/${album.id}/photos`);
        photos = data.photos || [];
    } catch (err) {
        return showToast('無法開啟相簿', 'error');
    }

    const modal = document.getElementById('photoViewerModal');
    const modalContent = modal.querySelector('.modal');
    modalContent.style.maxWidth = '880px';
    modalContent.style.background = 'var(--bg-card)';
    modalContent.style.borderRadius = 'var(--radius-lg)';
    modalContent.style.padding = '0';
    modalContent.style.position = 'relative';

    const headerActions = isOwner ? `
        <button class="btn btn-ghost btn-sm" onclick="renameAlbumPrompt('${album.id}', '${escapeAttr(album.title)}')" title="重新命名">✏️</button>
        <button class="btn btn-ghost btn-sm" onclick="toggleAlbumType('${album.id}', '${album.album_type}')" title="切換公開/私密">${isPrivate ? '🔓 設為公開' : '🔒 設為私密'}</button>
        <button class="btn btn-ghost btn-sm" onclick="deleteAlbumConfirm('${album.id}')" title="刪除相簿" style="color:var(--danger);">🗑</button>
    ` : '';

    const uploadButton = isOwner ? `
        <label class="btn btn-primary btn-sm" style="cursor:pointer;">
            ＋ 上傳照片 (${photos.length}/${MAX_PHOTOS})
            <input type="file" accept="image/*" multiple style="display:none" onchange="uploadAlbumPhotos('${album.id}', this)">
        </label>
    ` : '';

    const photoTiles = photos.length === 0
        ? `<div class="text-muted text-center" style="padding:3rem;">${isOwner ? '相簿是空的,點上方「上傳照片」開始 📷' : '相簿是空的'}</div>`
        : `<div class="album-photo-grid">${photos.map((p, idx) => renderPhotoTile(p, idx, isOwner, album.id)).join('')}</div>`;

    modalContent.innerHTML = `
        <div class="album-viewer-header">
            <div class="album-viewer-title">${escapeHtmlA(album.title)} ${isPrivate ? '<span style="color:var(--gold-light); font-size:0.75rem;">🔒</span>' : ''}</div>
            <div style="display:flex; gap:0.4rem; align-items:center;">${headerActions}<button class="btn btn-ghost btn-sm" onclick="closeModal('photoViewerModal')" title="關閉">✕</button></div>
        </div>
        ${isOwner ? `<div class="album-viewer-toolbar">${uploadButton}</div>` : ''}
        <div class="album-viewer-body">${photoTiles}</div>
    `;
    modal.classList.add('active');
    modal.classList.remove('hidden');
    // Stash photos for the lightbox to navigate
    modal._photos = photos;
}

function renderPhotoTile(p, idx, isOwner, albumId) {
    const ownerActions = isOwner ? `
        <div class="photo-tile-actions">
            <button title="設為封面" onclick="event.stopPropagation(); setAlbumCover('${albumId}', '${p.id}')">⭐</button>
            <button title="刪除" onclick="event.stopPropagation(); deletePhotoConfirm('${p.id}')">🗑</button>
        </div>
    ` : '';
    return `
        <div class="photo-tile" onclick="openLightbox(${idx})">
            <img src="${escapeAttr(p.image_url)}" alt="${escapeAttr(p.caption || '')}" loading="lazy" onerror="this.outerHTML='<div class=&quot;photo-tile-missing&quot;>📷</div>'">
            ${ownerActions}
        </div>
    `;
}

/* ---- Photo lightbox with prev/next ---- */
function openLightbox(startIdx) {
    const modal = document.getElementById('photoViewerModal');
    const photos = modal._photos || [];
    if (!photos.length) return;
    let idx = startIdx;

    const overlay = document.createElement('div');
    overlay.className = 'photo-lightbox';
    overlay.innerHTML = `
        <button class="lightbox-btn lightbox-prev" aria-label="上一張">‹</button>
        <img class="lightbox-img" src="${escapeAttr(photos[idx].image_url)}" alt="">
        <button class="lightbox-btn lightbox-next" aria-label="下一張">›</button>
        <button class="lightbox-close" aria-label="關閉">✕</button>
        <div class="lightbox-caption">${escapeHtmlA(photos[idx].caption || '')}</div>
    `;
    document.body.appendChild(overlay);

    const update = () => {
        overlay.querySelector('.lightbox-img').src = photos[idx].image_url;
        overlay.querySelector('.lightbox-caption').textContent = photos[idx].caption || '';
    };
    const prev = () => { idx = (idx - 1 + photos.length) % photos.length; update(); };
    const next = () => { idx = (idx + 1) % photos.length; update(); };
    overlay.querySelector('.lightbox-prev').onclick = (e) => { e.stopPropagation(); prev(); };
    overlay.querySelector('.lightbox-next').onclick = (e) => { e.stopPropagation(); next(); };
    overlay.querySelector('.lightbox-close').onclick = (e) => { e.stopPropagation(); cleanup(); };
    overlay.onclick = cleanup;
    const onKey = (e) => {
        if (e.key === 'ArrowLeft') prev();
        else if (e.key === 'ArrowRight') next();
        else if (e.key === 'Escape') cleanup();
    };
    document.addEventListener('keydown', onKey);
    function cleanup() {
        overlay.remove();
        document.removeEventListener('keydown', onKey);
    }
}

/* ---- Owner album management ---- */
async function uploadAlbumPhotos(albumId, input) {
    const files = Array.from(input.files || []);
    if (!files.length) return;
    const formData = new FormData();
    files.forEach(f => formData.append('images', f));
    try {
        const res = await api.post(`/api/albums/${albumId}/photos/batch`, formData, true);
        let msg = `已上傳 ${res.uploaded.length} 張`;
        if (res.skipped) msg += `,${res.skipped} 張因超過 ${MAX_PHOTOS} 張上限被略過`;
        showToast(msg, 'success');
        // Reload album viewer + grid
        await loadAlbums();
        // Re-open with refreshed data
        const data = await api.get(`/api/albums/user/${profileData.id}`);
        const updated = (data.albums || []).find(a => a.id === albumId);
        if (updated) openAlbumViewer(updated);
    } catch (err) {
        showToast(err.message || '上傳失敗', 'error');
    } finally {
        input.value = '';
    }
}

async function deletePhotoConfirm(photoId) {
    if (!confirm('確定要刪除這張照片?無法還原')) return;
    try {
        await api.delete(`/api/albums/photos/${photoId}`);
        showToast('已刪除', 'success');
        await loadAlbums();
        if (openAlbum) {
            const data = await api.get(`/api/albums/user/${profileData.id}`);
            const updated = (data.albums || []).find(a => a.id === openAlbum.id);
            if (updated) openAlbumViewer(updated); else closeModal('photoViewerModal');
        }
    } catch (err) {
        showToast(err.message || '刪除失敗', 'error');
    }
}

async function deleteAlbumConfirm(albumId) {
    if (!confirm('確定要刪除整個相簿?裡面所有照片都會一起消失,無法還原')) return;
    try {
        await api.delete(`/api/albums/${albumId}`);
        showToast('相簿已刪除', 'success');
        closeModal('photoViewerModal');
        loadAlbums();
    } catch (err) {
        showToast(err.message || '刪除失敗', 'error');
    }
}

async function renameAlbumPrompt(albumId, currentTitle) {
    const newTitle = prompt('相簿新名稱', currentTitle);
    if (!newTitle || newTitle.trim() === currentTitle) return;
    try {
        await api.put(`/api/albums/${albumId}`, { title: newTitle.trim() });
        showToast('已更名', 'success');
        await loadAlbums();
        const data = await api.get(`/api/albums/user/${profileData.id}`);
        const updated = (data.albums || []).find(a => a.id === albumId);
        if (updated) openAlbumViewer(updated);
    } catch (err) {
        showToast(err.message || '更名失敗', 'error');
    }
}

async function toggleAlbumType(albumId, currentType) {
    const next = currentType === 'private' ? 'public' : 'private';
    const label = next === 'private' ? '私密(需申請才能看)' : '公開';
    if (!confirm(`要把這個相簿改成「${label}」嗎?`)) return;
    try {
        await api.put(`/api/albums/${albumId}`, { album_type: next });
        showToast(`已切換為${label}`, 'success');
        await loadAlbums();
        const data = await api.get(`/api/albums/user/${profileData.id}`);
        const updated = (data.albums || []).find(a => a.id === albumId);
        if (updated) openAlbumViewer(updated);
    } catch (err) {
        showToast(err.message || '切換失敗', 'error');
    }
}

async function setAlbumCover(albumId, photoId) {
    try {
        await api.put(`/api/albums/${albumId}`, { cover_photo_id: photoId });
        showToast('封面已更新', 'success');
        loadAlbums();
    } catch (err) {
        showToast(err.message || '設定封面失敗', 'error');
    }
}

/* ---- Private album request flow (viewer side) ---- */
function openPrivateAccessGate(album) {
    const modal = document.getElementById('photoViewerModal');
    const modalContent = modal.querySelector('.modal');
    modalContent.style.maxWidth = '440px';
    modalContent.style.padding = '2rem 1.6rem';

    let body;
    if (album.request_status === 'pending') {
        body = '<div class="text-center" style="padding:1rem 0;"><div style="font-size:2.5rem;">⏳</div><h3 style="margin:0.6rem 0;">已送出申請</h3><p class="text-muted">等待對方審核中,通過後就能看到照片</p></div>';
    } else if (album.request_status === 'rejected') {
        body = '<div class="text-center" style="padding:1rem 0;"><div style="font-size:2.5rem;">😔</div><h3 style="margin:0.6rem 0;">申請未通過</h3><p class="text-muted">這次對方沒同意,可以先互動建立信任</p></div>';
    } else {
        body = `
            <div class="text-center" style="padding:1rem 0;">
                <div style="font-size:2.5rem;">🔒</div>
                <h3 style="margin:0.6rem 0;">這是私密相簿</h3>
                <p class="text-muted" style="margin-bottom:1.2rem;">需要對方核准才能查看</p>
                <button class="btn btn-primary btn-block" onclick="requestAccess('${album.id}')">申請查看</button>
            </div>
        `;
    }

    modalContent.innerHTML = `
        <button class="modal-close" onclick="closeModal('photoViewerModal')" style="position:absolute;top:0.6rem;right:0.6rem;">✕</button>
        ${body}
    `;
    modal.classList.add('active');
    modal.classList.remove('hidden');
}

async function requestAccess(albumId) {
    try {
        await api.post(`/api/albums/${albumId}/request-access`);
        showToast('已送出申請,等對方審核', 'success');
        closeModal('photoViewerModal');
        loadAlbums();
    } catch (err) {
        showToast(err.message || '申請失敗', 'error');
    }
}

/* ---- Owner: pending requests management ---- */
async function renderPendingRequestsPanel() {
    let host = document.getElementById('pendingRequestsPanel');
    if (!host) {
        host = document.createElement('div');
        host.id = 'pendingRequestsPanel';
        const tabContent = document.getElementById('tabAlbums');
        if (tabContent) tabContent.insertBefore(host, tabContent.firstChild);
    }

    try {
        const data = await api.get('/api/albums/access-requests/pending');
        const reqs = data.requests || [];
        if (reqs.length === 0) {
            host.innerHTML = '';
            return;
        }
        host.innerHTML = `
            <div class="card mb-2" style="border-color:var(--gold-dark);">
                <div class="card-body">
                    <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.7rem;">
                        <span style="font-size:1.1rem;">🔔</span>
                        <strong>有 ${reqs.length} 位想看你的私密相簿</strong>
                    </div>
                    ${reqs.map(r => `
                        <div class="pending-request-row">
                            <img src="${escapeAttr(r.requester.avatar_url || '')}" alt="" class="pending-request-avatar" loading="lazy" decoding="async">
                            <div style="flex:1; min-width:0;">
                                <div><strong>${escapeHtmlA(r.requester.display_name)}</strong> 想看 <span style="color:var(--gold-light)">${escapeHtmlA(r.album.title)}</span></div>
                                <div class="text-muted" style="font-size:0.78rem;">${timeAgo(r.created_at)}</div>
                            </div>
                            <button class="btn btn-primary btn-sm" onclick="approveRequest('${r.id}')">核准</button>
                            <button class="btn btn-ghost btn-sm" onclick="rejectRequest('${r.id}')" style="color:var(--danger)">拒絕</button>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    } catch (err) {
        host.innerHTML = '';
    }
}

async function approveRequest(requestId) {
    try {
        await api.post(`/api/albums/access-requests/${requestId}/approve`);
        showToast('已核准', 'success');
        renderPendingRequestsPanel();
    } catch (err) {
        showToast(err.message || '核准失敗', 'error');
    }
}

async function rejectRequest(requestId) {
    if (!confirm('確定拒絕這個申請?')) return;
    try {
        await api.post(`/api/albums/access-requests/${requestId}/reject`);
        showToast('已拒絕', 'success');
        renderPendingRequestsPanel();
    } catch (err) {
        showToast(err.message || '拒絕失敗', 'error');
    }
}

function showCreateAlbum() {
    const m = document.getElementById('createAlbumModal');
    m.classList.add('active');         // legacy class — harmless
    m.classList.remove('hidden');      // generic pattern — actually shows
}

function closeModal(id) {
    const m = document.getElementById(id);
    if (!m) return;
    m.classList.remove('active');
    m.classList.add('hidden');
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
