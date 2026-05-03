# Sawasdee — 台泰交友平台

## 專案概述
Sawasdee 是一個連結台灣與泰國會員的高品質交友平台，主打黑金奢華風格 UI、AI 即時翻譯、私密相簿、限時組局等功能。

## 技術架構
- **後端**: FastAPI + SQLAlchemy + PostgreSQL
- **前端**: Jinja2 模板 + vanilla JavaScript（無框架）
- **CSS**: 單一設計系統 `app/static/css/style.css`，使用 CSS custom properties
- **部署**: Railway（從 GitHub 自動部署）
- **GitHub**: https://github.com/TZ0857/sawasdee
- **線上網址**: https://awake-luck-production.up.railway.app

## 專案結構
```
sawasdee/
├── main.py                          # FastAPI 入口
├── app/
│   ├── models/                      # SQLAlchemy 資料模型
│   ├── routes/                      # API 路由
│   │   ├── auth.py                  # 登入/註冊/JWT
│   │   ├── users.py                 # 使用者 CRUD
│   │   ├── posts.py                 # 動態牆/留言/按讚/Stories
│   │   ├── messages.py              # 訊息/聊天/翻譯
│   │   ├── gatherings.py            # 組局功能
│   │   └── subscriptions.py         # Premium 訂閱
│   ├── templates/
│   │   ├── components/
│   │   │   ├── base.html            # 基礎模板（載入 CSS/JS）
│   │   │   └── navbar.html          # 導航列元件
│   │   └── pages/
│   │       ├── landing.html         # 首頁（未登入）
│   │       ├── login.html           # 登入
│   │       ├── register.html        # 註冊
│   │       ├── explore.html         # 探索會員
│   │       ├── feed.html            # 動態牆
│   │       ├── messages.html        # 訊息列表
│   │       ├── chat.html            # 聊天室（含 AI 翻譯）
│   │       ├── profile.html         # 個人檔案
│   │       ├── gatherings.html      # 組局（限時邀約）
│   │       ├── subscription.html    # Premium 方案
│   │       └── settings.html        # 設定頁
│   └── static/
│       ├── css/
│       │   └── style.css            # 全站設計系統（~990行）
│       └── js/
│           ├── api.js               # API 工具（fetch 封裝、JWT、timeAgo）
│           ├── feed.js              # 動態牆邏輯
│           ├── chat.js              # 聊天室 + WebSocket + 翻譯
│           ├── explore.js           # 探索頁篩選
│           ├── profile.js           # 個人檔案
│           ├── gatherings.js        # 組局功能
│           └── messages.js          # 訊息列表
├── requirements.txt
├── nixpacks.toml                    # Railway 部署設定
└── seed.py                          # 測試資料 seed
```

## 設計系統 — 黑金香檳風格
所有顏色透過 CSS variables 管理，定義在 `style.css` 的 `:root` 中：

### 核心色票
- `--gold: #C8A96A` — 主色（香檳金）
- `--gold-light: #E8C878` — 亮金（hover 狀態）
- `--gold-dark: #8F7442` — 深金（pressed 狀態）
- `--gradient-gold: linear-gradient(135deg, #C8A96A, #E8C878)` — 金色漸層
- `--bg-primary: #0a0a0a` — 主背景（近黑）
- `--bg-card: #111111` — 卡片背景
- `--bg-elevated: #1a1a1a` — 提升層背景
- `--text-primary: #F5F0E8` — 主文字（暖白）
- `--text-secondary: #B8B0A0` — 次要文字
- `--text-muted: #78716C` — 靜音文字

### 重要規則
- **絕對不要使用** 舊的金色 `#D6B56D` 或任何非系統定義的金色
- 所有元件必須使用 CSS variables，不要寫死色碼
- 按鈕 hover 用 `--gold-light`，active 用 `--gold-dark`
- 卡片圓角用 `--radius-lg` 或 `--radius-xl`

## 功能模組

### 1. 探索頁 (explore)
- 顯示所有會員（不分性別）
- 篩選：在線中、新會員
- 會員卡片：頭像、名稱、年齡、地點、興趣標籤

### 2. 動態牆 (feed)
- 發文 + 上傳圖片
- 分類篩選：日常、美食、旅行、夜生活、心情
- IG 風格展開式留言
- 按讚功能
- Stories 功能

### 3. 訊息/聊天 (messages + chat)
- 訊息列表 + 未讀數
- 即時聊天（WebSocket polling fallback）
- **AI 即時翻譯**：中↔泰↔英 自動翻譯
- 已讀回執

### 4. 組局 (gatherings)
- 限時邀約（倒數計時器）
- 類型：KTV、小酌、飯局、咖啡、戶外活動
- 加入/離開組局
- 地點 + 時間 + 人數上限

### 5. Premium 訂閱 (subscription)
- 月/季/年方案
- 功能：無限瀏覽、優先曝光、進階篩選、私密相簿

### 6. 設定 (settings)
- 帳號資料編輯
- 隱私設定（在線狀態、訊息權限）
- 通知設定
- 語言設定（繁中/泰文/英文）
- 封鎖名單

## 命名規範（繁體中文 UI 用語）
- 唱歌 → **KTV**
- 喝酒 → **小酌**
- 晚餐 → **飯局**
- 按讚 → **讚**
- 留言 → **留言**
- 發布 → **發布**

## 開發注意事項
1. **部署流程**: `git push origin main` → Railway 自動部署（約 1-2 分鐘）
2. **前端無框架**: 所有 JS 都是 vanilla，透過 `api.js` 的封裝函數與後端溝通
3. **JWT 認證**: token 存在 localStorage，`api.js` 自動帶入 header
4. **圖片上傳**: 用 FormData，`api.post(url, formData, true)` 第三參數 true 表示 multipart
5. **CSS 修改**: 只改 `style.css` 一個檔案，保持設計系統一致性
6. **模板繼承**: 所有頁面 extend `base.html`，navbar 用 `{% include %}`

## 近期完成的工作（供參考）
- ✅ 全站黑金香檳風格 UI 統一化（22 個檔案）
- ✅ 組局功能完整實作（前後端 + seed 資料）
- ✅ 動態牆分類篩選功能修復
- ✅ IG 風格展開式留言
- ✅ AI 即時翻譯功能修復
- ✅ 探索頁改為顯示所有會員
- ✅ 響應式行動裝置優化

## 待辦 / 可改進項目
- 組局頁加入地圖顯示
- 私密相簿前端實作
- 通知系統（目前只有 UI，無後端）
- 設定頁的隱私/通知 toggle 尚未接 API
- Stories 上傳功能（目前只有顯示）
- 搜尋功能強化
- 多語系 i18n 完整實作
