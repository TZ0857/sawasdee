// === Gathering Chat (group chat per gathering) ===
requireAuth();

const currentUser = getUser();
let lastRenderHash = '';
let pendingMessages = [];
let pendingSeq = 0;
let pollPausedUntil = 0;
let isInitialLoad = true;

// Viewer's display language → translations target this.
const _MY_LANG = (currentUser.nationality === 'thai') ? 'TH'
               : (currentUser.nationality === 'taiwanese') ? 'ZH'
               : 'EN';

// Per-gathering auto-translate preference, persisted in localStorage.
const _AUTO_KEY = `sw_autotr_g:${gatheringId}`;
let autoTranslate = localStorage.getItem(_AUTO_KEY) === '1';
let _lastMessageList = [];   // cached for auto-translate sweep on toggle

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

/* ---------- Per-message translation cache (client side) ---------- */
const _gMsgTranslateCache = new Map();   // msgId → translated text

// Show 🌐 button on a gathering chat message?
//   - skip system messages, my own messages, pending optimistic messages
//   - skip if no text or English source (we don't have an EN nationality)
//   - only when message language differs from MY language
function _gNeedsTranslate(m, isMine) {
    if (m.is_system || isMine) return false;
    if (m.is_pending) return false;
    if (!m.content) return false;
    if (!m.source_lang || m.source_lang === 'EN') return false;
    return m.source_lang !== _MY_LANG;
}

async function gTranslateMsg(msgId, btnEl) {
    if (btnEl) btnEl.disabled = true;
    const bubble = btnEl ? btnEl.closest('.g-msg-bubble')
                         : document.querySelector(`.g-msg-row [data-msg-id="${msgId}"] .g-msg-bubble`);
    if (!bubble) { if (btnEl) btnEl.disabled = false; return; }
    const textEl = bubble.querySelector('.g-msg-text');
    const sourceText = textEl ? textEl.textContent.trim() : '';
    if (!sourceText) {
        showToast('沒有文字可翻譯', 'error');
        if (btnEl) btnEl.disabled = false;
        return;
    }
    const existing = bubble.querySelector('.g-msg-translated');
    if (existing) {
        existing.remove();
        if (btnEl) { btnEl.disabled = false; btnEl.style.display = ''; }
        return;
    }
    const placeholder = document.createElement('div');
    placeholder.className = 'g-msg-translated';
    placeholder.textContent = '🌐 翻譯中…';
    bubble.insertBefore(placeholder, bubble.querySelector('.g-msg-foot') || bubble.querySelector('.g-msg-time'));
    try {
        let translated = _gMsgTranslateCache.get(msgId);
        let failed = false;
        if (!translated) {
            const r = await api.post('/api/translate', {
                text: sourceText,
                message_id: msgId,
                message_type: 'gathering',
            });
            failed = !!r.failed;
            translated = r.translated || sourceText;
            if (!failed && translated !== sourceText) {
                _gMsgTranslateCache.set(msgId, translated);
            }
        }
        if (failed) {
            placeholder.textContent = '🌐 翻譯服務暫時不可用,請稍後再點一次';
            return;
        }
        placeholder.textContent = translated === sourceText
            ? '🌐 (與你的語言相同,無需翻譯)'
            : '🌐 ' + translated;
        if (btnEl) btnEl.style.display = 'none';
    } catch (err) {
        placeholder.textContent = '🌐 翻譯失敗,請稍後再試';
    } finally {
        if (btnEl) btnEl.disabled = false;
    }
}

// Pre-fetch all needed translations in parallel BEFORE the next render.
// Eliminates the CLS jumps that came from inserting translations one by
// one into already-rendered bubbles. 2.5s ceiling keeps the chat snappy.
async function _gEnsureTranslationsLoaded(messages) {
    if (!autoTranslate) return;
    const todo = [];
    for (const m of messages) {
        if (!m.id || _gMsgTranslateCache.has(m.id)) continue;
        const isMine = !m.is_system && m.sender && m.sender.id === currentUser.id;
        if (!_gNeedsTranslate(m, isMine)) continue;
        todo.push(
            api.post('/api/translate', {
                text: m.content,
                message_id: m.id,
                message_type: 'gathering',
            }).then(r => {
                if (r && !r.failed && r.needed && r.translated && r.translated !== m.content) {
                    _gMsgTranslateCache.set(m.id, r.translated);
                }
            }).catch(() => {})
        );
    }
    if (!todo.length) return;
    await Promise.race([
        Promise.all(todo),
        new Promise(r => setTimeout(r, 2500)),
    ]);
}

function toggleGatheringAutoTranslate() {
    autoTranslate = !autoTranslate;
    localStorage.setItem(_AUTO_KEY, autoTranslate ? '1' : '0');
    const btn = document.getElementById('gAutoTrToggle');
    if (btn) {
        btn.style.background = autoTranslate ? 'rgba(196,86,111,0.15)' : '';
        btn.title = autoTranslate ? '自動翻譯已開啟' : '自動翻譯已關閉';
    }
    if (window.showToast) showToast(autoTranslate ? '已開啟自動翻譯' : '已關閉自動翻譯', 'success');
    if (!autoTranslate) {
        _gMsgTranslateCache.clear();
        lastRenderHash = '';
        loadMessages(true);
    } else {
        // Force a re-render through the new pre-fetch path
        lastRenderHash = '';
        loadMessages(true);
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
                <img src="${escapeHtml(m.sender.avatar_url || '')}" alt="" class="g-msg-avatar" loading="lazy" decoding="async"
                     style="${m.sender.avatar_url ? '' : 'background:var(--gradient-gold)'}">
                <span class="g-msg-name">${escapeHtml(m.sender.display_name)}</span>
            </a>
        </div>
    `;
    // Reuse cached translation across re-renders (poll every 3s wipes the DOM)
    const cached = m.id ? _gMsgTranslateCache.get(m.id) : null;
    const translatedHtml = cached
        ? `<div class="g-msg-translated">🌐 ${escapeHtml(cached)}</div>`
        : '';
    // 🌐 button only when message is in a foreign language relative to me
    // (and not my own / pending / system / English)
    const showTrBtn = _gNeedsTranslate(m, isMine) && !cached;
    const translateBtn = showTrBtn
        ? `<button class="g-msg-translate-btn" type="button" onclick="gTranslateMsg('${m.id}', this)" title="翻譯這則訊息">🌐</button>`
        : '';
    const idAttr = m.id ? ` data-msg-id="${m.id}"` : '';
    return `
        <div class="g-msg-row ${isMine ? 'g-msg-row-mine' : 'g-msg-row-other'}"${tempAttr}${idAttr}>
            ${senderInfo}
            <div class="g-msg-bubble ${isMine ? 'g-msg-bubble-mine' : 'g-msg-bubble-other'}" style="${opacity}">
                <div class="g-msg-text">${escapeHtml(m.content)}</div>
                ${translatedHtml}
                <div class="g-msg-foot">
                    <span class="g-msg-time">${timeAgo(ts)}</span>
                    ${translateBtn}
                </div>
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
        const hash = merged.map(m => `${m.id || m.pending_id}:${m.is_system ? 'S' : ''}`).join('|')
            + '|trc:' + _gMsgTranslateCache.size;
        if (hash === lastRenderHash && !scrollToBottom && !isInitialLoad) return;
        lastRenderHash = hash;

        // CLS-fix: pre-fetch all needed translations BEFORE rendering so
        // bubbles ship with the right height — no jumping.
        if (autoTranslate) {
            await _gEnsureTranslationsLoaded(merged);
        }

        container.innerHTML = merged.map(m => {
            const senderId = m.sender ? m.sender.id : null;
            const isMine = !m.is_system && senderId === currentUser.id;
            return renderMessage(m, isMine);
        }).join('');

        // Cache the latest list so the auto-translate toggle can sweep on demand
        _lastMessageList = merged;

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
                    <img src="${escapeHtml(m.avatar_url || '')}" alt="" class="g-member-avatar" loading="lazy" decoding="async"
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

// Reflect persisted auto-translate state on toggle button at load time
(function _initAutoTrToggle() {
    const btn = document.getElementById('gAutoTrToggle');
    if (!btn) return;
    btn.style.background = autoTranslate ? 'rgba(196,86,111,0.15)' : '';
    btn.title = autoTranslate ? '自動翻譯已開啟' : '自動翻譯已關閉';
})();

loadMyChats();
loadMessages(true);
