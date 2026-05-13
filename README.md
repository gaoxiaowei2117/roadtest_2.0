# ICBC Road Test Auto Booking

ICBC（卑诗省保险公司）路考自动查询和抢号工具。轮询 ICBC 在线系统，发现符合条件的考位时自动锁定、从 Gmail 取验证码并完成预约。

## 功能

- 按日期范围、时间段、考点、星期、上/下午等条件过滤考位
- 发现可用考位时多通道通知：SMS（Twilio）、PushDeer、ntfy、本地桌面通知、声音
- 自动预约：锁位 → 触发验证码邮件 → 从 Gmail IMAP 拉取验证码 → 提交预约
- 基于 Playwright 浏览器自动化登录（绕过 KBA），带 4 分钟 token 缓存

## 环境要求

- **Python 3.9+**（用到了 `zoneinfo`）
- **Linux / macOS**（脚本默认）。Windows 未测试。
- 网络可访问 `onlinebusiness.icbc.com` 和 `imap.gmail.com`
- 一个开启了"两步验证 + 应用专用密码"的 Gmail 账号（用于读取验证码邮件）
- 一个有效的 BC 驾照 + ICBC 关键词

## 依赖项

### Python 包（pip 安装）

| 包 | 用途 |
|---|---|
| `requests` | 调 ICBC REST API（查询/锁位/预约） |
| `PyYAML` | 读取 `config.yml` |
| `faker` | 生成请求头中的随机 User-Agent |
| `twilio` | SMS 推送（可选） |
| `pypushdeer` | PushDeer 推送（可选） |
| `playwright` | 浏览器自动化登录 ICBC 取 token |

### Playwright 浏览器二进制

`pip install playwright` 之后还需要单独下载 Chromium：

```bash
playwright install chromium
```

### 系统命令（可选，仅当启用对应通知时）

| 命令 | 用途 |
|---|---|
| `notify-send` | 桌面通知 (`pushlocal.enable=true`)，Linux 上由 `libnotify-bin` 提供 |
| `beep` / `mpg123` / `paplay` / `aplay` / `ffplay` | 声音通知 (`pushsound.enable=true`)，任选其一 |

## 安装

```bash
# 1. 安装 Python 依赖
pip3 install -r requirements.txt

# 2. 下载 Chromium（Playwright 用）
playwright install chromium

# 3. 如果要桌面通知（可选，仅 Linux）
sudo apt install libnotify-bin

# 4. 给启动脚本加执行权限
chmod +x start.sh
```

## 配置 `config.yml`

仓库**不包含**真实的 `config.yml`（已在 `.gitignore` 中），请基于模板创建：

```bash
cp config.yml.example config.yml
# 然后用编辑器填入你自己的驾照信息和 Gmail 应用密码
```

关键字段（节选自 `config.yml.example`）：

```yaml
icbc:
  drvrLastName: "YourLastName"     # 驾照姓
  licenceNumber: "00000000"        # 驾照号
  keyword: "0000"                  # ICBC 关键词
  DateOfIssue: "2025-JAN-01"       # 驾照发证日期，格式 YYYY-MMM-DD
  expactAfterDate: "2026-07-01"    # 想约的最早日期
  expactBeforeDate: "2026-08-31"   # 想约的最晚日期
  expactTimeRange: "10:00-15:00"   # 想约的时间段
  examClass: "5"                   # 5 = Class 5 路考
  posID: "274"                     # 考点 ID

gmail:
  enable: true
  email: "yourname@gmail.com"
  password: "xxxx xxxx xxxx xxxx"  # Gmail 应用专用密码（非账户密码）
                                    # 创建方式: Google 账号 → 安全 → 两步验证 → 应用密码

autoBooking:
  enable: true                     # true = 发现考位自动预约；false = 仅通知
  exitAfterSuccess: true           # 成功预约后退出
```

> ⚠️ **隐私警告**：`config.yml` 含驾照号 / Gmail 应用密码等敏感信息，**绝对不要**提交到公开仓库。本仓库的 `.gitignore` 已自动忽略 `config.yml`，请勿改动该规则。

通知通道（按需启用）：`pushsms` (Twilio) / `pushdeer` / `ntfy` / `pushlocal` / `pushsound`，默认全部 `enable: false`。

## 运行

### 推荐：使用启动脚本

```bash
./start.sh
```

菜单：
- `1` 测试模式（**注意**：依赖 `test_road.py`，仓库中暂未提供）
- `2` 实盘模式（连接真实 ICBC 系统）
- `3` 查看运行状态
- `4` 查看最近日志

### 直接命令行

```bash
# 实盘抢号
python3 road.py config.yml

# 查看状态
python3 status.py

# 仅测试登录流程
python3 playwright_login.py

# 测试 token 缓存
python3 token_manager.py
```

## 文件结构

```
roadtest_template/
├── road.py                # 主程序（轮询 + 抢号 + 通知）
├── playwright_login.py    # 浏览器登录，提取 Authorization token
├── token_manager.py       # Token 缓存（4 分钟 TTL）
├── status.py              # 查看预约状态
├── start.sh               # 交互式启动菜单
├── config.yml             # 配置文件
├── requirements.txt       # Python 依赖
└── log/                   # 运行时数据（last_run、processed_emails、debug 截图等）
```

## 工作流程

1. **登录**：Playwright 用无头 Chromium 模拟真实用户操作，填驾照号 + 发证日期 + 关键词，从网络请求中抓取 `Authorization: Bearer` token
2. **轮询**：每隔几秒调 `getAvailableAppointments` 接口，按 `config.yml` 的过滤条件筛选
3. **发现考位**：触发通知 → 调 `putLock` 锁位 → 调 `postMsg` 发送验证码到 Gmail
4. **取验证码**：通过 IMAP 读 Gmail 最新邮件，正则提取 6 位验证码
5. **完成预约**：用验证码调 `verifyBooking` 提交，结果写入 `booking_status.json`

## 已知问题

- `start.sh` 选项 1 调用的 `test_road.py` 在当前仓库中**不存在**

## 注意

- ICBC 反爬较严格，轮询过快会被封 IP / 锁账号。配置里 `requestLimit` 可限速。
- 实际抢号成功后，去 ICBC 官网二次确认预约状态。
- Gmail 密码必须使用「应用专用密码」，普通账户密码无法通过 IMAP 登录。
