// === Feed Page ===
requireAuth();

let currentCommentPostId = null;
const user = getUser();

// Set avatar
const feedAvatar = document.getElementById('feedAvatar');
if (user.avatar_url) feedAvatar.src = user.avatar_url;
else feedAvatar.style.background = 'var(--gradient-rose)';

// Image preview
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

async function createPost() {
    const content = document.getElementById('postContent').value.trim();
    if (!content) return showToast('請輸入內容', 'error');

    const formData = new FormData();
    formData.append('content', content);
    const imageFile = document.getElementById('postImage').files[0];
    if (imageFile) formData.append('image', imageFile);

    try {
        await api.post('/api/posts', formData, true);
        document.getElementById('postContent').value = '';
        clearImage();
        showToast('發布成功！', 'success');
        loadFeed();
    } catch (err) {
        showToast(err.message || '發布失敗', 'error');
    }
}

async function loadFeed() {
    try {
        const data = await api.get('/api/posts/feed?page=1&per_page=20');
        const feed = document.getElementById('postsFeed');

        if (data.posts.length === 0) {
            feed.innerHTML = '<div class="text-center text-muted" style="padding:4rem;">還沒有動態，成為第一個發文的人！</div>';
            return;
        }

        feed.innerHTML = data.posts.map(p => `
            <div class="card post-card">
                <div class="post-header">
                    <img src="${p.author.avatar_url || ''}" class="post-avatar" alt="" style="${p.author.avatar_url ? '' : 'background:var(--gradient-rose)'}">
                    <div>
                        <a href="/profile/${p.author.username}" class="post-author" style="color:var(--text-primary)">${p.author.display_name}</a>
                        <div class="post-time">${timeAgo(p.created_at)}</div>
                    </div>
                </div>
                ${p.image_url ? `<img src="${p.image_url}" class="post-image" alt="">` : ''}
                <div class="post-content">${p.content}</div>
                <div class="post-likes">${p.likes_count > 0 ? p.likes_count + ' 個讚' : ''}</div>
                <div class="post-actions">
                    <div class="post-action ${p.is_liked ? 'liked' : ''}" onclick="toggleLike('${p.id}', this)">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="${p.is_liked ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
                        <span>${p.likes_count}</span>
                    </div>
                    <div class="post-action" onclick="openComments('${p.id}')">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                        <span>${p.comments_count}</span>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (err) {
        document.getElementById('postsFeed').innerHTML = '<div class="text-center text-muted" style="padding:4rem;">載入失敗</div>';
    }
}

async function toggleLike(postId, el) {
    try {
        const data = await api.post(`/api/posts/${postId}/like`);
        el.querySelector('span').textContent = data.likes_count;
        el.classList.toggle('liked', data.liked);
        el.querySelector('svg').setAttribute('fill', data.liked ? 'currentColor' : 'none');
    } catch (err) {
        showToast('操作失敗', 'error');
    }
}

async function openComments(postId) {
    currentCommentPostId = postId;
    document.getElementById('commentsModal').classList.add('active');
    try {
        const data = await api.get(`/api/posts/${postId}/comments`);
        const list = document.getElementById('commentsList');
        if (data.comments.length === 0) {
            list.innerHTML = '<p class="text-muted text-center" style="padding:1rem">還沒有留言</p>';
        } else {
            list.innerHTML = data.comments.map(c => `
                <div style="display:flex; gap:0.6rem; margin-bottom:0.8rem;">
                    <img src="${c.author.avatar_url || ''}" class="post-avatar" style="width:32px; height:32px; ${c.author.avatar_url ? '' : 'background:var(--gradient-rose)'}" alt="">
                    <div>
                        <span style="font-weight:600; font-size:0.85rem">${c.author.display_name}</span>
                        <span class="text-muted" style="font-size:0.75rem; margin-left:0.5rem">${timeAgo(c.created_at)}</span>
                        <p style="font-size:0.9rem; margin-top:0.2rem">${c.content}</p>
                    </div>
                </div>
            `).join('');
        }
    } catch (err) {
        document.getElementById('commentsList').innerHTML = '<p class="text-muted text-center">載入失敗</p>';
    }
}

function closeComments() {
    document.getElementById('commentsModal').classList.remove('active');
    currentCommentPostId = null;
}

async function submitComment() {
    if (!currentCommentPostId) return;
    const input = document.getElementById('commentInput');
    const content = input.value.trim();
    if (!content) return;

    const formData = new FormData();
    formData.append('content', content);

    try {
        await api.post(`/api/posts/${currentCommentPostId}/comments`, formData, true);
        input.value = '';
        openComments(currentCommentPostId);
        loadFeed(); // Refresh counts
    } catch (err) {
        showToast('留言失敗', 'error');
    }
}

// Load stories
async function loadStories() {
    try {
        const data = await api.get('/api/posts/stories/active');
        const bar = document.getElementById('storiesBar');
        if (data.story_groups.length === 0) {
            bar.style.display = 'none';
            return;
        }
        bar.innerHTML = data.story_groups.map(g => `
            <div class="story-circle" onclick="viewStory('${g.stories[0].image_url}')">
                <div class="story-avatar-ring">
                    <img src="${g.author.avatar_url || ''}" alt="${g.author.display_name}" style="${g.author.avatar_url ? '' : 'background:var(--gradient-rose)'}">
                </div>
                <div class="story-name">${g.author.display_name}</div>
            </div>
        `).join('');
    } catch (e) { /* ignore */ }
}

function viewStory(imageUrl) {
    // Simple story viewer
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.95);z-index:3000;display:flex;align-items:center;justify-content:center;cursor:pointer;';
    overlay.innerHTML = `<img src="${imageUrl}" style="max-width:90%;max-height:90%;object-fit:contain;border-radius:12px;">`;
    overlay.onclick = () => overlay.remove();
    document.body.appendChild(overlay);
}

loadStories();
loadFeed();
