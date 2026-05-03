// === Chat Page ===
requireAuth();

const currentUser = getUser();
let chatPartner = null;
let autoTranslate = false;
let lastRenderHash = '';      // skip re-render when nothing changed
let pendingMessages = [];     // optimistic msgs not yet confirmed by server
let pendingSeq = 0;           // increasing id for optimistic msgs
let pollPausedUntil = 0;      // timestamp; polling skipped while in this window

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

function renderReadStatus(isSent, isRead, isPending) {
    if (!isSent) return '';
    if (isPending) {
        return ' <span class="msg-status msg-status-pending" title="傳送中">⏳</span>';
    }
    if (isRead) {
        return ' <span class="msg-status msg-status-read" title="已讀">✓✓ 已讀</span>';
    }
    return ' <span class="msg-status msg-status-sent" title="已送達">✓</span>';
}

function renderMessage(m, isSent) {
    const ts = (m.created_at || '').endsWith('Z') ? m.created_at : (m.created_at || '') + 'Z';
    const showTranslation = autoTranslate && m.translated_content && m.translated_content !== m.content;
    const readStatus = renderReadStatus(isSent, m.is_read, !!m.is_pending);
    const tempAttr = m.is_pending ? ` data-pending-id="${m.pending_id}"` : '';
    const opacity = m.is_pending ? ' opacity:0.78;' : '';
    return `
        <div class="message-bubble ${isSent ? 'message-sent' : 'message-received'}"${tempAttr} style="${opacity}">
            <div>${escapeHtml(m.content)}</div>
            ${showTranslation ? `<div class="message-translated">🌐 ${escapeHtml(m.translated_content)}</div>` : ''}
            <div class="message-time" style="text-align:${isSent ? 'right' : 'left'};">
                <span class="msg-time-text">${timeAgo(ts)}</span>${readStatus}
            </div>
        </div>
    `;
}

function escapeHtml(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function buildMessagesList(serverMessages) {
    // Filter out optimistic messages whose content+timing has been confirmed by the server
    const serverContents = new Set(
        serverMessages
            .filter(m => m.sender_id === currentUser.id)
            .map(m => `${m.content}|${m.created_at?.slice(0, 16)}`)
    );
    pendingMessages = pendingMessages.filter(p => {
        // Drop pending if server already echoed it back, or it's older than 30s (give up)
        const key = `${p.content}|${p.created_at?.slice(0, 16)}`;
        if (serverContents.has(key)) return false;
        if (Date.now() - p.created_at_ms > 30000) return false;
        return true;
    });
    return [...serverMessages, ...pendingMessages];
}

async function loadMessages(scrollToBottom = false) {
    // Skip polling while we're protecting an optimistic UI window
    if (Date.now() < pollPausedUntil && !scrollToBottom) return;

    try {
        const data = await api.get(`/api/messages/chat/${chatUserId}?page=1&per_page=50`);
        const container = document.getElementById('chatMessages');
        const merged = buildMessagesList(data.messages || []);

        if (merged.length === 0) {
            container.innerHTML = '<div class="flex-center" style="flex:1;color:var(--text-muted)">開始你們的第一段對話 💌</div>';
            lastRenderHash = '';
            return;
        }

        // Hash check — avoid rebuilding identical DOM every 3s (causes flicker)
        const hash = merged.map(m => `${m.id || m.pending_id}:${m.is_read ? 1 : 0}:${(m.translated_content || '').length}`).join('|');
        const wasNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 80;
        if (hash === lastRenderHash && !scrollToBottom) return;
        lastRenderHash = hash;

        container.innerHTML = merged.map(m => {
            const isSent = m.sender_id === currentUser.id;
            return renderMessage(m, isSent);
        }).join('');

        if (scrollToBottom || wasNearBottom) {
            container.scrollTop = container.scrollHeight;
        }
    } catch (err) {
        // Don't overwrite messages on transient refresh error
        const container = document.getElementById('chatMessages');
        if (container && !container.querySelector('.message-bubble')) {
            container.innerHTML = '<div class="flex-center" style="flex:1;color:var(--text-muted)">載入失敗</div>';
        }
    }
}

async function sendMessage() {
    const input = document.getElementById('messageInput');
    const content = input.value.trim();
    if (!content) return;

    // Clear input immediately so the user can keep typing the next message.
    input.value = '';
    input.focus();

    // Build optimistic message and append it right away.
    const pendingId = `pending-${++pendingSeq}-${Date.now()}`;
    const nowIso = new Date().toISOString();
    const optimistic = {
        pending_id: pendingId,
        is_pending: true,
        content,
        translated_content: '',
        is_read: false,
        created_at: nowIso,
        created_at_ms: Date.now(),
        sender_id: currentUser.id,
    };
    pendingMessages.push(optimistic);

    // Append the bubble manually so the user sees it instantly without
    // waiting for the next polling cycle.
    const container = document.getElementById('chatMessages');
    const emptyState = container.querySelector('.flex-center');
    if (emptyState) container.innerHTML = '';
    container.insertAdjacentHTML('beforeend', renderMessage(optimistic, true));
    container.scrollTop = container.scrollHeight;
    lastRenderHash = '';   // force the next poll to pick up the new state

    // Hold off the polling loop briefly so the optimistic bubble can't be wiped
    // by a poll that fires before the server has persisted the row.
    pollPausedUntil = Date.now() + 5000;

    // Fire-and-forget the network call. Failures roll back the optimistic UI.
    api.post('/api/messages/send', { receiver_id: chatUserId, content })
        .then((result) => {
            // Mark optimistic as confirmed — keep it visible until the next
            // poll merges in the canonical server row.
            const bubble = container.querySelector(`[data-pending-id="${pendingId}"]`);
            if (bubble) {
                bubble.style.opacity = '1';
                const status = bubble.querySelector('.msg-status');
                if (status) {
                    status.className = 'msg-status msg-status-sent';
                    status.textContent = '✓';
                    status.title = '已送達';
                }
                bubble.removeAttribute('data-pending-id');
            }
            // Update the corresponding pending entry so subsequent polls don't strip it prematurely
            const p = pendingMessages.find(x => x.pending_id === pendingId);
            if (p) {
                p.is_pending = false;
                p.id = result.id;
                p.created_at = result.created_at || p.created_at;
            }
            // Trigger a poll soon to pick up the canonical server data
            pollPausedUntil = Date.now() + 800;
        })
        .catch((err) => {
            const bubble = container.querySelector(`[data-pending-id="${pendingId}"]`);
            if (bubble) bubble.remove();
            pendingMessages = pendingMessages.filter(x => x.pending_id !== pendingId);
            showToast('傳送失敗,請再試一次', 'error');
            // Restore the user's text only if they haven't typed something else
            if (!input.value) input.value = content;
            pollPausedUntil = 0;
        });
}

function toggleAutoTranslate() {
    autoTranslate = !autoTranslate;
    const btn = document.getElementById('translateToggle');
    if (btn) {
        btn.style.background = autoTranslate ? 'rgba(200, 169, 106, 0.15)' : '';
        btn.title = autoTranslate ? '翻譯已開啟' : '翻譯已關閉';
    }
    showToast(autoTranslate ? '已開啟自動翻譯' : '已關閉自動翻譯', 'success');
    lastRenderHash = '';
    loadMessages(true);
}

// Enter key to send
document.getElementById('messageInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Auto refresh
setInterval(loadMessages, 3000);

loadChatUser();
loadMessages(true);
