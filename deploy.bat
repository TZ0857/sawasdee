@echo off
echo ==========================================
echo   Sawasdee - Railway 部署腳本
echo ==========================================
echo.

:: 1. 檢查 Git
git --version >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 請先安裝 Git: https://git-scm.com/downloads
    pause
    exit /b
)

:: 2. 檢查 Railway CLI
railway version >nul 2>&1
if errorlevel 1 (
    echo [安裝] 正在安裝 Railway CLI...
    npm install -g @railway/cli
    if errorlevel 1 (
        echo [錯誤] 安裝失敗，請先安裝 Node.js: https://nodejs.org
        echo 或手動安裝: npm install -g @railway/cli
        pause
        exit /b
    )
)

:: 3. 登入 Railway
echo.
echo [步驟 1/4] 登入 Railway（會開啟瀏覽器）...
railway login

:: 4. 初始化專案
echo.
echo [步驟 2/4] 建立 Railway 專案...
railway init

:: 5. 加入 PostgreSQL
echo.
echo [步驟 3/4] 加入 PostgreSQL 資料庫...
echo 請在 Railway 控制台中手動加入 PostgreSQL：
echo   1. 到 https://railway.app/dashboard
echo   2. 點進你的專案
echo   3. 點「+ New」→「Database」→「PostgreSQL」
echo   4. PostgreSQL 建好後，DATABASE_URL 會自動注入
echo.
pause

:: 6. 設定環境變數
:: 重要：SECRET_KEY 只在還沒設定時才產生一次。
:: 之前每次部署都重設亂數，會讓所有使用者的 JWT token 失效（出現 Invalid token），
:: 現在改成只設定一次、之後永久沿用。
echo.
echo [步驟 3.5] 檢查 SECRET_KEY...
railway variables 2>nul | findstr /C:"SECRET_KEY" >nul
if errorlevel 1 (
    railway variables set SECRET_KEY=sawasdee-prod-%RANDOM%%RANDOM%%RANDOM%%RANDOM%
    echo [已產生新的 SECRET_KEY]
) else (
    echo [SECRET_KEY 已存在，沿用既有設定 - 不會讓現有使用者被登出]
)
echo.

:: 7. 部署
echo.
echo [步驟 4/4] 正在部署到 Railway...
railway up --detach

echo.
echo ==========================================
echo   部署完成！
echo   請到 Railway 控制台查看你的網站網址
echo   https://railway.app/dashboard
echo ==========================================
pause
