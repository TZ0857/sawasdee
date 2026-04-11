// === Chat Page ===
requireAuth();

const currentUser = getUser();
let chatPartner = null;

async function loadChatUser() {
    try {
        const user = await api.get(`/api/users/${chatUserId}`);
        chatPartner = user;
        document.getElementById('chatName').textContent = user.display_name;
        document.getElementById('chatStatus').textContent = user.is_online ? '線上' : '離線';
        const avatar = document.getElementById('chatAvatar');
        if (user.avatar_url) avatar.src = user.avatar_url;
        else avatar.style.background = 'var(--gradient-rose)';
    } catch (err) {
        showToast('無法載入用戶資料', 'error');
    }
}

async function loadMessages() {
    try {
        const data = await api.get(`/api/messages/chat/${chatUserId}?page=1&per_page=50`);
        const container = document.getElementById('chatMessages');

        if (data.messages.length === 0) {
            container.innerHTML = '<div class="flex-center" style="flex:1;color:var(--text-muted)">開始你們的第一段對話 💌</div>';
            return;
        }

        container.innerHTML = data.messages.map(m => {
            const isSent = m.sender_id === currentUser.id;
            return `
                <div class="message-bubble ${isSent ? 'message-sent' : 'message-received'}">
                    <div>${m.content}</div>
                    ${m.translated_content && m.translated_content !== m.content ? `<div class="message-translated">🌐 ${m.translated_content}</div>` : ''}
                    <div class="message-time" style="text-align:${isSent ? 'right' : 'left'}; color:${isSent ? 'rgba(255,255,255,0.5)' : 'var(--text-muted)'}">
                        ${timeAgo(m.created_at)} ${m.is_read && isSent ? '✓✓' : ''}
                    </div>
                </div>
            `;
        }).join('');

        container.scrollTop = container.scrollHeight;
    } catch (err) {
        document.getElementById('chatMessages').innerHTML = '<div class="flex-center" style="flex:1;color:var(--text-muted)">載入失敗</div>';
    }
}

async function sendMessage() {
    const input = document.getElementById('messageInput');
    const content = input.value.trim();
    if (!content) return;

    input.value = '';
    try {
        await api.post('/api/messages/send', { receiver_id: chatUserId, content });
        loadMessages();
    } catch (err) {
        showToast('傳送失敗', 'error');
    }
}

// Enter key to send
document.getElementById('messageInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});

// Auto refresh
setInterval(loadMessages, 5000);

loadChatUser();
loadMessages();
