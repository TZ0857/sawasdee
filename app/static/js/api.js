// === Sawasdee API Client & Utilities ===

const api = {
    getToken() { return localStorage.getItem('token'); },

    async request(method, url, body = null, isForm = false) {
        const headers = {};
        const token = this.getToken();
        if (token) headers['Authorization'] = `Bearer ${token}`;
        if (body && !isForm) headers['Content-Type'] = 'application/json';

        const opts = { method, headers };
        if (body) opts.body = isForm ? body : JSON.stringify(body);

        const res = await fetch(url, opts);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Request failed');
        return data;
    },

    get(url) { return this.request('GET', url); },
    post(url, body, isForm = false) { return this.request('POST', url, body, isForm); },
    put(url, body) { return this.request('PUT', url, body); },
    delete(url) { return this.request('DELETE', url); },
};

function requireAuth() {
    if (!localStorage.getItem('token')) {
        window.location.href = '/login';
        return false;
    }
    return true;
}

function getUser() {
    try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; }
}

function showToast(msg, type = 'success') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function timeAgo(dateStr) {
    const now = new Date();
    // Ensure UTC interpretation if no timezone specified
    const ts = dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : dateStr + 'Z';
    const date = new Date(ts);
    const diff = Math.floor((now - date) / 1000);
    if (diff < 0) return '剛剛';
    if (diff < 60) return '剛剛';
    if (diff < 3600) return `${Math.floor(diff / 60)} 分鐘前`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} 小時前`;
    if (diff < 604800) return `${Math.floor(diff / 86400)} 天前`;
    return date.toLocaleDateString('zh-TW');
}

function avatarFallback(name) {
    return name ? name.charAt(0).toUpperCase() : 'S';
}

function goToProfile() {
    const user = getUser();
    if (user.username) window.location.href = `/profile/${user.username}`;
}

function goToSettings() {
    window.location.href = '/settings';
}

function toggleAvatarMenu() {
    const dd = document.getElementById('avatarDropdown');
    if (dd) dd.classList.toggle('hidden');
}

function doLogout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/login';
}

// Init navbar avatar
document.addEventListener('DOMContentLoaded', () => {
    const user = getUser();
    const navAvatar = document.getElementById('navAvatar');
    if (navAvatar && user.avatar_url) {
        navAvatar.src = user.avatar_url;
    } else if (navAvatar) {
        navAvatar.style.display = 'none';
    }

    // Highlight active nav link
    const path = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(link => {
        const page = link.dataset.page;
        if (page && path.startsWith('/' + page)) link.classList.add('active');
    });

    // Hide "升級 Premium" CTA when the user is already a Premium member
    if (user && user.is_subscribed) {
        document.querySelectorAll('.nav-premium-btn').forEach(el => {
            el.style.display = 'none';
        });
    }

    // Close avatar dropdown when clicking outside
    document.addEventListener('click', (e) => {
        const wrap = document.getElementById('navAvatarWrap');
        const dd = document.getElementById('avatarDropdown');
        if (dd && wrap && !wrap.contains(e.target)) {
            dd.classList.add('hidden');
        }
    });
});
