// === Messages Page ===
requireAuth();

async function loadConversations() {
    try {
        const data = await api.get('/api/messages/conversations');
        const list = document.getElementById('convListContent');

        if (data.conversations.length === 0) {
            list.innerHTML = '<div class="text-muted text-center" style="padding:2rem;">還沒有對話<br><a href="/explore" style="color:var(--rose-light)">去探索會員</a></div>';
            return;
        }

        list.innerHTML = data.conversations.map(c => `
            <div class="conversation-item" onclick="window.location.href='/chat/${c.other_user.id}'">
                <img src="${c.other_user.avatar_url || ''}" class="conversation-avatar" alt="" style="${c.other_user.avatar_url ? '' : 'background:var(--gradient-rose)'}">
                <div class="conversation-info">
                    <div class="conversation-name">
                        ${c.other_user.display_name}
                        ${c.other_user.is_online ? '<span style="display:inline-block;width:8px;height:8px;background:var(--success);border-radius:50%;margin-left:4px;"></span>' : ''}
                    </div>
                    <div class="conversation-preview">${c.last_message}</div>
                </div>
                ${c.unread_count > 0 ? `<div class="conversation-unread">${c.unread_count}</div>` : ''}
            </div>
        `).join('');
    } catch (err) {
        document.getElementById('convListContent').innerHTML = '<div class="text-muted text-center" style="padding:2rem;">載入失敗</div>';
    }
}

loadConversations();
