// === Messages Page ===
requireAuth();

let allConversations = [];

async function loadConversations() {
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

    list.innerHTML = conversations.map(c => `
        <div class="conversation-item" onclick="window.location.href='/chat/${c.other_user.id}'" data-unread="${c.unread_count || 0}">
            <img src="${c.other_user.avatar_url || ''}" class="conversation-avatar" alt="" style="${c.other_user.avatar_url ? '' : 'background:var(--gradient-gold)'}">
            <div class="conversation-info">
                <div class="conversation-name">
                    ${c.other_user.display_name}
                    ${c.other_user.is_online ? '<span style="display:inline-block;width:8px;height:8px;background:var(--success);border-radius:50%;margin-left:4px;"></span>' : ''}
                </div>
                <div class="conversation-preview">${c.last_message || ''}</div>
            </div>
            ${c.unread_count > 0 ? `<div class="conversation-unread">${c.unread_count}</div>` : ''}
        </div>
    `).join('');
}

function filterConv(type) {
    // Update active chip
    document.querySelectorAll('.chip').forEach(ch => ch.classList.remove('active'));
    event.target.classList.add('active');

    if (type === 'all') {
        renderConversations(allConversations);
    } else if (type === 'unread') {
        renderConversations(allConversations.filter(c => c.unread_count > 0));
    } else if (type === 'saved') {
        renderConversations(allConversations.filter(c => c.is_saved));
    }
}

// Search conversations
const convSearch = document.getElementById('convSearch');
if (convSearch) {
    convSearch.addEventListener('input', function() {
        const q = this.value.toLowerCase();
        if (!q) {
            renderConversations(allConversations);
            return;
        }
        renderConversations(allConversations.filter(c =>
            c.other_user.display_name.toLowerCase().includes(q) ||
            (c.last_message || '').toLowerCase().includes(q)
        ));
    });
}

loadConversations();
