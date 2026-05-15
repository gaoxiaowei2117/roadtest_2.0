> # ⚠️ Deprecated — moved to a newer version
>
> **👉 Use [`icbc-roadtest-auto-booking`](https://github.com/gaoxiaowei2117/icbc-roadtest-auto-booking) instead** — bilingual docs, better-organised code, more features.
>
> This repo is kept here for history and is **archived (read-only)**. No further updates will land here.

---

<h1 align="center">🚗 ICBC Road Test Auto Booking</h1>

<p align="center">
  <em>Polls ICBC's online appointment system and books your BC road test the instant a slot opens — pulling the verification code straight from Gmail.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/Playwright-2EAD33?logo=playwright&logoColor=white" alt="Playwright"/>
  <img src="https://img.shields.io/badge/Region-BC%2C%20Canada-red" alt="BC"/>
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT"/>
  <img src="https://img.shields.io/github/last-commit/gaoxiaowei2117/roadtest_2.0" alt="last commit"/>
</p>

<p align="center">
  <a href="#-features">Features</a> ·
  <a href="#-quick-start">Quick start</a> ·
  <a href="#-configuration">Configuration</a> ·
  <a href="#-notifications">Notifications</a> ·
  <a href="#-faq">FAQ</a>
</p>

> [中文 README](#中文说明) 在下方。

---

## ✨ Features

- 🎯 **Smart filtering** — filter by date range, time window, exam centre, day of week, AM/PM
- 🔔 **Multi-channel alerts** — SMS (Twilio), PushDeer, ntfy, desktop, sound
- 🤖 **Hands-off booking** — locks the slot → triggers the verification email → reads it from Gmail IMAP → confirms the booking
- 🧠 **Playwright login** that bypasses KBA, with a 4-minute token cache
- 🧪 **Dry-run mode** so you can test the pipeline without spending money

## 📦 Quick start

```bash
# 1. Clone
git clone https://github.com/gaoxiaowei2117/roadtest_2.0.git
cd roadtest_2.0

# 2. Install Python deps
pip3 install -r requirements.txt
playwright install chromium

# 3. (Optional, Linux only) desktop notifications
sudo apt install libnotify-bin

# 4. Configure
cp config.yml.example config.yml
$EDITOR config.yml          # fill in licence + Gmail App Password

# 5. Run
chmod +x start.sh && ./start.sh
```

Pick `2` from the menu for **live mode**.

## ⚙️ Configuration

Fill in `config.yml` — only the fields below are mandatory:

```yaml
icbc:
  drvrLastName:    "YourLastName"
  licenceNumber:   "00000000"
  keyword:         "0000"
  DateOfIssue:     "2025-JAN-01"     # YYYY-MMM-DD
  expactAfterDate: "2026-07-01"
  expactBeforeDate:"2026-08-31"
  expactTimeRange: "10:00-15:00"
  examClass:       "5"               # Class 5 road test
  posID:           "274"             # exam centre id

gmail:
  enable:   true
  email:    "yourname@gmail.com"
  password: "xxxx xxxx xxxx xxxx"   # Gmail App Password — NOT your real password
```

> 🔐 **`config.yml` is in `.gitignore` — keep it that way.** It contains your licence number and Gmail App Password.

Full reference and all optional knobs live in [`config.yml.example`](./config.yml.example).

## 📣 Notifications

All channels default to `enable: false`. Turn on what you need:

| Channel    | Why                                | Config key   |
|------------|-----------------------------------|--------------|
| Twilio SMS | Reliable, costs money              | `pushsms`    |
| PushDeer   | Free push to phone via WeChat      | `pushdeer`   |
| ntfy       | Free self-hostable push            | `ntfy`       |
| Desktop    | `notify-send` popup on Linux       | `pushlocal`  |
| Sound      | `paplay`/`aplay`/`ffplay`/`beep`   | `pushsound`  |

## 🗂️ Project layout

```
.
├── road.py                # main loop (poll + book + notify)
├── playwright_login.py    # browser login, extracts auth token
├── token_manager.py       # token cache (4-min TTL)
├── status.py              # show current state
├── start.sh               # interactive launcher
├── config.yml.example     # template — copy to config.yml
└── requirements.txt
```

## 🛡️ Disclaimer

This project automates **public** ICBC endpoints to book **your own** road test. It does not bypass auth, payment, or rate limits beyond what a human user would. Use responsibly and at your own risk — ICBC may change their API at any time.

## ❓ FAQ

<details>
<summary><b>I get "Authentication failed" from Gmail.</b></summary>

You're using your real Gmail password. Generate an **App Password**: Google Account → Security → 2-Step Verification → App passwords. Paste the 16-char string (with spaces) into `gmail.password`.
</details>

<details>
<summary><b>Playwright says <code>browser not found</code>.</b></summary>

Run `playwright install chromium` after `pip install playwright`.
</details>

<details>
<summary><b>How do I find <code>posID</code> for my exam centre?</b></summary>

Open the ICBC booking page in DevTools → Network → search for the request to `/qmaticwebbooking/rest/schedule/...`. The `serviceId` in the response maps to each centre. Common ones: `9` Burnaby, `274` Vancouver Point Grey.
</details>

## 📄 License

MIT — see [LICENSE](./LICENSE).

---

## 中文说明

ICBC（卑诗省保险公司）路考自动查询和抢号工具。轮询 ICBC 在线系统，发现符合条件的考位时自动锁定、从 Gmail 取验证码并完成预约。

### 功能

- 按日期范围、时间段、考点、星期、上/下午等条件过滤考位
- 发现可用考位时多通道通知：SMS（Twilio）、PushDeer、ntfy、本地桌面通知、声音
- 自动预约：锁位 → 触发验证码邮件 → 从 Gmail IMAP 拉取验证码 → 提交预约
- 基于 Playwright 浏览器自动化登录（绕过 KBA），带 4 分钟 token 缓存

### 快速开始

```bash
git clone https://github.com/gaoxiaowei2117/roadtest_2.0.git
cd roadtest_2.0
pip3 install -r requirements.txt
playwright install chromium
cp config.yml.example config.yml      # 编辑填入驾照信息和 Gmail 应用密码
./start.sh                            # 选 2 进入实盘模式
```

### 隐私警告

⚠️ `config.yml` 含驾照号 / Gmail 应用密码等敏感信息，**绝对不要**提交到公开仓库。本仓库的 `.gitignore` 已自动忽略 `config.yml`，请勿改动该规则。

### 完整文档

英文版的 [Features](#-features) / [Configuration](#-configuration) / [FAQ](#-faq) 章节内容完全适用，结构和翻译保持一致。
