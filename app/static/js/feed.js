// === Feed Page ===
requireAuth();

let currentCommentPostId = null;
let currentCategory = '';
const user = getUser();

// Category filter
function filterFeed(category) {
    currentCategory = category;
    document.querySelectorAll('.chip').forEach(c => {
        const isAll = !c.textContent.trim() || c.onclick?.toString().includes("''");
        if (category === '') {
            c.classList.toggle('active', c.onclick?.toString().includes("''"));
        } else {
            c.classList.toggle('active', c.textContent.trim() === getCategoryLabel(category));
        }
    });
    // Re-select chips properly
    document.querySelectorAll('.chip').forEach(c => {
        const handler = c.getAttribute('onclick') || '';
        const match = handler.match(/filterFeed\('([^']*)'\)/);
        if (match) {
            c.classList.toggle('active', match[1] === category);
        }
    });
    loadFeed();
}

function getCategoryLabel(cat) {
    const map = { daily: '日常', food: '美食', travel: '旅行', nightlife: '夜生活', mood: '心情' };
    return map[cat] || '全部';
}

// Set avatar
const feedAvatar = document.getElementById('feedAvatar');
if (user.avatar_url) feedAvatar.src = user.avatar_url;
else feedAvatar.style.background = 'var(--gradient-gold)';

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
        let feedUrl = '/api/posts/feed?page=1&per_page=20';
        if (currentCategory) feedUrl += `&category=${currentCategory}`;
        const data = await api.get(feedUrl);
        const feed = document.getElementById('postsFeed');

        if (data.posts.length === 0) {
            feed.innerHTML = '<div class="text-center text-muted" style="padding:4rem;">還沒有動態，成為第一個發文的人！</div>';
            return;
        }

        feed.innerHTML = data.posts.map(p => `
            <div class="card post-card" data-post-id="${p.id}">
                <div class="post-header">
                    <img src="${p.author.avatar_url || ''}" class="post-avatar" alt="" style="${p.author.avatar_url ? '' : 'background:var(--gradient-gold)'}">
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
                    <div class="post-action" onclick="toggleComments('${p.id}')">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                        <span>${p.comments_count}</span>
                    </div>
                </div>
                <!-- Inline comments section (hidden by default) -->
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
    try {
        const data = await api.post(`/api/posts/${postId}/like`);
        el.querySelector('span').textContent = data.likes_count;
        el.classList.toggle('liked', data.liked);
        el.querySelector('svg').setAttribute('fill', data.liked ? 'currentColor' : 'none');
    } catch (err) {
        showToast('操作失敗', 'error');
    }
}

// Toggle inline comments (IG style)
async function toggleComments(postId) {
    const section = document.getElementById(`comments-${postId}`);
    if (!section) return;

    if (section.classList.contains('hidden')) {
        section.classList.remove('hidden');
        await loadComments(postId);
        // Focus the input
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
                    <img src="${c.author.avatar_url || ''}" class="comment-avatar" alt="" style="${c.author.avatar_url ? '' : 'background:var(--gradient-gold)'}">
                    <div class="comment-body">
                        <span class="comment-author">${c.author.display_name}</span>
                        <span class="comment-text">${c.content}</span>
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
        // Update comment count in actions
        const card = document.querySelector(`[data-post-id="${postId}"]`);
        if (card) {
            const countSpan = card.querySelectorAll('.post-action span')[1];
            if (countSpan) countSpan.textContent = parseInt(countSpan.textContent || '0') + 1;
        }
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
                    <img src="${g.author.avatar_url || ''}" alt="${g.author.display_name}" style="${g.author.avatar_url ? '' : 'background:var(--gradient-gold)'}">
                </div>
                <div class="story-name">${g.author.display_name}</div>
            </div>
        `).join('');
    } catch (e) { /* ignore */ }
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
