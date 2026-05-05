// === Messages Page ===
requireAuth();

let allConversations = [];

function _showConvSkeleton() {
    document.getElementById('convListContent').innerHTML = Array.from({length: 5}, () => `
        <div class="skeleton-row">
            <div class="skeleton skeleton-avatar"></div>
            <div>
                <div class="skeleton skeleton-line w-50"></div>
                <div class="skeleton skeleton-line w-90"></div>
            </div>
        </div>
    `).join('');
}

async function loadConversations() {
    _showConvSkeleton();
    try {
        const data = await api.get('/api/messages/conversations');
        allConversations = data.conversations || [];
        renderConversations(allConversations);
    } catch (err) {
        document.getElementById('convListContent').innerHTML = '<div class="text-muted text-center" style="padding:2rem;">載入失敗</div>';
    }
}

function renderConversations(conversations) {
    const list = document.getElementById('convListContent');

    if (conversations.length === 0) {
        list.innerHTML = '<div class="text-muted text-center" style="padding:2rem;">還沒有對話<br><a href="/explore" style="color:var(--gold)">去探索會員</a></div>';
        return;
    }

    list.innerHTML = conversations.map(c => {
        const profilePath = `/profile/${encodeURIComponent(c.other_user.username)}`;
        return `
        <div class="conversation-item" onclick="window.location.href='/chat/${c.other_user.id}'" data-unread="${c.unread_count || 0}">
            <img src="${c.other_user.avatar_url || ''}" class="conversation-avatar" alt="" loading="lazy" decoding="async"
                 title="點擊查看個人頁"
                 onclick="event.stopPropagation(); window.location.href='${profilePath}'; return false;"
                 style="${c.other_user.avatar_url ? '' : 'background:var(--gradient-gold)'}; cursor:pointer;">
            <div class="conversation-info">
                <div class="conversation-name">
                    ${c.other_user.display_name}
                    ${c.other_user.is_online ? '<span style="display:inline-block;width:8px;height:8px;background:var(--success);border-radius:50%;margin-left:4px;"></span>' : ''}
                </div>
                <div class="conversation-preview">${c.last_message || ''}</div>
            </div>
            ${c.unread_count > 0 ? `<div class="conversation-unread">${c.unread_count}</div>` : ''}
        </div>
        `;
    }).join('');
}

function filterConv(type, btnEl) {
    // Update active chip — accept the tapped button explicitly so we don't
    // rely on the global `event` (undefined under some mobile browsers /
    // strict mode bundlers).
    document.querySelectorAll('.chip').forEach(ch => ch.classList.remove('active'));
    const target = btnEl || (typeof event !== 'undefined' ? event.target : null);
    if (target && target.classList) target.classList.add('active');

    if (type === 'all') {
        renderConversations(allConversations);
    } else if (type === 'unread') {
        renderConversations(allConversations.filter(c => c.unread_count > 0));
    }
    // 'saved' filter intentionally removed (chip dropped from UI; the field
    // never existed on Conversation so it always returned 0 results).
}

// Search conversations — debounced 200ms so we don't re-render the list
// on every keystroke (cheap when there are few conversations, but adds up
// if the user pastes a long string).
const convSearch = document.getElementById('convSearch');
if (convSearch) {
    let _convSearchTimer = null;
    convSearch.addEventListener('input', function() {
        const val = this.value;
        clearTimeout(_convSearchTimer);
        _convSearchTimer = setTimeout(() => {
            const q = val.toLowerCase().trim();
            if (!q) { renderConversations(allConversations); return; }
            renderConversations(allConversations.filter(c =>
                c.other_user.display_name.toLowerCase().includes(q) ||
                (c.last_message || '').toLowerCase().includes(q)
            ));
        }, 200);
    });
}

loadConversations();
