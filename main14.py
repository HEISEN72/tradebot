import os
from dotenv import load_dotenv
import asyncio
import json
import logging
import sys
from datetime import datetime

import aiohttp
import aiosqlite
from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
                    stream=sys.stdout)
logger = logging.getLogger(__name__)

# ==========================================
# 1. КОНФИГУРАЦИЯ
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN")

if not BOT_TOKEN:
    raise ValueError("Токен бота не найден! Проверьте файл .env")
if not WEBAPP_URL:
    raise ValueError("Ссылка на Web App не найдена! Проверьте файл .env")

WEB_SERVER_PORT = 8080
DB_NAME = "tradebot.db"

dp = Dispatcher()

API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
HTTP_HEADERS = {"X-Frame-Options": "ALLOWALL", "Access-Control-Allow-Origin": "*",
                "Content-Security-Policy": "frame-ancestors *"}


# ==========================================
# 2. ИНИЦИАЛИЗАЦИЯ БД
# ==========================================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0,
                in_bots REAL DEFAULT 0,
                profit REAL DEFAULT 0,
                lang TEXT DEFAULT 'en',
                bots_data TEXT DEFAULT '[]'
            )
        """)
        await db.execute(
            "CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, text TEXT, date TEXT)")
        await db.commit()


# ==========================================
# 3. PREMIUM FRONTEND (HTML_CONTENT)
# ==========================================
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>TradeBot Premium</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest"></script>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>

    <style>
        :root {
            --bg-deep: #0B0C10;
            --bg-card: #14151C;
            --bg-nav: rgba(20, 21, 28, 0.85);
            --accent: #4F46E5;
            --accent-light: #6366F1;
            --text-main: #FFFFFF;
            --text-muted: #8E9BAE;
            --success: #10B981;
            --danger: #EF4444;
            --border: rgba(255, 255, 255, 0.06);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
        body { 
            font-family: 'Inter', sans-serif; 
            background-color: var(--bg-deep); 
            color: var(--text-main); 
            padding: 20px 16px 100px 16px;
            user-select: none; -webkit-user-select: none;
            overflow-x: hidden;
        }

        h1 { font-size: 24px; font-weight: 700; margin-bottom: 20px; letter-spacing: -0.5px; }

        /* Анимации */
        .tab-content { display: none; animation: fadeIn 0.4s ease; }
        .tab-content.active { display: block; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

        /* Карточки */
        .premium-card {
            background-color: var(--bg-card);
            border-radius: 24px;
            padding: 20px;
            border: 1px solid var(--border);
            margin-bottom: 16px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        }

        /* Баланс */
        .balance-label { color: var(--text-muted); font-size: 13px; font-weight: 500; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }
        .balance-amount { font-size: 36px; font-weight: 700; margin-bottom: 16px; letter-spacing: -1px; }
        .stats-row { display: flex; justify-content: space-between; padding-top: 16px; border-top: 1px solid var(--border); }
        .stat-item { display: flex; flex-direction: column; gap: 4px; }
        .stat-val { font-weight: 600; font-size: 15px; }
        .stat-lbl { color: var(--text-muted); font-size: 12px; }

        /* Кнопки */
        .btn-group { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 24px; }
        .btn {
            display: flex; align-items: center; justify-content: center; gap: 8px;
            padding: 16px; border-radius: 18px; border: none; font-size: 15px; font-weight: 600;
            cursor: pointer; transition: all 0.2s; color: white; outline: none;
        }
        .btn-main { background: linear-gradient(135deg, var(--accent), var(--accent-light)); }
        .btn-sec { background-color: rgba(255, 255, 255, 0.05); border: 1px solid var(--border); }
        .btn:active { transform: scale(0.96); opacity: 0.9; }

        /* Список монет и ботов */
        .list-title { font-size: 18px; font-weight: 600; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
        .item-card {
            display: flex; justify-content: space-between; align-items: center;
            background: var(--bg-card); padding: 16px; border-radius: 20px;
            margin-bottom: 10px; border: 1px solid var(--border); transition: 0.2s;
        }
        .item-card:active { border-color: var(--accent); background: rgba(79, 70, 229, 0.05); }

        /* Навигация */
        .bottom-nav {
            position: fixed; bottom: 0; left: 0; right: 0;
            background: var(--bg-nav); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
            display: flex; justify-content: space-around; padding: 12px 10px 28px 10px;
            border-top: 1px solid var(--border); z-index: 1000;
        }
        .nav-item { display: flex; flex-direction: column; align-items: center; color: var(--text-muted); font-size: 11px; font-weight: 500; gap: 4px; cursor: pointer; }
        .nav-item.active { color: var(--accent-light); }
        .nav-item svg { width: 22px; height: 22px; }

        /* Модальные окна */
        .modal-overlay {
            display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.7); z-index: 2000; align-items: flex-end;
        }
        .modal-overlay.active { display: flex; animation: fadeInOverlay 0.3s forwards; }
        .modal-content {
            background: var(--bg-card); width: 100%; max-height: 85vh;
            border-radius: 32px 32px 0 0; padding: 32px 20px; overflow-y: auto;
            border-top: 1px solid var(--border); transform: translateY(100%);
            transition: transform 0.3s cubic-bezier(0.32, 0.72, 0, 1);
        }
        .modal-overlay.active .modal-content { transform: translateY(0); }
        @keyframes fadeInOverlay { from { opacity: 0; } to { opacity: 1; } }

        /* Ввод и Chips */
        .input-box {
            background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border);
            border-radius: 16px; padding: 16px; width: 100%; color: white;
            font-size: 18px; font-weight: 600; outline: none; margin-bottom: 12px;
        }
        .input-box:focus { border-color: var(--accent); }
        .chip-row { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 5px; scrollbar-width: none; }
        .chip-row::-webkit-scrollbar { display: none; }
        .chip { 
            background: rgba(255, 255, 255, 0.05); border: 1px solid var(--border);
            padding: 10px 16px; border-radius: 14px; font-size: 13px; font-weight: 600; white-space: nowrap;
            transition: 0.2s; cursor: pointer;
        }
        .chip.active { background: var(--accent); border-color: var(--accent); }

        /* ИСПРАВЛЕНИЕ: Кнопка назад без выделения */
        .back-btn { 
            background: none; border: none; color: var(--text-muted); font-size: 16px; 
            margin-bottom: 15px; cursor: pointer; display: flex; align-items: center; gap: 5px; 
            outline: none; -webkit-tap-highlight-color: transparent;
        }
        .back-btn:active { color: var(--text-main); }

        /* ИСПРАВЛЕНИЕ: Жесткие размеры графика против сплющивания */
        .tv-container { 
            border-radius: 20px; overflow: hidden; border: 1px solid var(--border); 
            margin-bottom: 20px; background: #000; 
            height: 380px; min-height: 380px; flex-shrink: 0; 
            display: block; width: 100%;
        }
        #market-list-view, #chart-setup-view, #bot-detail-view { width: 100%; }
        .tf-chip { padding: 6px 12px; font-size: 12px; border-radius: 10px; }

        /* Профиль */
        .profile-header { display: flex; align-items: center; margin-bottom: 25px; }
        .profile-avatar { 
            width: 60px; height: 60px; min-width: 60px; 
            border-radius: 50%; background: linear-gradient(135deg, var(--accent), var(--accent-light)); 
            display: flex; align-items: center; justify-content: center; 
            font-size: 24px; font-weight: bold; margin-right: 15px; flex-shrink: 0;
        }

        /* ИСПРАВЛЕНИЕ: Выравнивание иконок меню в профиле */
        .menu-list { overflow: hidden; }
        .menu-item { 
            display: flex; align-items: center; padding: 18px 20px; 
            border-bottom: 1px solid var(--border); cursor: pointer; transition: background 0.2s;
        }
        .menu-item:active { background: rgba(255, 255, 255, 0.03); }
        .menu-item:last-child { border-bottom: none; }

        /* Жесткая защита от сжатия вектора (SVG) */
        .menu-item svg { 
            width: 22px; height: 22px; min-width: 22px; flex-shrink: 0; 
            margin-right: 14px; color: var(--accent-light); 
        }
    </style>
</head>
<body>

    <div id="tab-dashboard" class="tab-content active">
        <h1 data-i18n="dash_title">Dashboard</h1>

        <div class="premium-card">
            <div class="balance-label"><i data-lucide="wallet"></i> <span data-i18n="avail_bal">Available Balance</span></div>
            <div class="balance-amount" id="balanceDisplay">$0.00</div>

            <div class="stats-row">
                <div class="stat-item">
                    <span class="stat-val" id="inBotsDisplay">$0.00</span>
                    <span class="stat-lbl" data-i18n="in_bots">In Trading</span>
                </div>
                <div class="stat-item" style="text-align: right;">
                    <span class="stat-val" id="profitDisplay" style="color: var(--success);">$0.00</span>
                    <span class="stat-lbl" data-i18n="total_profit">Profit 24h</span>
                </div>
            </div>
        </div>

        <div class="btn-group">
            <button class="btn btn-main" onclick="handleDepositClick()">
                <i data-lucide="plus-circle"></i> <span data-i18n="btn_deposit">Deposit</span>
            </button>
            <button class="btn btn-sec" onclick="tg.showAlert(dict[currentLang].withdraw_lock)">
                <i data-lucide="arrow-up-right"></i> <span data-i18n="btn_withdraw">Withdraw</span>
            </button>
        </div>

        <div class="list-title"><i data-lucide="bot"></i> <span data-i18n="active_bots">Active Bots</span></div>
        <div id="activeBotsContainer" data-i18n="no_bots">Loading...</div>
    </div>

    <div id="tab-trade" class="tab-content">
        <div id="market-list-view">
            <h1>Markets</h1>
            <input type="text" id="searchInput" class="input-box" style="font-size: 15px;" placeholder="Search symbol..." onkeyup="filterCoins()">
            <div class="coin-list" id="coinListContainer"></div>
        </div>

        <div id="chart-setup-view">
            <button class="back-btn" onclick="closeSetupView()"><i data-lucide="chevron-left"></i> Back</button>
            <h2 id="setupCoinTitle" style="margin-bottom: 12px;">BTC/USDT</h2>

            <div class="chip-row" id="tf-setup" style="margin-bottom: 12px;">
                <div class="chip tf-chip" data-tf="1" onclick="changeTimeframe('1', this, 'setup')">1m</div>
                <div class="chip tf-chip" data-tf="5" onclick="changeTimeframe('5', this, 'setup')">5m</div>
                <div class="chip tf-chip active" data-tf="15" onclick="changeTimeframe('15', this, 'setup')">15m</div>
                <div class="chip tf-chip" data-tf="60" onclick="changeTimeframe('60', this, 'setup')">1h</div>
                <div class="chip tf-chip" data-tf="240" onclick="changeTimeframe('240', this, 'setup')">4h</div>
                <div class="chip tf-chip" data-tf="D" onclick="changeTimeframe('D', this, 'setup')">1d</div>
            </div>

            <div id="setup_chart_container" class="tv-container"></div>

            <div class="premium-card">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px;">
                    <div><span class="stat-lbl" data-i18n="lower_price">Lower Price</span><input type="number" id="gridLower" class="input-box" oninput="updateSetupGridLines()"></div>
                    <div><span class="stat-lbl" data-i18n="upper_price">Upper Price</span><input type="number" id="gridUpper" class="input-box" oninput="updateSetupGridLines()"></div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px;">
                    <div><span class="stat-lbl" data-i18n="grids_count">Grids</span><input type="number" id="gridCount" class="input-box" value="10" oninput="updateSetupGridLines()"></div>
                    <div><span class="stat-lbl" data-i18n="invest">Investment</span><input type="number" id="gridInvest" class="input-box" placeholder="Min 10"></div>
                </div>
                <button class="btn btn-main" style="width: 100%;" onclick="launchGridBot()">
                    <i data-lucide="rocket"></i> <span data-i18n="btn_launch">Launch Bot</span>
                </button>
            </div>
        </div>

        <div id="bot-detail-view">
            <button class="back-btn" onclick="closeBotDetail()"><i data-lucide="chevron-left"></i> Back</button>
            <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 12px;">
                <h2 id="detailBotTitle">BTC/USDT</h2>
                <div id="detailBotProfit" style="font-size: 20px; font-weight: 700;">$0.00</div>
            </div>

            <div class="chip-row" id="tf-detail" style="margin-bottom: 12px;">
                <div class="chip tf-chip" data-tf="1" onclick="changeTimeframe('1', this, 'detail')">1m</div>
                <div class="chip tf-chip" data-tf="5" onclick="changeTimeframe('5', this, 'detail')">5m</div>
                <div class="chip tf-chip active" data-tf="15" onclick="changeTimeframe('15', this, 'detail')">15m</div>
                <div class="chip tf-chip" data-tf="60" onclick="changeTimeframe('60', this, 'detail')">1h</div>
                <div class="chip tf-chip" data-tf="240" onclick="changeTimeframe('240', this, 'detail')">4h</div>
                <div class="chip tf-chip" data-tf="D" onclick="changeTimeframe('D', this, 'detail')">1d</div>
            </div>

            <div id="detail_chart_container" class="tv-container"></div>

            <div class="premium-card">
                <div style="display: flex; justify-content: space-between; margin-bottom: 20px;">
                    <span class="stat-lbl" data-i18n="total_trades">Total Trades</span>
                    <span id="detailBotTradesCount" style="font-weight: 600;">0</span>
                </div>
                <button class="btn btn-sec" style="width: 100%; color: var(--danger); border-color: rgba(239, 68, 68, 0.2);" onclick="stopCurrentBot()">
                    <i data-lucide="stop-circle"></i> <span data-i18n="btn_stop">Stop & Withdraw</span>
                </button>
            </div>
        </div>
    </div>

    <div id="tab-calculator" class="tab-content">
        <h1 data-i18n="calc_title">Profit Calculator</h1>
        <div class="premium-card">
            <span class="stat-lbl" data-i18n="invest" style="margin-bottom: 10px; display: block;">Investment Amount</span>
            <input type="number" id="calcAmount" class="input-box" value="100" oninput="calculateProfit()">
            <div class="chip-row" style="margin-bottom: 20px;">
                <div class="chip" onclick="addAmount(10)">+10</div>
                <div class="chip" onclick="addAmount(100)">+100</div>
                <div class="chip" onclick="addAmount(1000)">+1K</div>
            </div>

            <span class="stat-lbl" data-i18n="period" style="margin-bottom: 10px; display: block;">Staking Period</span>
            <div class="chip-row" id="periodButtons" style="margin-bottom: 20px;">
                <div class="chip" onclick="setPeriod(7, this)">7 Days</div>
                <div class="chip active" onclick="setPeriod(30, this)">30 Days</div>
                <div class="chip" onclick="setPeriod(365, this)">1 Year</div>
            </div>

            <div class="stats-row" style="margin-top: 10px; border: none; background: rgba(255,255,255,0.03); padding: 20px; border-radius: 16px;">
                <div class="stat-item">
                    <span class="stat-lbl" data-i18n="final_amt">Estimation</span>
                    <span class="stat-val" id="calcFinal" style="font-size: 20px;">$0.00</span>
                </div>
                <div class="stat-item" style="text-align: right;">
                    <span class="stat-lbl" data-i18n="profit">Net Profit</span>
                    <span class="stat-val" id="calcProfitPercent" style="color: var(--success); font-size: 20px;">+0%</span>
                </div>
            </div>
        </div>
    </div>

    <div id="tab-profile" class="tab-content">
        <div class="profile-header">
            <div class="profile-avatar" id="profileAvatar">U</div>
            <div>
                <h2 id="profileName" style="font-size: 20px;">User</h2>
                <p id="profileId" style="color: var(--text-muted); font-size: 13px;">ID: 000000</p>
            </div>
        </div>

        <div class="premium-card" style="display: flex; justify-content: space-between; align-items: center;">
            <div class="stat-item">
                <span class="stat-lbl" data-i18n="plan">Current Plan</span>
                <span class="stat-val">PREMIUM</span>
            </div>
            <div class="stat-item" style="text-align: right;">
                <span class="stat-lbl" data-i18n="total_earned">Total Earned</span>
                <span class="stat-val" id="profileTotalEarned" style="color: var(--success);">$0.00</span>
            </div>
        </div>

        <div class="menu-list premium-card" style="padding: 0;">
            <div class="menu-item" onclick="openModal('langModal')">
                <i data-lucide="globe"></i> 
                <span data-i18n="menu_lang">Language</span>
            </div>
            <div class="menu-item" onclick="tg.openTelegramLink('https://t.me/' + SUPPORT_USERNAME)">
                <i data-lucide="help-circle"></i> 
                <span data-i18n="menu_support">Support</span>
            </div>
            <div class="menu-item" onclick="openModal('faqModal')">
                <i data-lucide="info"></i> 
                <span>FAQ</span>
            </div>
            <div class="menu-item" onclick="openModal('reviewsModal')">
                <i data-lucide="message-square"></i> 
                <span data-i18n="menu_reviews">Reviews</span>
            </div>
        </div>
    </div>

    <nav class="bottom-nav">
        <div class="nav-item active" onclick="switchTab('dashboard', this)"><i data-lucide="layout-dashboard"></i><span data-i18n="nav_dash">Dashboard</span></div>
        <div class="nav-item" onclick="switchTab('trade', this)"><i data-lucide="line-chart"></i><span data-i18n="nav_trade">Trade</span></div>
        <div class="nav-item" onclick="switchTab('calculator', this)"><i data-lucide="calculator"></i><span data-i18n="nav_calc">Calc</span></div>
        <div class="nav-item" onclick="switchTab('profile', this)"><i data-lucide="user"></i><span data-i18n="nav_prof">Profile</span></div>
    </nav>

    <div id="langModal" class="modal-overlay" onclick="closeModal(event, 'langModal')">
        <div class="modal-content">
            <h2 style="margin-bottom: 20px;">Select Language</h2>
            <div class="menu-list" style="background: none; border: none;">
                <div class="item-card" onclick="setLanguage('en'); closeModalForce('langModal')">🇬🇧 English</div>
                <div class="item-card" onclick="setLanguage('ru'); closeModalForce('langModal')">🇷🇺 Русский</div>
            </div>
        </div>
    </div>

    <div id="faqModal" class="modal-overlay" onclick="closeModal(event, 'faqModal')">
        <div class="modal-content">
            <h2 style="margin-bottom: 20px;">FAQ</h2>
            <div id="faqText" style="color: var(--text-muted); line-height: 1.6; font-size: 14px;"></div>
        </div>
    </div>

    <div id="reviewsModal" class="modal-overlay" onclick="closeModal(event, 'reviewsModal')">
        <div class="modal-content">
            <h2 style="margin-bottom: 20px;">Community Reviews</h2>
            <textarea id="reviewInput" class="input-box" style="height: 100px; font-size: 14px;" placeholder="Share your experience..."></textarea>
            <button class="btn btn-main" style="width: 100%; margin-bottom: 20px;" onclick="submitReview()">Send Review</button>
            <div id="reviewsListContainer"></div>
        </div>
    </div>

    <script>
    const SUPPORT_USERNAME = "trabe72bot"; 
    const tg = window.Telegram.WebApp;
    tg.expand(); tg.ready();
    lucide.createIcons();

    const userInfo = tg.initDataUnsafe?.user || { id: 111111, first_name: "Demo", username: "User" };
    document.getElementById('profileName').innerText = userInfo.first_name || userInfo.username;
    document.getElementById('profileId').innerText = 'ID: ' + userInfo.id;
    document.getElementById('profileAvatar').innerText = (userInfo.first_name || userInfo.username).charAt(0).toUpperCase();

    let currentLang = 'en';
    let currentTf = '15'; // Таймфрейм по умолчанию

    const dict = {
        'en': {
            dash_title: "Wallet", avail_bal: "Available Balance", in_bots: "In Trading", total_profit: "Profit 24h",
            btn_deposit: "Deposit", btn_withdraw: "Withdraw", active_bots: "Active AI Bots", no_bots: "No bots running. Start trading to see stats.",
            config_grid: "Strategy Setup", lower_price: "Min Price", upper_price: "Max Price", grids_count: "Grid Levels",
            invest: "Investment", btn_launch: "Start AI Trading", total_trades: "Total Executed", btn_stop: "Close Strategy",
            calc_title: "Profit Forecast", period: "Period", btn_calc: "Estimate", final_amt: "Potential Balance", profit: "Net Profit",
            plan: "Account Status", total_earned: "Total Profit", menu_lang: "Language", menu_support: "Support Center", menu_reviews: "User Feed",
            nav_dash: "Main", nav_trade: "Trade", nav_calc: "Forecast", nav_prof: "Settings", withdraw_lock: "Demo account: Withdrawals disabled.",
            faq_text: "<b>AI Trading Guide</b><br><br>1. Deposit funds to your demo account.<br>2. Select a market pair in the Trade tab.<br>3. Set your price range (corridor).<br>4. Launch the bot. It will execute buy/sell orders automatically within your range."
        },
        'ru': {
            dash_title: "Кошелек", avail_bal: "Доступный баланс", in_bots: "В торговле", total_profit: "Профит 24ч",
            btn_deposit: "Пополнить", btn_withdraw: "Вывести", active_bots: "Активные боты", no_bots: "Нет запущенных ботов. Начните торговать!",
            config_grid: "Настройка стратегии", lower_price: "Мин. цена", upper_price: "Макс. цена", grids_count: "Линии сетки",
            invest: "Инвестиция", btn_launch: "Запустить AI бота", total_trades: "Всего сделок", btn_stop: "Закрыть стратегию",
            calc_title: "Прогноз прибыли", period: "Период", btn_calc: "Рассчитать", final_amt: "Ожидаемый баланс", profit: "Чистая прибыль",
            plan: "Статус аккаунта", total_earned: "Общая прибыль", menu_lang: "Язык интерфейса", menu_support: "Центр поддержки", menu_reviews: "Отзывы",
            nav_dash: "Главная", nav_trade: "Торговля", nav_calc: "Прогноз", nav_prof: "Профиль", withdraw_lock: "Демо-счет: Вывод средств заблокирован.",
            faq_text: "<b>Инструкция по AI-трейдингу</b><br><br>1. Пополните демо-баланс.<br>2. Выберите торговую пару во вкладке 'Торговля'.<br>3. Укажите ценовой коридор (Мин/Макс цены).<br>4. Запустите бота. Он будет автоматически покупать и продавать внутри сетки."
        }
    };

    function setLanguage(lang) {
        currentLang = lang;
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            if(dict[lang][key]) el.innerHTML = dict[lang][key];
        });
        document.getElementById('faqText').innerHTML = dict[lang].faq_text;
        queueSaveState();
    }

    let availableBalance = 0; let inBotsBalance = 0; let totalBotProfit = 0;
    let activeBots = []; let coinsData = []; let currentSymbol = ''; let currentSetupPrice = 0;
    let setupChart = null; let setupCandleSeries = null; let setupGridLines = [];
    let detailChart = null; let detailCandleSeries = null; let detailGridLines = []; let activeDetailBotId = null;

    async function loadStateFromDB() {
        try {
            const res = await fetch(`/api/user?id=${userInfo.id}`);
            const data = await res.json();
            availableBalance = data.balance || 0;
            inBotsBalance = data.in_bots || 0;
            totalBotProfit = data.profit || 0;
            currentLang = data.lang || 'en';
            try { activeBots = JSON.parse(data.bots_data || '[]'); } catch(e) { activeBots = []; }
            activeBots.forEach(bot => startBotSimulation(bot));
            setLanguage(currentLang);
            updateFinancesUI();
            renderActiveBots();
        } catch (e) { console.error(e); }
    }

    async function saveStateToDB() {
        const safeBots = activeBots.map(b => ({ ...b, interval: null }));
        const payload = { user_id: userInfo.id, balance: availableBalance, in_bots: inBotsBalance, profit: totalBotProfit, lang: currentLang, bots_data: JSON.stringify(safeBots) };
        try { await fetch('/api/user', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) }); } catch (e) {}
    }

    let saveTimeout;
    function queueSaveState() { clearTimeout(saveTimeout); saveTimeout = setTimeout(saveStateToDB, 2000); }

    window.updateFinancesUI = function() {
        document.getElementById('balanceDisplay').innerText = '$' + availableBalance.toLocaleString('en-US', {minimumFractionDigits: 2});
        document.getElementById('inBotsDisplay').innerText = '$' + inBotsBalance.toLocaleString('en-US', {minimumFractionDigits: 2});
        document.getElementById('profitDisplay').innerText = '$' + totalBotProfit.toLocaleString('en-US', {minimumFractionDigits: 2});
        document.getElementById('profileTotalEarned').innerText = '$' + totalBotProfit.toLocaleString('en-US', {minimumFractionDigits: 2});
        queueSaveState();
    };

    window.switchTab = function(tabName, clickedBtn) {
        document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
        document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));
        document.getElementById('tab-' + tabName).classList.add('active');
        if(clickedBtn) clickedBtn.classList.add('active');

        if (tabName === 'trade') {
            if (coinsData.length === 0) window.fetchLiveMarketData();
            document.getElementById('market-list-view').style.display = 'block';
            document.getElementById('chart-setup-view').style.display = 'none';
            document.getElementById('bot-detail-view').style.display = 'none';
            activeDetailBotId = null;
        }
        if(tabName === 'calculator') window.calculateProfit();
    };

    window.fetchLiveMarketData = async function() {
        try {
            const response = await fetch('/api/24hr');
            const json = await response.json();
            const data = json.result.list;
            coinsData = data.filter(c => c.symbol.endsWith('USDT')).sort((a, b) => parseFloat(b.turnover24h) - parseFloat(a.turnover24h)).slice(0, 40);
            window.renderCoins(coinsData);
        } catch (error) {}
    };

    window.renderCoins = function(coins) {
        const container = document.getElementById('coinListContainer');
        container.innerHTML = '';
        coins.forEach(coin => {
            const price = parseFloat(coin.lastPrice);
            const change = parseFloat(coin.price24hPcnt) * 100;
            const color = change >= 0 ? 'var(--success)' : 'var(--danger)';
            const item = document.createElement('div');
            item.className = 'item-card';
            item.onclick = () => window.openSetupView(coin.symbol, price);
            item.innerHTML = `
                <div><div style="font-weight: 700;">${coin.symbol.replace('USDT', '')}/USDT</div><div style="font-size: 11px; color: var(--text-muted);">Bybit Spot</div></div>
                <div style="text-align: right;"><div style="font-weight: 700;">$${price.toLocaleString()}</div><div style="color: ${color}; font-size: 12px; font-weight: 600;">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</div></div>
            `;
            container.appendChild(item);
        });
    };

    window.filterCoins = function() {
        const query = document.getElementById('searchInput').value.toUpperCase();
        window.renderCoins(coinsData.filter(c => c.symbol.includes(query)));
    };

    function createLightweightChart(containerId) {
        const container = document.getElementById(containerId);
        container.innerHTML = '';
        const chart = LightweightCharts.createChart(container, {
            autoSize: true,
            layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#8b8d9c' },
            grid: { vertLines: { color: 'rgba(255,255,255,0.05)' }, horzLines: { color: 'rgba(255,255,255,0.05)' } },
            timeScale: { timeVisible: true, borderVisible: false },
            rightPriceScale: { autoScale: true, borderVisible: false }
        });
        const candleSeries = chart.addCandlestickSeries({ upColor: '#10B981', downColor: '#EF4444', borderVisible: false, wickUpColor: '#10B981', wickDownColor: '#EF4444' });
        return { chart, candleSeries };
    }

    async function fetchKlinesForChart(symbol, series, chartInstance, containerId) {
        try {
            const res = await fetch(`/api/klines?symbol=${symbol}&limit=100&interval=${currentTf}`);
            const json = await res.json();
            const data = json.result.list;
            let formattedData = data.map(d => ({ time: Math.floor(parseInt(d[0]) / 1000), open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4]) })).sort((a, b) => a.time - b.time);
            formattedData = formattedData.filter((item, index, arr) => index === 0 || item.time > arr[index - 1].time);
            series.setData(formattedData);
            chartInstance.timeScale().fitContent();
        } catch (e) {}
    }

    window.changeTimeframe = async function(tf, btn, viewType) {
        currentTf = tf;
        document.querySelectorAll(`#tf-${viewType} .chip`).forEach(c => c.classList.remove('active'));
        btn.classList.add('active');

        if (viewType === 'setup') {
            if(setupCandleSeries && setupChart) {
                await fetchKlinesForChart(currentSymbol, setupCandleSeries, setupChart, 'setup_chart_container');
                window.updateSetupGridLines();
            }
        } else {
            if(detailCandleSeries && detailChart && activeDetailBotId) {
                const bot = activeBots.find(b => b.id === activeDetailBotId);
                if(bot) {
                    detailGridLines.forEach(line => detailCandleSeries.removePriceLine(line));
                    detailGridLines = [];
                    await fetchKlinesForChart(bot.symbol, detailCandleSeries, detailChart, 'detail_chart_container');
                    const step = (bot.upper - bot.lower) / (bot.count - 1);
                    for (let i = 0; i < bot.count; i++) {
                        const price = bot.lower + (i * step);
                        const lineColor = price > bot.initialPrice ? 'rgba(239, 68, 68, 0.4)' : 'rgba(16, 185, 129, 0.4)';
                        const line = detailCandleSeries.createPriceLine({ price: price, color: lineColor, lineWidth: 1, lineStyle: 2 });
                        detailGridLines.push(line);
                    }
                    if (bot.markers.length > 0) detailCandleSeries.setMarkers(bot.markers);
                }
            }
        }
    };

    window.openSetupView = async function(symbol, price) {
        currentSymbol = symbol; currentSetupPrice = price;
        document.getElementById('market-list-view').style.display = 'none';
        document.getElementById('chart-setup-view').style.display = 'block';
        document.getElementById('setupCoinTitle').innerText = `${symbol.replace('USDT', '')}/USDT`;
        document.getElementById('gridLower').value = (price * 0.95).toFixed(price > 1 ? 2 : 5);
        document.getElementById('gridUpper').value = (price * 1.05).toFixed(price > 1 ? 2 : 5);

        document.querySelectorAll('#tf-setup .chip').forEach(c => c.classList.remove('active'));
        document.querySelector('#tf-setup .chip[data-tf="15"]').classList.add('active');
        currentTf = '15';

        setTimeout(async () => {
            const chartData = createLightweightChart('setup_chart_container');
            setupChart = chartData.chart; setupCandleSeries = chartData.candleSeries;
            await fetchKlinesForChart(symbol, setupCandleSeries, setupChart, 'setup_chart_container');
            window.updateSetupGridLines();
        }, 100); 
    };

    window.updateSetupGridLines = function() {
        if (!setupCandleSeries) return;
        setupGridLines.forEach(line => setupCandleSeries.removePriceLine(line));
        setupGridLines = [];
        const lower = parseFloat(document.getElementById('gridLower').value);
        const upper = parseFloat(document.getElementById('gridUpper').value);
        const count = parseInt(document.getElementById('gridCount').value);
        if (lower && upper && count >= 2 && lower < upper) {
            const step = (upper - lower) / (count - 1);
            for (let i = 0; i < count; i++) {
                const price = lower + (i * step);
                const lineColor = price > currentSetupPrice ? 'rgba(239, 68, 68, 0.4)' : 'rgba(16, 185, 129, 0.4)';
                setupGridLines.push(setupCandleSeries.createPriceLine({ price: price, color: lineColor, lineWidth: 1, lineStyle: 2 }));
            }
        }
    };

    window.closeSetupView = function() { document.getElementById('market-list-view').style.display = 'block'; document.getElementById('chart-setup-view').style.display = 'none'; };

    window.launchGridBot = function() {
        const lower = parseFloat(document.getElementById('gridLower').value), upper = parseFloat(document.getElementById('gridUpper').value), invest = parseFloat(document.getElementById('gridInvest').value), grids = parseInt(document.getElementById('gridCount').value);
        if (!invest || invest < 10) return tg.showAlert("Min 10 USDT");
        if (invest > availableBalance) return tg.showAlert("Low Balance");
        if (!lower || !upper || lower >= upper) return tg.showAlert("Check Range");
        availableBalance -= invest; inBotsBalance += invest; window.updateFinancesUI();
        const newBot = { id: Date.now(), symbol: currentSymbol, invest: invest, lower: lower, upper: upper, count: grids, profit: 0, trades: 0, status: 'Running', initialPrice: currentSetupPrice, currentPrice: currentSetupPrice, markers: [] };
        activeBots.push(newBot); startBotSimulation(newBot); tg.showAlert("Bot Started!");
        window.switchTab('dashboard', document.querySelectorAll('.nav-item')[0]); window.renderActiveBots();
    };

    window.renderActiveBots = function() {
        const container = document.getElementById('activeBotsContainer');
        if (activeBots.length === 0) { container.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--text-muted);">${dict[currentLang].no_bots}</div>`; return; }
        container.innerHTML = '';
        activeBots.forEach(bot => {
            const color = bot.profit >= 0 ? 'var(--success)' : 'var(--danger)';
            container.innerHTML += `
                <div class="item-card" onclick="window.openBotDetail(${bot.id})">
                    <div><div style="font-weight: 700;">${bot.symbol.replace('USDT', '')}/USDT</div><div style="font-size: 11px; color: var(--text-muted);">$${bot.invest} invested</div></div>
                    <div style="text-align: right;"><div style="color: ${color}; font-weight: 700;">${bot.profit >= 0 ? '+' : ''}$${bot.profit.toFixed(4)}</div><div style="font-size: 11px; color: var(--text-muted);">Tap to View</div></div>
                </div>`;
        });
    };

    function startBotSimulation(bot) {
        bot.interval = setInterval(async () => {
            try {
                const response = await fetch(`/api/price?symbol=${bot.symbol}`);
                const json = await response.json();
                if(json.retCode !== 0) return;
                const livePrice = parseFloat(json.result.list[0].lastPrice);
                const oldPrice = bot.currentPrice; bot.currentPrice = livePrice;
                const step = (bot.upper - bot.lower) / (bot.count - 1);
                for (let i = 0; i < bot.count; i++) {
                    const linePrice = bot.lower + (i * step);
                    if (oldPrice > linePrice && bot.currentPrice <= linePrice) registerTrade(bot, 'buy', linePrice);
                    else if (oldPrice < linePrice && bot.currentPrice >= linePrice) registerTrade(bot, 'sell', linePrice);
                }
                if (activeDetailBotId === bot.id && detailCandleSeries) {
                    const klineRes = await fetch(`/api/klines?symbol=${bot.symbol}&limit=1&interval=${currentTf}`);
                    const klineJson = await klineRes.json();
                    if (klineJson.retCode === 0) {
                        const d = klineJson.result.list[0];
                        detailCandleSeries.update({ time: Math.floor(parseInt(d[0]) / 1000), open: parseFloat(d[1]), high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4]) });
                    }
                }
            } catch (e) {}
        }, 3000);
    }

    function registerTrade(bot, type, price) {
        bot.trades++;
        const profitFromTrade = (bot.invest / bot.count) * 0.001;
        bot.profit += profitFromTrade; totalBotProfit += profitFromTrade;
        window.updateFinancesUI();
        bot.markers.push({ time: Math.floor(Date.now() / 1000), position: type === 'buy' ? 'belowBar' : 'aboveBar', color: type === 'buy' ? '#10B981' : '#EF4444', shape: type === 'buy' ? 'arrowUp' : 'arrowDown', text: type.toUpperCase() });
        if (activeDetailBotId === bot.id && detailCandleSeries) { detailCandleSeries.setMarkers(bot.markers); window.updateBotDetailUI(bot); }
        window.renderActiveBots(); queueSaveState();
    }

    window.openBotDetail = async function(botId) {
        const bot = activeBots.find(b => b.id === botId);
        if (!bot) return;
        activeDetailBotId = botId;
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
        document.getElementById('tab-trade').classList.add('active');
        document.getElementById('market-list-view').style.display = 'none';
        document.getElementById('chart-setup-view').style.display = 'none';
        document.getElementById('bot-detail-view').style.display = 'block';
        window.updateBotDetailUI(bot);

        document.querySelectorAll('#tf-detail .chip').forEach(c => c.classList.remove('active'));
        document.querySelector('#tf-detail .chip[data-tf="15"]').classList.add('active');
        currentTf = '15';

        setTimeout(async () => {
            const chartData = createLightweightChart('detail_chart_container');
            detailChart = chartData.chart; detailCandleSeries = chartData.candleSeries;
            await fetchKlinesForChart(bot.symbol, detailCandleSeries, detailChart, 'detail_chart_container');

            detailGridLines = [];
            const step = (bot.upper - bot.lower) / (bot.count - 1);
            for (let i = 0; i < bot.count; i++) {
                const price = bot.lower + (i * step);
                const lineColor = price > bot.initialPrice ? 'rgba(239, 68, 68, 0.3)' : 'rgba(16, 185, 129, 0.3)';
                const line = detailCandleSeries.createPriceLine({ price: price, color: lineColor, lineWidth: 1, lineStyle: 2 });
                detailGridLines.push(line);
            }
            if (bot.markers.length > 0) detailCandleSeries.setMarkers(bot.markers);
        }, 100);
    };

    window.updateBotDetailUI = function(bot) {
        document.getElementById('detailBotTitle').innerText = `${bot.symbol.replace('USDT', '')}/USDT`;
        document.getElementById('detailBotProfit').innerText = (bot.profit >= 0 ? '+' : '') + '$' + bot.profit.toFixed(4);
        document.getElementById('detailBotProfit').style.color = bot.profit >= 0 ? 'var(--success)' : 'var(--danger)';
        document.getElementById('detailBotTradesCount').innerText = bot.trades;
    };

    window.closeBotDetail = function() { activeDetailBotId = null; document.getElementById('bot-detail-view').style.display = 'none'; window.switchTab('dashboard', document.querySelectorAll('.nav-item')[0]); };

    window.stopCurrentBot = function() {
        tg.showConfirm("Are you sure?", function(conf) {
            if (conf) {
                const idx = activeBots.findIndex(b => b.id === activeDetailBotId);
                if (idx > -1) {
                    const bot = activeBots[idx]; clearInterval(bot.interval);
                    inBotsBalance -= bot.invest; availableBalance += (bot.invest + bot.profit);
                    activeBots.splice(idx, 1); window.updateFinancesUI(); window.renderActiveBots();
                    tg.showAlert("Bot Closed!"); window.closeBotDetail();
                }
            }
        });
    };

    window.handleDepositClick = function() {
        const amt = prompt("Deposit amount (USDT):", "50");
        if (!amt || isNaN(amt) || amt <= 0) return;
        fetch(`/api/invoice?user_id=${userInfo.id}&amount=${amt}`).then(r => r.json()).then(data => {
            if(data.url) tg.openTelegramLink(data.url);
            else { availableBalance += parseFloat(amt); window.updateFinancesUI(); }
        });
    };

    window.openModal = function(id) { document.getElementById(id).classList.add('active'); if(id === 'reviewsModal') loadReviews(); };
    window.closeModal = function(e, id) { if(e.target.id === id) document.getElementById(id).classList.remove('active'); };
    window.closeModalForce = function(id) { document.getElementById(id).classList.remove('active'); };

    async function loadReviews() {
        const cont = document.getElementById('reviewsListContainer');
        try {
            const res = await fetch('/api/reviews');
            const revs = await res.json();
            cont.innerHTML = revs.length ? '' : '<div style="color: var(--text-muted); text-align: center;">No reviews yet.</div>';
            revs.forEach(r => { cont.innerHTML += `<div class="premium-card" style="padding: 16px; margin-bottom: 12px;"><div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); margin-bottom: 6px;"><span>${r.name}</span><span>${r.date}</span></div><div style="font-size: 14px;">${r.text}</div></div>`; });
        } catch(e) {}
    }

    window.submitReview = async function() {
        const input = document.getElementById('reviewInput');
        if(!input.value.trim()) return;
        await fetch('/api/reviews', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ name: userInfo.first_name || userInfo.username, text: input.value }) });
        input.value = ''; loadReviews();
    }

    // --- КАЛЬКУЛЯТОР ---
    let calcPeriodDays = 30;
    window.addAmount = function(v) { document.getElementById('calcAmount').value = (parseFloat(document.getElementById('calcAmount').value || 0) + v).toFixed(0); window.calculateProfit(); };
    window.setPeriod = function(d, btn) { calcPeriodDays = d; document.querySelectorAll('#periodButtons .chip').forEach(c => c.classList.remove('active')); btn.classList.add('active'); window.calculateProfit(); };
    window.calculateProfit = function() {
        let amt = parseFloat(document.getElementById('calcAmount').value || 0);
        let final = amt * Math.pow((1 + 0.0253), calcPeriodDays);
        document.getElementById('calcFinal').innerText = '$' + final.toLocaleString('en-US', {maximumFractionDigits: 2});
        document.getElementById('calcProfitPercent').innerText = '+' + ((final-amt)/amt*100).toFixed(0) + '%';
    };

    document.addEventListener("DOMContentLoaded", () => { loadStateFromDB(); });
    </script>
</body>
</html>
"""


# ==========================================
# 4. ВЕБ-СЕРВЕР И API
# ==========================================
async def web_app_handler(request):
    return web.Response(text=HTML_CONTENT, content_type="text/html", headers=HTTP_HEADERS)


async def api_get_user(request):
    user_id = request.query.get('id')
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT balance, in_bots, profit, lang, bots_data FROM users WHERE user_id = ?",
                              (int(user_id),)) as cursor:
            row = await cursor.fetchone()
            if row:
                return web.json_response(
                    {"balance": row[0], "in_bots": row[1], "profit": row[2], "lang": row[3], "bots_data": row[4]})
            else:
                await db.execute("INSERT INTO users (user_id) VALUES (?)", (int(user_id),))
                await db.commit()
                return web.json_response({"balance": 0, "in_bots": 0, "profit": 0, "lang": "en", "bots_data": "[]"})


async def api_save_user(request):
    data = await request.json()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance=?, in_bots=?, profit=?, lang=?, bots_data=? WHERE user_id=?",
                         (data['balance'], data['in_bots'], data['profit'], data['lang'], data['bots_data'],
                          int(data['user_id'])))
        await db.commit()
    return web.json_response({"status": "ok"})


async def api_get_reviews(request):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT name, text, date FROM reviews ORDER BY id DESC LIMIT 30") as cursor:
            rows = await cursor.fetchall()
            return web.json_response([{"name": r[0], "text": r[1], "date": r[2]} for r in rows])


async def api_add_review(request):
    data = await request.json()
    date_str = datetime.now().strftime("%d.%m %H:%M")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO reviews (name, text, date) VALUES (?, ?, ?)",
                         (data['name'], data['text'], date_str))
        await db.commit()
    return web.json_response({"status": "ok"})


async def api_create_invoice(request):
    if not CRYPTO_TOKEN: return web.json_response({"error": "No token"}, status=500)
    user_id, amount = request.query.get('user_id'), request.query.get('amount')
    headers = {"Crypto-Pay-API-Token": CRYPTO_TOKEN}
    payload = {"asset": "USDT", "amount": str(amount), "payload": str(user_id)}
    async with aiohttp.ClientSession() as session:
        async with session.post("https://pay.crypt.bot/api/createInvoice", headers=headers, data=payload) as resp:
            data = await resp.json()
            return web.json_response({"url": data["result"]["bot_invoice_url"]}) if data.get(
                "ok") else web.json_response({"error": data})


async def proxy_24hr(request):
    async with aiohttp.ClientSession(headers=API_HEADERS) as session:
        async with session.get("https://api.bybit.com/v5/market/tickers?category=linear") as resp:
            return web.json_response(await resp.json(), headers=HTTP_HEADERS)


async def proxy_klines(request):
    symbol = request.query.get('symbol', 'BTCUSDT').upper()
    limit = request.query.get('limit', '100')
    interval = request.query.get('interval', '15')  # Получаем таймфрейм из запроса
    url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit={limit}"

    async with aiohttp.ClientSession(headers=API_HEADERS) as session:
        async with session.get(url) as resp:
            return web.json_response(await resp.json(), headers=HTTP_HEADERS)


async def proxy_price(request):
    symbol = request.query.get('symbol', 'BTCUSDT').upper()
    async with aiohttp.ClientSession(headers=API_HEADERS) as session:
        async with session.get(f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}") as resp:
            return web.json_response(await resp.json(), headers=HTTP_HEADERS)


async def start_web_server():
    app = web.Application()
    app.router.add_get('/', web_app_handler)
    app.router.add_get('/api/user', api_get_user)
    app.router.add_post('/api/user', api_save_user)
    app.router.add_get('/api/reviews', api_get_reviews)
    app.router.add_post('/api/reviews', api_add_review)
    app.router.add_get('/api/invoice', api_create_invoice)
    app.router.add_get('/api/24hr', proxy_24hr)
    app.router.add_get('/api/klines', proxy_klines)
    app.router.add_get('/api/price', proxy_price)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', WEB_SERVER_PORT).start()


# ==========================================
# 5. ТЕЛЕГРАМ БОТ
# ==========================================
@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Start Terminal", web_app=WebAppInfo(url=WEBAPP_URL))
    await message.answer(
        f"Hi, {html.bold(message.from_user.full_name)}! Welcome to TradeBot Premium. Press the button below to start trading.",
        reply_markup=builder.as_markup()
    )


async def main() -> None:
    if not BOT_TOKEN: return
    await init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await start_web_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())