# Supertrend Algo — TradingView to MetaTrader 5 Bridge

A multi-user web application that receives trade signals from **TradingView** and automatically executes them on **MetaTrader 5** brokers such as Exness, FundingPips, FundedNext, and any other MT5-compatible broker.

---

## How It Works

```
TradingView Alert (Pine Script)
        │
        │  HTTP POST (JSON)
        ▼
Flask Web App  (/tvwebhook)
        │
        │  Identifies user by secret key
        │  Parses signal (direction, lot size, magic)
        ▼
MT5 Worker Process (per user)
        │
        │  MetaTrader5 Python API
        ▼
MT5 Terminal → Broker Server → Trade Executed
```

Each user has their own dedicated background process connected to their MT5 account. Multiple users can fire signals simultaneously — orders execute in parallel.

---

## Requirements

| Requirement | Details |
|---|---|
| **Operating System** | Windows only (MetaTrader5 Python package is Windows-exclusive) |
| **Python** | 3.10 or higher |
| **MetaTrader 5** | MT5 terminal installed and running on the same machine |
| **Broker** | Any MT5 broker (Exness, FundingPips, FundedNext, etc.) |
| **TradingView** | Any plan that supports webhook alerts |

---

## Installation

### Step 1 — Install Python dependencies

Open a Command Prompt or PowerShell in the project folder and run:

```bat
pip install -r requirements.txt
```

### Step 2 — Install and log in to MetaTrader 5

1. Download and install the MT5 terminal from your broker's website
2. Open MT5 and log in to your trading account
3. **Keep MT5 running** — the app connects to it in the background

### Step 3 — First-time setup

Run the application for the first time:

```bat
python main.py
```

or double-click `execute_main.bat`

On the first run you will be prompted to enter:

| Prompt | Description |
|---|---|
| `REGISTER_SECRETKEY` | A password you choose. Anyone registering a new account needs this key. |
| `SUPERUSER_USERNAME` | Admin account username |
| `SUPERUSER_NAME` | Admin account display name |
| `SUPERUSER_PASSWORD` | Admin account password (hidden input) |
| `NGROK_ENABLED (y/n)` | Type `y` to get a public webhook URL via ngrok (required if TradingView cannot reach your local machine) |

These are saved to a `.env` file — you will not be asked again on future runs.

> **Note:** If upgrading from the Dhan version of this app, delete `instance/database.db` before running for the first time. The database schema has changed completely.

---

## Running the App

```bat
python main.py
```

or double-click:

```
execute_main.bat
```

The app starts on port **8501**. Open your browser and go to:

```
http://localhost:8501
```

---

## User Setup (Web Interface)

### 1. Register an Account

Go to `http://localhost:8501/register`

- Enter a username, your full name, a password, and the **Register Secret Key** you set during first-time setup.
- Each trader who wants to use the bot needs their own account.

### 2. Connect Your MT5 Account

Go to **Profile** (top navigation)

Fill in the MT5 Account section:

| Field | Description | Example |
|---|---|---|
| MT5 Account Number | Your numeric MT5 login ID | `12345678` |
| MT5 Password | Your MT5 trading password | `MyPassword123` |
| MT5 Server | Your broker's MT5 server name | `Exness-MT5Real8` |
| Broker Name | Your broker's name (for display) | `Exness` |

Click **Connect**. The status badge will show **CONNECTED** if successful.

> **How to find your MT5 Server name:** Open MetaTrader 5 → File → Login to Trade Account → the server list shows all available server names for your broker.

#### Common MT5 Server Names

| Broker | Example Server Name |
|---|---|
| Exness | `Exness-MT5Real8`, `Exness-MT5Trial` |
| FundingPips | `FundingPips-Server` |
| FundedNext | `FundedNext-Server` |

> Check your broker's website or the MT5 terminal's server list for the exact name.

### 3. Get Your Webhook URL

Go to **Dashboard**. You will see:

- **Webhook URL** — copy this and paste it into TradingView
- **Alert Message Template** — copy this as a starting point for your TradingView alert

---

## TradingView Setup

### Step 1 — Create a Pine Script Alert

In your TradingView chart, right-click on your indicator/strategy → **Add Alert**

### Step 2 — Configure the Alert

- **Condition:** Your indicator signal
- **Webhook URL:** Paste the URL from the Dashboard
- **Message:** Use the template below

### Alert Message Format

```json
{
  "secret": "YOUR_TV_SECRET",
  "ticker": "XAUUSD",
  "volume": 0.01,
  "magic": 1001,
  "alert_message": "long entry"
}
```

Your `secret` is shown in the Dashboard template (pre-filled for you).

### Field Reference

| Field | Type | Description |
|---|---|---|
| `secret` | string | Your unique webhook secret from the Dashboard. Identifies your account. |
| `ticker` | string | The MT5 symbol name **exactly as it appears in your broker's MT5**. |
| `volume` | float | Lot size. Minimum `0.01`. Can be a fixed number or a TradingView variable. |
| `magic` | integer | A unique number per strategy. Used to track and close specific trades. |
| `alert_message` | string | The trade signal. See options below. |

### Alert Message Options

| Value | Action |
|---|---|
| `long entry` | Buy (open long position) |
| `long exit` | Close long position |
| `long exit SL` | Close long — logged with reason "SL" (stop loss) |
| `long exit TP` | Close long — logged with reason "TP" (take profit) |
| `short entry` | Sell (open short position) |
| `short exit` | Close short position |
| `short exit SL` | Close short — logged with reason "SL" |
| `short exit TP` | Close short — logged with reason "TP" |

You can add any word after the direction as the exit reason (e.g., `long exit TRAIL`).

---

## The Magic Number — How Trade Tracking Works

The `magic` number is how the bot knows **which specific trade to close** when an exit signal fires.

- When you **enter** a trade with `magic: 1001`, MT5 tags that position with `1001`
- When you **exit** with `magic: 1001`, the bot finds only the position tagged `1001` and closes it
- All other open positions (with different magic numbers) are **untouched**

**This means you can run multiple strategies simultaneously on the same symbol:**

```
Strategy A fires "long entry"  magic=1001  → opens position A
Strategy B fires "short entry" magic=2002  → opens position B
Strategy A fires "long exit"   magic=1001  → closes position A only
Strategy B is still running                → position B untouched
```

**Rule: Each strategy must have its own unique magic number.**

---

## Broker Symbol Names

Symbol names vary by broker. Always use the exact symbol name as shown in your broker's MT5 Market Watch.

| Instrument | Exness Example | Generic MT5 |
|---|---|---|
| Gold | `XAUUSDm` or `XAUUSD` | `XAUUSD` |
| Oil (WTI) | `USOILm` or `USOUSD` | `USOIL` |
| Euro/Dollar | `EURUSDm` or `EURUSD` | `EURUSD` |
| US30 (Dow) | `US30` or `DJ30` | `US30` |
| NAS100 | `NAS100` or `USTEC` | `NAS100` |
| S&P 500 | `SPX500` or `US500` | `SP500` |

> If an order fails with "symbol not found", check the exact symbol name in your MT5 Market Watch window.

---

## Multiple Users / Prop Firm Accounts

Each trader registers their own account on the web interface and connects their own MT5 credentials. Signals are completely isolated per user — User A's webhook only affects User A's MT5 account.

A single installation can serve **many users simultaneously**. Each user's trades run in a parallel background process — no blocking or queuing.

---

## Enabling Public Webhook URL (ngrok)

TradingView needs to reach your machine over the internet. If your machine is not publicly accessible (home internet, no static IP), use ngrok:

1. Set `NGROK_ENABLED=1` in your `.env` file
2. Sign up at [ngrok.com](https://ngrok.com) and get a free auth token
3. Run `ngrok authtoken YOUR_TOKEN` once in your terminal
4. Restart the app — the Dashboard will show your public ngrok URL

> **Important:** The ngrok URL changes every time you restart the app on a free plan. Update your TradingView alert webhook URL whenever you restart.

For a stable URL, run the app on a Windows VPS with a static IP and use the machine's IP directly.

---

## File Structure

```
supertrend-algo-exness-master/
├── main.py                   # Entry point — starts Flask + MT5 workers
├── requirements.txt          # Python dependencies
├── .env                      # Your configuration (auto-created on first run)
├── .env.template             # Template for .env
├── execute_main.bat          # Windows double-click launcher
│
├── utils/
│   ├── mt5_manager.py        # MT5 worker processes + order execution
│   ├── shared.py             # Shared utilities and logger
│   └── logger.py             # Rotating log file setup
│
├── web/
│   ├── __init__.py           # Flask app factory
│   ├── auth.py               # Login, register, admin user
│   ├── views.py              # Dashboard, profile, MT5 credential forms
│   ├── tvviews.py            # TradingView webhook handler
│   ├── models.py             # Database models (User, MT5Account, Trade)
│   └── templates/            # HTML pages
│
└── instance/
    ├── database.db           # SQLite database (auto-created)
    └── logs/app.log          # Application log (auto-created)
```

---

## Troubleshooting

### MT5 shows DISCONNECTED after entering credentials

- Make sure the **MT5 terminal is open and running** on the same machine
- Double-check the **server name** — it must match exactly (case-sensitive)
- Verify the **account number and password** are correct
- Some brokers require you to enable **Algo Trading** in MT5: Tools → Options → Expert Advisors → Allow Automated Trading

### Order placed but no trade appears in MT5

- Check that **Algo Trading is enabled** in MT5 (the robot icon in the toolbar should be green)
- Verify the **symbol name** matches exactly what is in your broker's Market Watch
- Check `logs/app.log` for the full error message from MT5

### TradingView alert fires but webhook shows no response

- Confirm the **Webhook URL** in your TradingView alert matches the Dashboard URL exactly
- If using ngrok, check that it is still running and the URL has not changed
- Check that the **JSON in the alert message is valid** (no extra quotes or missing braces)
- Check `logs/app.log` for incoming webhook logs

### Two strategies closing each other's trades

- Each strategy must have a **different magic number**
- Check that your exit alerts are sending the correct magic number

### App crashes on startup

- Make sure you have run `pip install -r requirements.txt`
- Ensure you are on **Windows** (MetaTrader5 package does not work on Mac or Linux)
- Check the console output for the specific error

---

## Log File

All activity is logged to:

```
logs/app.log
```

The log rotates automatically at 10 MB with up to 10 backup files. Check this file first when debugging any issue.

---

## Security Notes

- Keep your `.env` file private — it contains your admin password
- Each user's TradingView `secret` is unique and auto-generated — do not share it
- MT5 passwords are stored in the local SQLite database — keep the `instance/` folder secure
- If deploying on a VPS, use a firewall to restrict access to port 8501

---

## Version

**v2.0.0** — MT5 Edition  
Replaces the original Dhan (NSE India) integration with MetaTrader 5 support for Forex, Metals, Oils, and Indices trading across multiple international brokers.
