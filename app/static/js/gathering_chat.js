// === Gathering Chat (group chat per gathering) ===
requireAuth();

const currentUser = getUser();
let lastRenderHash = '';
let pendingMessages = [];
let pendingSeq = 0;
let pollPausedUntil = 0;
let isInitialLoad = true;

const TYPE_EMOJI = { meal: '🍜', drinks: '🥂', karaoke: '🎤', movie: '🎬', nightlife: '🌙' };

function escapeHtml(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/* ---------- Load sidebar list of my chats ---------- */
async function loadMyChats() {
    try {
        const data = await api.get('/api/gatherings/my-chats');
        const list = document.getElementById('gChatList');
        const chats = data.chats || [];
        if (chats.length === 0) {
            list.innerHTML = '<div class="text-muted text-center" style="padding:1.5rem; font-size:0.85rem;">還沒有任何局,先去發起或申請加入</div>';
            return;
        }
        list.innerHTML = chats.map(c => {
            const emoji = TYPE_EMOJI[c.type] || '🎯';
            const isActive = c.id === gatheringId;
            const eventDate = c.event_at ? new Date(c.event_at + 'Z') : null;
            const timeLabel = eventDate
                ? `${eventDate.getMonth()+1}/${eventDate.getDate()} ${String(eventDate.getHours()).padStart(2,'0')}:${String(eventDate.getMinutes()).padStart(2,'0')}`
                : '';
            return `
                <a href="/gatherings/${c.id}/chat" class="g-chat-item ${isActive ? 'active' : ''}">
                    <div class="g-chat-item-emoji">${emoji}</div>
                    <div class="g-chat-item-body">
                        <div class="g-chat-item-title">${escapeHtml(c.title)}</div>
                        <div class="g-chat-item-meta">${timeLabel} · ${c.member_count} 人${c.is_host ? ' · 你是主揪' : ''}</div>
                    </div>
                </a>
            `;
        }).join('');
    } catch (err) {
        document.getElementById('gChatList').innerHTML = '<div class="text-muted" style="padding:1rem;">載入失敗</div>';
    }
}

/* ---------- Render messages ---------- */
function renderMessage(m, isMine) {
    const ts = m.created_at.endsWith('Z') ? m.created_at : m.created_at + 'Z';

    if (m.is_system) {
        return `<div class="g-msg-system">${escapeHtml(m.content)}<span class="g-msg-system-time">· ${timeAgo(ts)}</span></div>`;
    }

    const tempAttr = m.is_pending ? ` data-pending-id="${m.pending_id}"` : '';
    const opacity = m.is_pending ? ' opacity:0.78;' : '';
    const profilePath = m.sender && m.sender.username
        ? `/profile/${encodeURIComponent(m.sender.username)}`
        : '#';
    const senderInfo = isMine ? '' : `
        <div class="g-msg-sender">
            <a href="${profilePath}" title="查看 ${escapeHtml(m.sender.display_name)} 的個人頁" style="display:inline-flex; align-items:center; gap:0.3rem; color:inherit; text-decoration:none;">
                <img src="${escapeHtml(m.sender.avatar_url || '')}" alt="" class="g-msg-avatar"
                     style="${m.sender.avatar_url ? '' : 'background:var(--gradient-gold)'}">
                <span class="g-msg-name">${escapeHtml(m.sender.display_name)}</span>
            </a>
        </div>
    `;
    return `
        <div class="g-msg-row ${isMine ? 'g-msg-row-mine' : 'g-msg-row-other'}"${tempAttr}>
            ${senderInfo}
            <div class="g-msg-bubble ${isMine ? 'g-msg-bubble-mine' : 'g-msg-bubble-other'}" style="${opacity}">
                <div>${escapeHtml(m.content)}</div>
                <div class="g-msg-time">${timeAgo(ts)}</div>
            </div>
        </div>
    `;
}

function buildMergedList(serverMessages) {
    const seen = new Set(
        serverMessages
            .filter(m => !m.is_system && m.sender && m.sender.id === currentUser.id)
            .map(m => `${m.content}|${m.created_at?.slice(0, 16)}`)
    );
    pendingMessages = pendingMessages.filter(p => {
        const key = `${p.content}|${p.created_at?.slice(0, 16)}`;
        if (seen.has(key)) return false;
        if (Date.now() - p.created_at_ms > 30000) return false;
        return true;
    });
    return [...serverMessages, ...pendingMessages];
}

async function loadMessages(scrollToBottom = false) {
    if (Date.now() < pollPausedUntil && !scrollToBottom && !isInitialLoad) return;

    try {
        const data = await api.get(`/api/gatherings/${gatheringId}/messages?page=1&per_page=80`);
        const container = document.getElementById('gChatMessages');

        // Header info from response
        if (data.gathering) {
            const t = data.gathering;
            document.getElementById('gChatTitle').textContent = `${TYPE_EMOJI[t.type] || ''} ${t.title}`;
        }

        const merged = buildMergedList(data.messages || []);
        if (merged.length === 0) {
            container.innerHTML = '<div class="flex-center" style="flex:1;color:var(--text-muted);text-align:center;padding:2rem;">還沒有訊息<br>說個 hi 開場吧 👋</div>';
            lastRenderHash = '';
            isInitialLoad = false;
            return;
        }

        const wasNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 80;
        const hash = merged.map(m => `${m.id || m.pending_id}:${m.is_system ? 'S' : ''}`).join('|');
        if (hash === lastRenderHash && !scrollToBottom && !isInitialLoad) return;
        lastRenderHash = hash;

        container.innerHTML = merged.map(m => {
            const senderId = m.sender ? m.sender.id : null;
            const isMine = !m.is_system && senderId === currentUser.id;
            return renderMessage(m, isMine);
        }).join('');

        if (isInitialLoad || scrollToBottom || wasNearBottom) {
            container.scrollTop = container.scrollHeight;
        }
        isInitialLoad = false;
    } catch (err) {
        const m = (err && err.message) || '';
        if (m.includes('關閉') || m.includes('已開始')) {
            // 410: gathering has started, chat room closed
            document.getElementById('gChatMessages').innerHTML = `
                <div class="text-center" style="padding:2.5rem 1rem; color:var(--text-muted);">
                    <div style="font-size:2rem; margin-bottom:0.5rem;">🌙</div>
                    <div style="color:var(--text-primary); font-weight:600; margin-bottom:0.4rem;">局已開始,聊天室已關閉</div>
                    <div style="font-size:0.85rem; line-height:1.6;">時間到了之後,所有訊息都自動刪除了。<br>祝你們玩得開心!</div>
                    <a href="/gatherings" class="btn btn-primary btn-sm" style="margin-top:1.2rem;">回到組局</a>
                </div>
            `;
            document.getElementById('gChatTitle').textContent = '聊天室已關閉';
            // Also stop the polling loop
            if (window._chatPollIntervalId) clearInterval(window._chatPollIntervalId);
            // Hide the input area
            const inputArea = document.querySelector('.g-chat-input-area');
            if (inputArea) inputArea.style.display = 'none';
        } else if (m.includes('成員')) {
            // 403: not a member
            document.getElementById('gChatMessages').innerHTML =
                '<div class="text-center text-muted" style="padding:2rem;">你不是這個局的成員,無法進入聊天室</div>';
            document.getElementById('gChatTitle').textContent = '無權進入';
        } else {
            const c = document.getElementById('gChatMessages');
            if (c && !c.querySelector('.g-msg-row')) {
                c.innerHTML = '<div class="text-center text-muted" style="padding:2rem;">載入失敗</div>';
            }
        }
        isInitialLoad = false;
    }
}

async function sendMessage() {
    const input = document.getElementById('gChatInput');
    const content = input.value.trim();
    if (!content) return;

    input.value = '';
    input.focus();

    const pendingId = `pending-${++pendingSeq}-${Date.now()}`;
    const nowIso = new Date().toISOString();
    const optimistic = {
        pending_id: pendingId,
        is_pending: true,
        is_system: false,
        content,
        sender: { id: currentUser.id, display_name: currentUser.display_name || '你', avatar_url: currentUser.avatar_url || '' },
        created_at: nowIso,
        created_at_ms: Date.now(),
    };
    pendingMessages.push(optimistic);

    const container = document.getElementById('gChatMessages');
    if (container.querySelector('.flex-center')) container.innerHTML = '';
    container.insertAdjacentHTML('beforeend', renderMessage(optimistic, true));
    container.scrollTop = container.scrollHeight;
    lastRenderHash = '';
    pollPausedUntil = Date.now() + 4000;

    api.post(`/api/gatherings/${gatheringId}/messages`, { content })
        .then(() => {
            const row = container.querySelector(`[data-pending-id="${pendingId}"]`);
            if (row) {
                row.style.opacity = '1';
                row.removeAttribute('data-pending-id');
            }
            const p = pendingMessages.find(x => x.pending_id === pendingId);
            if (p) p.is_pending = false;
            pollPausedUntil = Date.now() + 600;
        })
        .catch((err) => {
            const row = container.querySelector(`[data-pending-id="${pendingId}"]`);
            if (row) row.remove();
            pendingMessages = pendingMessages.filter(x => x.pending_id !== pendingId);
            showToast(err.message || '傳送失敗', 'error');
            if (!input.value) input.value = content;
            pollPausedUntil = 0;
        });
}

// Enter to send
document.getElementById('gChatInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Auto-poll (kept on window so we can clear it when the chat is closed)
window._chatPollIntervalId = setInterval(loadMessages, 3000);

/* ---------- Members panel: list + kick (host only) ---------- */
let membersPanelOpen = false;
let cachedIsHost = false;

async function loadMembers() {
    try {
        const data = await api.get(`/api/gatherings/${gatheringId}/members`);
        cachedIsHost = !!data.is_host;
        const members = data.members || [];
        document.getElementById('gMemberCount').textContent = members.length;
        document.getElementById('gMembersList').innerHTML = members.map(m => {
            const profilePath = `/profile/${encodeURIComponent(m.username)}`;
            const isMe = m.id === currentUser.id;
            const kickBtn = (cachedIsHost && !m.is_host && !isMe)
                ? `<button class="g-member-kick" onclick="kickMember('${m.id}', '${escapeHtml(m.display_name)}'); event.stopPropagation();" title="移出">移出</button>`
                : '';
            const hostBadge = m.is_host ? '<span class="g-member-host-badge">主揪</span>' : '';
            return `
                <a href="${profilePath}" class="g-member-row" title="查看 ${escapeHtml(m.display_name)} 的個人頁">
                    <img src="${escapeHtml(m.avatar_url || '')}" alt="" class="g-member-avatar"
                         onerror="this.style.background='var(--gradient-gold)'; this.removeAttribute('src');">
                    <div class="g-member-name">
                        ${escapeHtml(m.display_name)}${isMe ? ' (你)' : ''}
                        ${hostBadge}
                    </div>
                    ${kickBtn}
                </a>
            `;
        }).join('');
    } catch (err) {
        document.getElementById('gMembersList').innerHTML =
            '<div class="text-muted" style="padding:1rem;">無法載入成員</div>';
    }
}

function toggleMembersPanel() {
    const panel = document.getElementById('gMembersPanel');
    if (!panel) return;
    membersPanelOpen = !membersPanelOpen;
    panel.classList.toggle('hidden', !membersPanelOpen);
    if (membersPanelOpen) loadMembers();
}

async function kickMember(userId, displayName) {
    if (!confirm(`確定把「${displayName}」移出局?`)) return;
    try {
        await api.post(`/api/gatherings/${gatheringId}/kick/${userId}`);
        showToast(`已將 ${displayName} 移出`, 'success');
        loadMembers();
        lastRenderHash = '';
        loadMessages(true);   // refresh to show the system "X 已被移出局" message
    } catch (err) {
        showToast(err.message || '移出失敗', 'error');
    }
}

loadMyChats();
loadMessages(true);
