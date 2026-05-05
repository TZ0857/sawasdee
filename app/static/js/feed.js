// === Feed Page ===
requireAuth();

let currentFilter = '';            // '' = all, 'liked' = only posts I've liked
let currentCommentPostId = null;
const user = getUser();

/* ---------- Filter chips: All / Liked ---------- */
function filterFeed(f) {
    currentFilter = f || '';
    document.querySelectorAll('[data-feed-filter]').forEach(c => {
        c.classList.toggle('active', (c.dataset.feedFilter || '') === currentFilter);
    });
    loadFeed();
}

/* ---------- Avatar in composer ---------- */
const feedAvatar = document.getElementById('feedAvatar');
if (user.avatar_url) feedAvatar.src = user.avatar_url;
else feedAvatar.style.background = 'var(--gradient-gold)';

/* ---------- Image preview ---------- */
document.getElementById('postImage').addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = (ev) => {
            document.getElementById('previewImg').src = ev.target.result;
            document.getElementById('imagePreview').classList.remove('hidden');
        };
        reader.readAsDataURL(file);
    }
});

function clearImage() {
    document.getElementById('postImage').value = '';
    document.getElementById('imagePreview').classList.add('hidden');
}

/* ---------- Video preview ---------- */
const MAX_VIDEO_SECONDS = 60;
const MAX_VIDEO_BYTES = 100 * 1024 * 1024;

document.getElementById('postVideo').addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (file.size > MAX_VIDEO_BYTES) {
        showToast('影片檔案超過 100MB,請壓縮後再上傳', 'error');
        e.target.value = '';
        return;
    }

    const url = URL.createObjectURL(file);
    const video = document.getElementById('previewVideo');
    video.onloadedmetadata = () => {
        if (video.duration > MAX_VIDEO_SECONDS + 0.5) {
            showToast(`影片不能超過 ${MAX_VIDEO_SECONDS} 秒(目前 ${Math.round(video.duration)} 秒)`, 'error');
            URL.revokeObjectURL(url);
            video.removeAttribute('src');
            video.load();
            document.getElementById('videoPreview').classList.add('hidden');
            e.target.value = '';
            return;
        }
        document.getElementById('videoPreview').classList.remove('hidden');
    };
    video.src = url;
});

function clearVideo() {
    const input = document.getElementById('postVideo');
    const video = document.getElementById('previewVideo');
    if (video.src) URL.revokeObjectURL(video.src);
    video.removeAttribute('src');
    video.load();
    input.value = '';
    document.getElementById('videoPreview').classList.add('hidden');
}

/* ---------- Audio recording (MediaRecorder API) ---------- */
let mediaRecorder = null;
let audioChunks = [];
let audioBlob = null;
let recordTimer = null;
let recordStartedAt = 0;
const MAX_RECORD_MS = 60_000;

function pickMimeType() {
    const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/mpeg'];
    for (const t of candidates) {
        if (window.MediaRecorder && MediaRecorder.isTypeSupported(t)) return t;
    }
    return '';
}

async function toggleRecording() {
    if (!navigator.mediaDevices || !window.MediaRecorder) {
        return showToast('此瀏覽器不支援錄音', 'error');
    }
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        stopRecording();
        return;
    }
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mime = pickMimeType();
        mediaRecorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
        audioChunks = [];
        mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
        mediaRecorder.onstop = () => {
            stream.getTracks().forEach(t => t.stop());
            audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
            const url = URL.createObjectURL(audioBlob);
            document.getElementById('previewAudio').src = url;
            document.getElementById('audioPreview').classList.remove('hidden');
            updateAudioButton(false);
        };
        mediaRecorder.start();
        recordStartedAt = Date.now();
        updateAudioButton(true);
        // Auto-stop after MAX_RECORD_MS
        recordTimer = setInterval(() => {
            const elapsed = Date.now() - recordStartedAt;
            if (elapsed >= MAX_RECORD_MS) {
                stopRecording();
                showToast('已達 60 秒上限', 'success');
            } else {
                document.getElementById('audioBtnLabel').textContent = `停止 (${Math.ceil((MAX_RECORD_MS - elapsed) / 1000)}s)`;
            }
        }, 250);
    } catch (err) {
        showToast('無法存取麥克風: ' + (err.message || '請允許錄音權限'), 'error');
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') mediaRecorder.stop();
    if (recordTimer) { clearInterval(recordTimer); recordTimer = null; }
}

function updateAudioButton(isRecording) {
    const btn = document.getElementById('audioBtn');
    const label = document.getElementById('audioBtnLabel');
    if (isRecording) {
        btn.style.color = 'var(--danger, #ef4444)';
        btn.title = '點擊停止錄音';
        label.textContent = '錄音中…';
    } else {
        btn.style.color = 'var(--text-muted)';
        btn.title = '錄製語音 (最多 60 秒)';
        label.textContent = '語音';
    }
}

function clearAudio() {
    audioBlob = null;
    audioChunks = [];
    const a = document.getElementById('previewAudio');
    if (a.src) URL.revokeObjectURL(a.src);
    a.removeAttribute('src');
    document.getElementById('audioPreview').classList.add('hidden');
}

/* ---------- Create post ---------- */
async function createPost() {
    const content = document.getElementById('postContent').value.trim();
    const imageFile = document.getElementById('postImage').files[0];
    const videoFile = document.getElementById('postVideo').files[0];
    const hasAudio = !!audioBlob;

    if (!content && !imageFile && !videoFile && !hasAudio) {
        return showToast('請輸入文字、加入照片、影片或錄製語音', 'error');
    }

    const formData = new FormData();
    formData.append('content', content);
    if (imageFile) formData.append('image', imageFile);
    if (videoFile) formData.append('video', videoFile);
    if (hasAudio) {
        const ext = (audioBlob.type.includes('webm')) ? 'webm'
                  : (audioBlob.type.includes('mp4')) ? 'm4a'
                  : 'audio';
        formData.append('audio', audioBlob, `voice.${ext}`);
    }

    try {
        await api.post('/api/posts', formData, true);
        document.getElementById('postContent').value = '';
        clearImage();
        clearVideo();
        clearAudio();
        showToast('發布成功！', 'success');
        loadFeed();
    } catch (err) {
        showToast(err.message || '發布失敗', 'error');
    }
}

/* ---------- Feed rendering ---------- */
function escapeHtml(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function renderImage(url) {
    if (!url) return '';
    // onerror hides the broken image gracefully if the upload was lost
    // (Railway containers have ephemeral filesystem — files in /uploads
    //  vanish on every redeploy unless a Volume is mounted there).
    const safe = escapeHtml(url);
    return `<img src="${safe}" class="post-image" alt="" loading="lazy" decoding="async" onerror="this.outerHTML='<div class=&quot;post-image-missing&quot;>📷 圖片暫時無法載入</div>'">`;
}

function renderVideo(url) {
    if (!url) return '';
    const safe = escapeHtml(url);
    return `<video class="post-video" controls preload="metadata" playsinline src="${safe}"
        onerror="this.outerHTML='<div class=&quot;post-image-missing&quot;>🎬 影片暫時無法載入</div>'"></video>`;
}

function renderAudio(url) {
    if (!url) return '';
    const safe = escapeHtml(url);
    return `<div class="post-audio-wrap"><audio class="post-audio" controls preload="metadata" src="${safe}"></audio></div>`;
}

async function loadFeed() {
    const feedSkeleton = document.getElementById('postsFeed');
    if (feedSkeleton && !feedSkeleton.querySelector('.post-card')) {
        feedSkeleton.innerHTML = Array.from({length: 3}, () => `
            <div class="card post-card">
                <div class="post-header">
                    <div class="skeleton skeleton-avatar"></div>
                    <div style="flex:1">
                        <div class="skeleton skeleton-line w-30"></div>
                        <div class="skeleton skeleton-line w-50"></div>
                    </div>
                </div>
                <div class="skeleton" style="aspect-ratio:4/5; width:100%; max-height:560px; border-radius:0;"></div>
                <div style="padding:0.85rem 1rem;">
                    <div class="skeleton skeleton-line w-90"></div>
                    <div class="skeleton skeleton-line w-70"></div>
                </div>
            </div>
        `).join('');
    }
    try {
        let feedUrl = '/api/posts/feed?page=1&per_page=20';
        if (currentFilter) feedUrl += `&filter=${currentFilter}`;
        const data = await api.get(feedUrl);
        const feed = document.getElementById('postsFeed');

        if (!data.posts || data.posts.length === 0) {
            const msg = currentFilter === 'liked'
                ? '還沒有按過喜歡的動態。'
                : '還沒有動態，成為第一個發文的人！';
            feed.innerHTML = `<div class="text-center text-muted" style="padding:4rem;">${msg}</div>`;
            return;
        }

        feed.innerHTML = data.posts.map(p => `
            <div class="card post-card" data-post-id="${p.id}">
                <div class="post-header">
                    <img src="${escapeHtml(p.author.avatar_url || '')}" class="post-avatar" alt="" loading="lazy" decoding="async" style="${p.author.avatar_url ? '' : 'background:var(--gradient-gold)'}">
                    <div>
                        <a href="/profile/${escapeHtml(p.author.username)}" class="post-author" style="color:var(--text-primary)">${escapeHtml(p.author.display_name)}</a>
                        <div class="post-time">${timeAgo(p.created_at)}</div>
                    </div>
                </div>
                ${renderImage(p.image_url)}
                ${renderVideo(p.video_url)}
                ${renderAudio(p.audio_url)}
                ${p.content ? `<div class="post-content">${escapeHtml(p.content)}</div>` : ''}
                <div class="post-likes">${p.likes_count > 0 ? p.likes_count + ' 個讚' : ''}</div>
                <div class="post-actions">
                    <div class="post-action ${p.is_liked ? 'liked' : ''}" onclick="toggleLike('${p.id}', this)">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="${p.is_liked ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
                        <span>${p.likes_count}</span>
                    </div>
                    <div class="post-action" onclick="toggleComments('${p.id}')">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                        <span>${p.comments_count}</span>
                    </div>
                </div>
                <div class="comments-section hidden" id="comments-${p.id}">
                    <div class="comments-list" id="commentsList-${p.id}"></div>
                    <div class="comment-input-row">
                        <input type="text" class="form-input comment-input" id="commentInput-${p.id}" placeholder="留言..." onkeydown="if(event.key==='Enter')submitComment('${p.id}')">
                        <button class="btn btn-primary btn-sm comment-send-btn" onclick="submitComment('${p.id}')">送出</button>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (err) {
        document.getElementById('postsFeed').innerHTML = '<div class="text-center text-muted" style="padding:4rem;">載入失敗</div>';
    }
}

async function toggleLike(postId, el) {
    // Optimistic UI: flip heart + count immediately, reconcile with server later.
    const wasLiked = el.classList.contains('liked');
    const willBeLiked = !wasLiked;
    const countEl = el.querySelector('span');
    const svg = el.querySelector('svg');
    const prevCount = parseInt(countEl.textContent || '0', 10) || 0;
    const optimisticCount = Math.max(0, prevCount + (willBeLiked ? 1 : -1));
    countEl.textContent = optimisticCount;
    el.classList.toggle('liked', willBeLiked);
    if (svg) svg.setAttribute('fill', willBeLiked ? 'currentColor' : 'none');
    el.style.pointerEvents = 'none';   // dedupe rapid taps
    try {
        const data = await api.post(`/api/posts/${postId}/like`);
        // Reconcile with server truth
        countEl.textContent = data.likes_count;
        el.classList.toggle('liked', data.liked);
        if (svg) svg.setAttribute('fill', data.liked ? 'currentColor' : 'none');
        if (currentFilter === 'liked' && !data.liked) {
            const card = el.closest('.post-card');
            if (card) card.remove();
        }
    } catch (err) {
        // Roll back on failure
        countEl.textContent = prevCount;
        el.classList.toggle('liked', wasLiked);
        if (svg) svg.setAttribute('fill', wasLiked ? 'currentColor' : 'none');
        showToast('操作失敗', 'error');
    } finally {
        el.style.pointerEvents = '';
    }
}

/* ---------- Inline comments (IG style) ---------- */
async function toggleComments(postId) {
    const section = document.getElementById(`comments-${postId}`);
    if (!section) return;
    if (section.classList.contains('hidden')) {
        section.classList.remove('hidden');
        await loadComments(postId);
        const input = document.getElementById(`commentInput-${postId}`);
        if (input) input.focus();
    } else {
        section.classList.add('hidden');
    }
}

async function loadComments(postId) {
    const list = document.getElementById(`commentsList-${postId}`);
    if (!list) return;
    list.innerHTML = '<div class="text-center text-muted" style="padding:0.5rem"><div class="spinner" style="width:20px;height:20px"></div></div>';
    try {
        const data = await api.get(`/api/posts/${postId}/comments`);
        if (data.comments.length === 0) {
            list.innerHTML = '<p class="text-muted" style="padding:0.3rem 0; font-size:0.85rem">還沒有留言，來說點什麼吧</p>';
        } else {
            list.innerHTML = data.comments.map(c => `
                <div class="comment-item">
                    <img src="${escapeHtml(c.author.avatar_url || '')}" class="comment-avatar" alt="" loading="lazy" decoding="async" style="${c.author.avatar_url ? '' : 'background:var(--gradient-gold)'}">
                    <div class="comment-body">
                        <span class="comment-author">${escapeHtml(c.author.display_name)}</span>
                        <span class="comment-text">${escapeHtml(c.content)}</span>
                        <span class="comment-time">${timeAgo(c.created_at)}</span>
                    </div>
                </div>
            `).join('');
        }
    } catch (err) {
        list.innerHTML = '<p class="text-muted" style="font-size:0.85rem">載入失敗</p>';
    }
}

async function submitComment(postId) {
    const input = document.getElementById(`commentInput-${postId}`);
    if (!input) return;
    const content = input.value.trim();
    if (!content) return;
    const formData = new FormData();
    formData.append('content', content);
    try {
        await api.post(`/api/posts/${postId}/comments`, formData, true);
        input.value = '';
        await loadComments(postId);
        const card = document.querySelector(`[data-post-id="${postId}"]`);
        if (card) {
            const countSpan = card.querySelectorAll('.post-action span')[1];
            if (countSpan) countSpan.textContent = parseInt(countSpan.textContent || '0') + 1;
        }
    } catch (err) {
        showToast('留言失敗', 'error');
    }
}

/* ---------- Stories ---------- */
async function loadStories() {
    const bar = document.getElementById('storiesBar');
    bar.style.display = '';
    let storyGroups = [];
    try {
        const data = await api.get('/api/posts/stories/active');
        storyGroups = data.story_groups || [];
    } catch (e) { /* ignore */ }

    // Always show the user's own "add story" circle first
    const myAvatar = user.avatar_url ? escapeHtml(user.avatar_url) : '';
    const myStoryCircle = `
        <div class="story-circle story-mine" onclick="document.getElementById('storyUploadInput').click()">
            <div class="story-avatar-ring story-add-ring">
                <img src="${myAvatar}" alt="${escapeHtml(user.display_name || '我')}" loading="lazy" decoding="async" style="${myAvatar ? '' : 'background:var(--gradient-gold)'}">
                <div class="story-add-plus">+</div>
            </div>
            <div class="story-name">你的限動</div>
        </div>
    `;

    // Filter out my own group from "others" so we don't render twice
    const myId = String(user.id);
    const others = storyGroups.filter(g => String(g.author.id) !== myId);

    bar.innerHTML = myStoryCircle + others.map(g => `
        <div class="story-circle" onclick="viewStory('${escapeHtml(g.stories[0].image_url)}')">
            <div class="story-avatar-ring">
                <img src="${escapeHtml(g.author.avatar_url || '')}" alt="${escapeHtml(g.author.display_name)}" loading="lazy" decoding="async" style="${g.author.avatar_url ? '' : 'background:var(--gradient-gold)'}">
            </div>
            <div class="story-name">${escapeHtml(g.author.display_name)}</div>
        </div>
    `).join('');

    // Hidden file input (created once)
    if (!document.getElementById('storyUploadInput')) {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*';
        input.id = 'storyUploadInput';
        input.style.display = 'none';
        input.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) uploadStory(file);
            e.target.value = '';
        });
        document.body.appendChild(input);
    }
}

async function uploadStory(file) {
    const MAX = 20 * 1024 * 1024;
    if (file.size > MAX) {
        showToast('圖片超過 20MB', 'error');
        return;
    }
    const fd = new FormData();
    fd.append('image', file);
    fd.append('caption', '');
    showToast('上傳中…', 'success');
    try {
        await api.post('/api/posts/stories', fd, true);
        showToast('限動已發布,24 小時內可見', 'success');
        loadStories();
    } catch (err) {
        showToast('上傳失敗', 'error');
    }
}

function viewStory(imageUrl) {
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.95);z-index:3000;display:flex;align-items:center;justify-content:center;cursor:pointer;';
    overlay.innerHTML = `<img src="${imageUrl}" style="max-width:90%;max-height:90%;object-fit:contain;border-radius:12px;">`;
    overlay.onclick = () => overlay.remove();
    document.body.appendChild(overlay);
}

loadStories();
loadFeed();
