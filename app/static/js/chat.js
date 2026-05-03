// === Chat Page ===
requireAuth();

const currentUser = getUser();
let chatPartner = null;
let autoTranslate = false;
let isSending = false;
let lastMsgCount = 0;

async function loadChatUser() {
    try {
        const user = await api.get(`/api/users/${chatUserId}`);
        chatPartner = user;
        document.getElementById('chatName').textContent = user.display_name;
        document.getElementById('chatStatus').textContent = user.is_online ? '線上' : '離線';
        const avatar = document.getElementById('chatAvatar');
        if (user.avatar_url) avatar.src = user.avatar_url;
        else avatar.style.background = 'var(--gradient-gold)';
    } catch (err) {
        showToast('無法載入用戶資料', 'error');
    }
}

function renderMessage(m, isSent) {
    const ts = m.created_at.endsWith('Z') ? m.created_at : m.created_at + 'Z';
    const showTranslation = autoTranslate && m.translated_content && m.translated_content !== m.content;
    const readStatus = isSent ? (m.is_read ? ' <span style="color:var(--gold);">✓✓</span>' : ' <span style="opacity:0.4">✓</span>') : '';
    return `
        <div class="message-bubble ${isSent ? 'message-sent' : 'message-received'}">
            <div>${m.content}</div>
            ${showTranslation ? `<div class="message-translated">🌐 ${m.translated_content}</div>` : ''}
            <div class="message-time" style="text-align:${isSent ? 'right' : 'left'}; color:${isSent ? 'rgba(255,255,255,0.5)' : 'var(--text-muted)'}">
                ${timeAgo(ts)}${readStatus}
            </div>
        </div>
    `;
}

async function loadMessages(scrollToBottom = false) {
    try {
        const data = await api.get(`/api/messages/chat/${chatUserId}?page=1&per_page=50`);
        const container = document.getElementById('chatMessages');

        if (data.messages.length === 0) {
            container.innerHTML = '<div class="flex-center" style="flex:1;color:var(--text-muted)">開始你們的第一段對話 💌</div>';
            lastMsgCount = 0;
            return;
        }

        const shouldScroll = scrollToBottom || data.messages.length !== lastMsgCount ||
            container.scrollHeight - container.scrollTop - container.clientHeight < 80;

        container.innerHTML = data.messages.map(m => {
            const isSent = m.sender_id === currentUser.id;
            return renderMessage(m, isSent);
        }).join('');

        lastMsgCount = data.messages.length;

        if (shouldScroll) {
            container.scrollTop = container.scrollHeight;
        }
    } catch (err) {
        // Don't overwrite messages on refresh error
        if (lastMsgCount === 0) {
            document.getElementById('chatMessages').innerHTML = '<div class="flex-center" style="flex:1;color:var(--text-muted)">載入失敗</div>';
        }
    }
}

async function sendMessage() {
    const input = document.getElementById('messageInput');
    const content = input.value.trim();
    if (!content || isSending) return;

    isSending = true;
    input.value = '';

    // Optimistic: show message immediately
    const container = document.getElementById('chatMessages');
    const emptyState = container.querySelector('.flex-center');
    if (emptyState) container.innerHTML = '';

    const tempMsg = {
        content: content,
        translated_content: '',
        is_read: false,
        created_at: new Date().toISOString(),
        sender_id: currentUser.id,
    };
    const tempEl = document.createElement('div');
    tempEl.innerHTML = renderMessage(tempMsg, true);
    tempEl.firstElementChild.style.opacity = '0.7';
    tempEl.firstElementChild.id = 'sending-msg';
    container.appendChild(tempEl.firstElementChild);
    container.scrollTop = container.scrollHeight;

    try {
        const result = await api.post('/api/messages/send', { receiver_id: chatUserId, content });
        // Replace temp msg with real data
        const sending = document.getElementById('sending-msg');
        if (sending) {
            sending.style.opacity = '1';
            sending.removeAttribute('id');
            // Update with translation if available
            if (result.translated_content && autoTranslate) {
                const realMsg = { ...result, is_read: false };
                sending.outerHTML = renderMessage(realMsg, true);
            }
        }
        lastMsgCount++;
    } catch (err) {
        // Remove temp message on failure
        const sending = document.getElementById('sending-msg');
        if (sending) sending.remove();
        showToast('傳送失敗', 'error');
        input.value = content; // restore message
    }
    isSending = false;
}

function toggleAutoTranslate() {
    autoTranslate = !autoTranslate;
    const btn = document.getElementById('translateToggle');
    if (btn) {
        btn.style.background = autoTranslate ? 'rgba(214, 181, 109, 0.15)' : '';
        btn.title = autoTranslate ? '翻譯已開啟' : '翻譯已關閉';
    }
    showToast(autoTranslate ? '已開啟自動翻譯' : '已關閉自動翻譯', 'success');
    loadMessages(true);
}

// Enter key to send
document.getElementById('messageInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});

// Auto refresh (every 3s for more responsive feel)
setInterval(loadMessages, 3000);

loadChatUser();
loadMessages(true);
