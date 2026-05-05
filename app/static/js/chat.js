// === Chat Page ===
requireAuth();

const currentUser = getUser();
let chatPartner = null;
let autoTranslate = false;
let lastRenderHash = '';        // skip re-render when nothing changed
let pendingMessages = [];       // optimistic msgs not yet confirmed by server
let pendingSeq = 0;             // increasing id for optimistic msgs
let pollPausedUntil = 0;        // timestamp; polling skipped while in this window
let isInitialLoad = true;       // first /chat fetch — different scroll behavior
let dividerBeforeMsgId = null;  // msg id to draw the "未讀訊息" divider above

async function loadChatUser() {
    try {
        const user = await api.get(`/api/users/${chatUserId}`);
        chatPartner = user;
        document.getElementById('chatName').textContent = user.display_name;
        document.getElementById('chatStatus').textContent = user.is_online ? '線上' : '離線';
        const avatar = document.getElementById('chatAvatar');
        if (user.avatar_url) avatar.src = user.avatar_url;
        else avatar.style.background = 'var(--gradient-gold)';
        // Tap avatar / name to open the partner's profile
        const goProfile = () => { window.location.href = `/profile/${encodeURIComponent(user.username)}`; };
        avatar.style.cursor = 'pointer';
        avatar.onclick = goProfile;
        const nameEl = document.getElementById('chatName');
        if (nameEl) {
            nameEl.style.cursor = 'pointer';
            nameEl.onclick = goProfile;
        }
    } catch (err) {
        showToast('無法載入用戶資料', 'error');
    }
}

function renderReceiptBelow(m, isSent) {
    if (!isSent) return '';
    if (m.is_pending) {
        return '<div class="msg-receipt msg-receipt-pending" title="傳送中">⏳ 傳送中…</div>';
    }
    if (m.is_read) {
        return '<div class="msg-receipt msg-receipt-read" title="對方已讀">已讀</div>';
    }
    return '<div class="msg-receipt msg-receipt-sent" title="已送達">已送達</div>';
}

function renderReplyQuote(reply) {
    if (!reply) return '';
    let preview;
    if (reply.is_deleted) {
        preview = '<i style="opacity:0.6">已收回的訊息</i>';
    } else if (reply.media_type === 'audio') {
        preview = '🎤 語音訊息';
    } else if (reply.media_type === 'video') {
        preview = '🎬 影片';
    } else if (reply.media_type === 'image') {
        preview = '📷 照片';
    } else {
        preview = escapeHtml(reply.content_preview || '');
    }
    return `<div class="msg-reply-quote" data-jump-to="${reply.id}">${preview}</div>`;
}

function renderMedia(m) {
    if (!m.media_url) return '';
    const safe = escapeHtml(m.media_url);
    if (m.media_type === 'audio') {
        return `<div class="msg-media-audio"><audio controls preload="metadata" src="${safe}"></audio></div>`;
    }
    if (m.media_type === 'video') {
        return `<video class="msg-media-video" controls preload="metadata" playsinline src="${safe}"></video>`;
    }
    if (m.media_type === 'image') {
        return `<img class="msg-media-image" src="${safe}" alt="" loading="lazy" decoding="async" onclick="openImageLightbox('${safe}')">`;
    }
    return '';
}

function renderMessage(m, isSent) {
    const ts = (m.created_at || '').endsWith('Z') ? m.created_at : (m.created_at || '') + 'Z';
    // Show server-cached translation when autoTranslate is on, OR a per-message
    // on-demand translation the user tapped 翻譯 on (cached client-side).
    const tappedTranslation = m.id ? _msgTranslateCache.get(m.id) : null;
    const autoTrText = (autoTranslate && m.translated_content && m.translated_content !== m.content)
        ? m.translated_content : null;
    const trText = tappedTranslation || autoTrText;
    const showTranslation = !m.is_deleted && !!trText;
    const tempAttr = m.is_pending ? ` data-pending-id="${m.pending_id}"` : '';
    const opacity = m.is_pending ? ' opacity:0.78;' : '';
    const receipt = renderReceiptBelow(m, isSent);

    let bodyHtml;
    if (m.is_deleted) {
        bodyHtml = '<div class="msg-deleted">↺ 已收回此訊息</div>';
    } else {
        const mediaHtml = renderMedia(m);
        const textHtml = m.content ? `<div class="msg-text">${escapeHtml(m.content)}</div>` : '';
        const trHtml = showTranslation ? `<div class="message-translated">🌐 ${escapeHtml(trText)}</div>` : '';
        bodyHtml = mediaHtml + textHtml + trHtml;
    }

    const idAttr = m.id ? ` data-msg-id="${m.id}"` : '';
    const onClick = (m.id && !m.is_pending && !m.is_deleted)
        ? `onclick="openMsgMenu(this, '${m.id}', ${isSent})"`
        : '';

    return `
        <div class="message-row ${isSent ? 'message-row-sent' : 'message-row-received'}"${tempAttr}${idAttr}>
            ${renderReplyQuote(m.reply_to)}
            <div class="message-bubble ${isSent ? 'message-sent' : 'message-received'} ${m.is_deleted ? 'message-deleted' : ''}" style="${opacity}" ${onClick}>
                ${bodyHtml}
                <div class="message-time" style="text-align:${isSent ? 'right' : 'left'};">
                    ${timeAgo(ts)}
                </div>
            </div>
            ${receipt}
        </div>
    `;
}

/* ---------- Action menu (reply / translate / recall) ---------- */
let activeMenuMsg = null;     // { id, isSent }
function openMsgMenu(bubbleEl, msgId, isSent) {
    activeMenuMsg = { id: msgId, isSent };
    const menu = document.getElementById('chatActionMenu');
    if (!menu) return;
    // Show only the actions that make sense
    document.getElementById('actionRecallBtn').style.display = isSent ? '' : 'none';
    // Position menu near the bubble
    const rect = bubbleEl.getBoundingClientRect();
    menu.classList.remove('hidden');
    // After making visible, measure
    const mw = menu.offsetWidth;
    const mh = menu.offsetHeight;
    let top = rect.top + window.scrollY - mh - 6;
    if (top < 8) top = rect.bottom + window.scrollY + 6;
    let left = rect.right + window.scrollX - mw;
    if (left < 8) left = 8;
    if (left + mw > window.innerWidth - 8) left = window.innerWidth - 8 - mw;
    menu.style.top = top + 'px';
    menu.style.left = left + 'px';
}
function closeMsgMenu() {
    activeMenuMsg = null;
    const menu = document.getElementById('chatActionMenu');
    if (menu) menu.classList.add('hidden');
}
document.addEventListener('click', (e) => {
    const menu = document.getElementById('chatActionMenu');
    if (!menu || menu.classList.contains('hidden')) return;
    if (menu.contains(e.target)) return;
    if (e.target.closest('.message-bubble')) return;
    closeMsgMenu();
});

/* ---------- Reply state ---------- */
let currentReplyTo = null;
function actionReply() {
    if (!activeMenuMsg) return closeMsgMenu();
    const row = document.querySelector(`[data-msg-id="${activeMenuMsg.id}"]`);
    if (!row) return closeMsgMenu();
    const senderName = activeMenuMsg.isSent
        ? '你自己'
        : (chatPartner ? chatPartner.display_name : '對方');
    const bubble = row.querySelector('.message-bubble');
    const previewText = bubble ? (bubble.querySelector('.msg-text')?.textContent
        || (row.querySelector('.msg-media-audio') ? '🎤 語音訊息' : '')
        || (row.querySelector('.msg-media-video') ? '🎬 影片' : '')
        || (row.querySelector('.msg-media-image') ? '📷 照片' : '')) : '';
    currentReplyTo = { id: activeMenuMsg.id, sender_name: senderName, content: previewText.slice(0, 80) };
    document.getElementById('chatReplyName').textContent = `回覆 ${senderName}`;
    document.getElementById('chatReplyPreview').textContent = currentReplyTo.content || '';
    document.getElementById('chatReplyBar').classList.remove('hidden');
    document.getElementById('messageInput').focus();
    closeMsgMenu();
}
function clearReply() {
    currentReplyTo = null;
    document.getElementById('chatReplyBar').classList.add('hidden');
}

// Per-message translation cache so re-tapping 翻譯 doesn't re-fetch.
const _msgTranslateCache = new Map();   // msgId → translated text

async function actionTranslate() {
    if (!activeMenuMsg) return closeMsgMenu();
    const id = activeMenuMsg.id;
    closeMsgMenu();

    const row = document.querySelector(`[data-msg-id="${id}"]`);
    if (!row) return;
    const bubble = row.querySelector('.message-bubble');
    if (!bubble) return;
    const textEl = bubble.querySelector('.msg-text');
    const sourceText = textEl ? textEl.textContent.trim() : '';
    if (!sourceText) {
        showToast('這則訊息沒有文字可翻譯', 'error');
        return;
    }

    // If we already have a translation rendered, toggle it off (and back on if tapped again).
    const existing = bubble.querySelector('.message-translated');
    if (existing) {
        existing.remove();
        return;
    }

    // Show a placeholder while we fetch
    const placeholder = document.createElement('div');
    placeholder.className = 'message-translated';
    placeholder.textContent = '🌐 翻譯中…';
    bubble.appendChild(placeholder);

    try {
        let translated = _msgTranslateCache.get(id);
        if (!translated) {
            const r = await api.post('/api/translate', { text: sourceText });
            translated = r.translated || sourceText;
            _msgTranslateCache.set(id, translated);
        }
        if (translated === sourceText) {
            placeholder.textContent = '🌐 (語言相同,無需翻譯)';
        } else {
            placeholder.textContent = '🌐 ' + translated;
        }
    } catch (err) {
        placeholder.textContent = '🌐 翻譯失敗,請稍後再試';
    }
}

// Optional: keep autoTranslate toggle on the chat header for users who want
// every message translated automatically. The per-bubble action above is the
// primary way to translate on demand.

async function actionRecall() {
    if (!activeMenuMsg) return closeMsgMenu();
    const id = activeMenuMsg.id;
    closeMsgMenu();
    if (!confirm('確定要收回這則訊息?')) return;
    try {
        await api.post(`/api/messages/${id}/recall`);
        // Mark as deleted in pending too just in case
        pendingMessages = pendingMessages.filter(p => p.id !== id);
        lastRenderHash = '';
        loadMessages();
    } catch (err) {
        showToast(err.message || '收回失敗', 'error');
    }
}

/* ---------- Image / video / voice send ---------- */
function openImageLightbox(url) {
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.95);z-index:3001;display:flex;align-items:center;justify-content:center;cursor:pointer;';
    overlay.innerHTML = `<img src="${url}" style="max-width:92vw;max-height:88vh;object-fit:contain;border-radius:12px;">`;
    overlay.onclick = () => overlay.remove();
    document.body.appendChild(overlay);
}

async function sendImageFile(input) {
    const file = input.files[0];
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) {
        showToast('圖片不能超過 20MB', 'error');
        input.value = '';
        return;
    }
    await sendMediaFile(file, 'image');
    input.value = '';
}

async function sendVideoFile(input) {
    const file = input.files[0];
    if (!file) return;
    if (file.size > 100 * 1024 * 1024) {
        showToast('影片不能超過 100MB', 'error');
        input.value = '';
        return;
    }
    // Soft check duration
    const url = URL.createObjectURL(file);
    const probe = document.createElement('video');
    probe.src = url;
    await new Promise(res => { probe.onloadedmetadata = res; probe.onerror = res; });
    URL.revokeObjectURL(url);
    if (probe.duration && probe.duration > 60.5) {
        showToast('影片不能超過 60 秒', 'error');
        input.value = '';
        return;
    }
    await sendMediaFile(file, 'video');
    input.value = '';
}

async function sendMediaFile(file, mediaType) {
    const replyId = currentReplyTo ? currentReplyTo.id : '';
    clearReply();
    const formData = new FormData();
    formData.append('receiver_id', chatUserId);
    formData.append('media_type', mediaType);
    formData.append('media', file, file.name || `chat_${mediaType}`);
    if (replyId) formData.append('reply_to_id', replyId);
    try {
        await api.post('/api/messages/send-media', formData, true);
        pollPausedUntil = Date.now() + 800;
        showToast('已送出', 'success');
        lastRenderHash = '';
        loadMessages(true);
    } catch (err) {
        showToast(err.message || '傳送失敗', 'error');
    }
}

/* ---------- Voice recording ---------- */
let recMediaRecorder = null;
let recChunks = [];
let recStartedAt = 0;
let recTimerId = null;
const REC_MAX_MS = 60_000;

async function startRecording() {
    if (!navigator.mediaDevices || !window.MediaRecorder) {
        return showToast('此瀏覽器不支援錄音', 'error');
    }
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        let mime = '';
        for (const t of ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/mpeg']) {
            if (MediaRecorder.isTypeSupported(t)) { mime = t; break; }
        }
        recMediaRecorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
        recChunks = [];
        recMediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) recChunks.push(e.data); };
        recMediaRecorder.onstop = async () => {
            stream.getTracks().forEach(t => t.stop());
            const send = recMediaRecorder._shouldSend;
            recMediaRecorder = null;
            if (recTimerId) { clearInterval(recTimerId); recTimerId = null; }
            document.getElementById('chatRecording').classList.add('hidden');
            document.getElementById('chatInputArea').classList.remove('hidden');
            if (!send || recChunks.length === 0) return;
            const blob = new Blob(recChunks, { type: 'audio/webm' });
            const ext = (blob.type.includes('webm')) ? 'webm' : (blob.type.includes('mp4') ? 'm4a' : 'audio');
            const file = new File([blob], `voice.${ext}`, { type: blob.type });
            await sendMediaFile(file, 'audio');
        };
        recMediaRecorder.start();
        recStartedAt = Date.now();
        document.getElementById('chatInputArea').classList.add('hidden');
        document.getElementById('chatRecording').classList.remove('hidden');
        recTimerId = setInterval(() => {
            const elapsed = Date.now() - recStartedAt;
            const sec = Math.floor(elapsed / 1000);
            document.getElementById('chatRecordingTime').textContent = `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
            if (elapsed >= REC_MAX_MS) stopRecording(true);
        }, 200);
    } catch (err) {
        showToast('無法存取麥克風,請允許錄音權限', 'error');
    }
}

function stopRecording(shouldSend) {
    if (!recMediaRecorder) return;
    recMediaRecorder._shouldSend = shouldSend;
    if (recMediaRecorder.state === 'recording') recMediaRecorder.stop();
}

function cancelRecording() { stopRecording(false); }

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
        const serverMessages = data.messages || [];
        const merged = buildMessagesList(serverMessages);

        // First-load only: place an "未讀訊息" divider above the oldest unread
        // received message. The server returns unread_count BEFORE marking the
        // messages as read, so we count back that many received messages.
        if (isInitialLoad && (data.unread_count || 0) > 0) {
            let receivedSeen = 0;
            for (let i = serverMessages.length - 1; i >= 0; i--) {
                const m = serverMessages[i];
                if (m.sender_id !== currentUser.id) {
                    receivedSeen++;
                    if (receivedSeen === data.unread_count) {
                        dividerBeforeMsgId = m.id;
                        break;
                    }
                }
            }
        }

        if (merged.length === 0) {
            container.innerHTML = '<div class="flex-center" style="flex:1;color:var(--text-muted)">開始你們的第一段對話 💌</div>';
            lastRenderHash = '';
            isInitialLoad = false;
            return;
        }

        // Hash check — avoid rebuilding identical DOM every 3s (causes flicker)
        const hash = merged.map(m => `${m.id || m.pending_id}:${m.is_read ? 1 : 0}:${(m.translated_content || '').length}`).join('|')
            + '|d:' + (dividerBeforeMsgId || '');
        const wasNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 80;
        if (hash === lastRenderHash && !scrollToBottom && !isInitialLoad) return;
        lastRenderHash = hash;

        container.innerHTML = merged.map(m => {
            const isSent = m.sender_id === currentUser.id;
            const dividerHtml = (m.id && m.id === dividerBeforeMsgId)
                ? '<div class="unread-divider"><span>未讀訊息</span></div>'
                : '';
            return dividerHtml + renderMessage(m, isSent);
        }).join('');

        // Scroll behavior:
        //   - First load with unread → land on the divider so the user sees
        //     where they left off (Telegram-style).
        //   - Otherwise, stay anchored at the bottom on initial load and on
        //     subsequent polls if the user was already near the bottom.
        if (isInitialLoad && dividerBeforeMsgId) {
            const divider = container.querySelector('.unread-divider');
            if (divider) {
                divider.scrollIntoView({ block: 'start' });
            } else {
                container.scrollTop = container.scrollHeight;
            }
        } else if (scrollToBottom || wasNearBottom) {
            container.scrollTop = container.scrollHeight;
        }

        isInitialLoad = false;
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

    // Snapshot the reply state and clear it so the next message isn't a reply.
    const replyId = currentReplyTo ? currentReplyTo.id : null;
    const replySnapshot = currentReplyTo ? { ...currentReplyTo } : null;
    clearReply();

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
        reply_to: replySnapshot ? {
            id: replySnapshot.id,
            sender_id: '',
            is_deleted: false,
            media_type: '',
            content_preview: replySnapshot.content || '',
        } : null,
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
    const body = { receiver_id: chatUserId, content };
    if (replyId) body.reply_to_id = replyId;
    api.post('/api/messages/send', body)
        .then((result) => {
            // Promote the optimistic row from "傳送中" to "已送達" in place;
            // the next poll will merge the canonical server row in.
            const row = container.querySelector(`[data-pending-id="${pendingId}"]`);
            if (row) {
                const bubble = row.querySelector('.message-bubble');
                if (bubble) bubble.style.opacity = '1';
                const receipt = row.querySelector('.msg-receipt');
                if (receipt) {
                    receipt.className = 'msg-receipt msg-receipt-sent';
                    receipt.textContent = '已送達';
                    receipt.title = '已送達';
                }
                row.removeAttribute('data-pending-id');
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
            const row = container.querySelector(`[data-pending-id="${pendingId}"]`);
            if (row) row.remove();
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

/* ---------- Desktop sidebar: list of all my conversations ----------
   Renders with the SAME HTML structure as /messages page (.conversation-item)
   so both pages look identical. */
let allSidebarConvs = [];
let convSidebarFilter = 'all';

async function loadConvSidebar() {
    const list = document.getElementById('chatConvList');
    if (!list) return;
    try {
        const data = await api.get('/api/messages/conversations');
        allSidebarConvs = data.conversations || [];
        renderConvSidebar(filteredSidebarConvs());
    } catch (e) {
        list.innerHTML = '<div class="text-muted text-center" style="padding:1.2rem; font-size:0.85rem;">載入失敗</div>';
    }
}

function filteredSidebarConvs() {
    const q = (document.getElementById('chatConvSearch') || { value: '' }).value.trim().toLowerCase();
    return allSidebarConvs.filter(c => {
        if (convSidebarFilter === 'unread' && !(c.unread_count > 0)) return false;
        if (q) {
            const name = (c.other_user.display_name || '').toLowerCase();
            const msg = (c.last_message || '').toLowerCase();
            if (!name.includes(q) && !msg.includes(q)) return false;
        }
        return true;
    });
}

function renderConvSidebar(convs) {
    const list = document.getElementById('chatConvList');
    if (!list) return;
    if (!convs.length) {
        list.innerHTML = '<div class="text-muted text-center" style="padding:1.2rem; font-size:0.85rem;">沒有符合的對話</div>';
        return;
    }
    list.innerHTML = convs.map(c => {
        const isActive = c.other_user.id === chatUserId || c.other_user.username === chatUserId;
        const profilePath = `/profile/${encodeURIComponent(c.other_user.username)}`;
        return `
            <div class="conversation-item ${isActive ? 'active' : ''}"
                 onclick="window.location.href='/chat/${c.other_user.id}'"
                 data-unread="${c.unread_count || 0}">
                <img src="${c.other_user.avatar_url || ''}" alt="" class="conversation-avatar" loading="lazy" decoding="async"
                     title="點擊查看個人頁"
                     onclick="event.stopPropagation(); window.location.href='${profilePath}'; return false;"
                     style="${c.other_user.avatar_url ? '' : 'background:var(--gradient-gold)'}; cursor:pointer;">
                <div class="conversation-info">
                    <div class="conversation-name">
                        ${escapeHtml(c.other_user.display_name)}
                        ${c.other_user.is_online ? '<span style="display:inline-block;width:8px;height:8px;background:var(--success);border-radius:50%;margin-left:4px;"></span>' : ''}
                    </div>
                    <div class="conversation-preview">${escapeHtml(c.last_message || '')}</div>
                </div>
                ${c.unread_count > 0 ? `<div class="conversation-unread">${c.unread_count}</div>` : ''}
            </div>
        `;
    }).join('');
}

function filterConvSidebar(type) {
    convSidebarFilter = type;
    document.querySelectorAll('[data-conv-filter]').forEach(el => {
        el.classList.toggle('active', el.dataset.convFilter === type);
    });
    renderConvSidebar(filteredSidebarConvs());
}

const _convSearch = document.getElementById('chatConvSearch');
if (_convSearch) {
    _convSearch.addEventListener('input', () => renderConvSidebar(filteredSidebarConvs()));
}

loadChatUser();
loadMessages(true);
loadConvSidebar();
