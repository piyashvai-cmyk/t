# -*- @MASTER_FF_01 -*-
"""
MASTER OFFICIAL - Dashboard Server (BD Version)
Full Web Dashboard with Blue Ninja Theme
+Pause/Delete fully functional
"""

import asyncio
import json
import os
import time
from typing import Dict, List, Any, Optional
from aiohttp import web


# ==================== GLOBAL STATE ====================
class BotState:
    def __init__(self):
        self.accounts: Dict[str, Dict[str, Any]] = {}
        self.logs: List[Dict[str, Any]] = []
        self.max_logs = 200
        self.total_matches = 0
        self.total_gained_exp = 0
        self.start_time = time.time()
        self.account_workers: Dict[str, asyncio.Task] = {}
        self.refresh_callbacks: Dict[str, Any] = {}
        self.account_credentials: Dict[str, Dict[str, Any]] = {}

    def log(self, message: str, level: str = "info", uid: Optional[str] = None):
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "level": level,
            "message": message,
            "uid": uid
        }
        self.logs.append(entry)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)

    def register_account(self, uid: str, nickname: str, region: str, level: int, exp: int, likes: int = 0):
        uid_str = str(uid)
        if uid_str not in self.accounts:
            self.accounts[uid_str] = {
                "uid": uid_str,
                "nickname": nickname or f"Player_{uid_str[:6]}",
                "region": region or "BD",
                "level": level or 1,
                "initial_exp": exp,
                "current_exp": exp,
                "gained_exp": 0,
                "likes": likes or 0,
                "status": "ONLINE",
                "matches_played": 0,
                "active_matches": 0,
                "last_match_time": None,
                "last_updated": time.strftime("%H:%M:%S"),
                "is_paused": False,
                "uptime_seconds": int(time.time()),
                "match_history": []
            }
        else:
            acc = self.accounts[uid_str]
            if nickname:
                acc["nickname"] = nickname
            if region:
                acc["region"] = region
            if level:
                acc["level"] = level
            acc["current_exp"] = exp
            acc["gained_exp"] = max(0, exp - acc["initial_exp"])
            acc["likes"] = likes
            # Don't override PAUSED / OFFLINE status
            if not acc.get("is_paused", False) and acc.get("status") not in ("PAUSED", "OFFLINE"):
                acc["status"] = "ONLINE"
            acc["last_updated"] = time.strftime("%H:%M:%S")
        self.recalc_totals()

    def update_exp(self, uid: str, current_exp: int, level: Optional[int] = None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            acc = self.accounts[uid_str]
            old_exp = acc["current_exp"]
            acc["current_exp"] = current_exp
            if level is not None and level > 0:
                acc["level"] = level
            acc["gained_exp"] = max(0, current_exp - acc["initial_exp"])
            acc["last_updated"] = time.strftime("%H:%M:%S")
            diff = current_exp - old_exp
            if diff > 0:
                self.log(f"{acc['nickname']} gained +{diff} EXP! Total: +{acc['gained_exp']}", "success", uid_str)
            self.recalc_totals()

    def update_status(self, uid: str, status: str, active_matches: Optional[int] = None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            acc = self.accounts[uid_str]
            # If account is paused, don't let external updates override
            if acc.get("is_paused", False) and status not in ("PAUSED", "OFFLINE"):
                return
            acc["status"] = status
            if active_matches is not None:
                acc["active_matches"] = active_matches
            acc["last_updated"] = time.strftime("%H:%M:%S")

    def increment_match(self, uid: str):
        uid_str = str(uid)
        self.total_matches += 1
        if uid_str in self.accounts:
            acc = self.accounts[uid_str]
            acc["matches_played"] += 1
            acc["last_match_time"] = time.strftime("%H:%M:%S")
            acc["last_updated"] = time.strftime("%H:%M:%S")
            history = acc.get("match_history", [])
            history.append({
                "time": time.strftime("%H:%M:%S"),
                "msg": f"Match #{acc['matches_played']} completed"
            })
            if len(history) > 20:
                history.pop(0)
            acc["match_history"] = history
            self.log(f"{acc['nickname']} finished Match #{acc['matches_played']}", "info", uid_str)

    def recalc_totals(self):
        self.total_gained_exp = sum(acc.get("gained_exp", 0) for acc in self.accounts.values())

    def get_exp_per_hour(self) -> int:
        elapsed = max(1, time.time() - self.start_time)
        return int(self.total_gained_exp / (elapsed / 3600))

    def get_total_active_matches(self) -> int:
        return sum(acc.get("active_matches", 0) for acc in self.accounts.values())


bot_state = BotState()


# ==================== PATHS ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(TEMPLATES_DIR, "static")
TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "index.html")
ACCOUNTS_FILE = "accounts.json"


# ==================== HTTP HANDLERS ====================

async def handle_index(request: web.Request) -> web.Response:
    if os.path.exists(TEMPLATE_PATH):
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = """
        <html><body style="background:#050a18;color:#e8f4ff;font-family:sans-serif;padding:40px;text-align:center">
        <h1>⚠️ templates/index.html not found!</h1>
        <p>Please create templates/index.html</p>
        </body></html>
        """
    return web.Response(text=content, content_type="text/html", charset="utf-8")


async def handle_get_stats(request: web.Request) -> web.Response:
    accounts_data = list(bot_state.accounts.values())
    accounts_data.sort(key=lambda x: x.get("gained_exp", 0), reverse=True)
    return web.json_response({
        "total_accounts": len(bot_state.accounts),
        "total_matches": bot_state.total_matches,
        "total_matches_started": bot_state.total_matches,
        "total_gained_exp": bot_state.total_gained_exp,
        "total_active_matches": bot_state.get_total_active_matches(),
        "exp_per_hour": bot_state.get_exp_per_hour(),
        "accounts": accounts_data,
        "logs": bot_state.logs[-60:],
        "uptime": int(time.time() - bot_state.start_time)
    })


async def handle_add_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        existing = []
        if os.path.exists(ACCOUNTS_FILE):
            try:
                with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        if "uid" in data and "password" in data:
            uid = str(data["uid"]).strip()
            pwd = str(data["password"]).strip()
            if not uid or not pwd:
                return web.json_response({"status": "error", "error": "UID and Password required"})
            existing = [acc for acc in existing if str(acc.get("uid")) != uid]
            existing.append({"uid": uid, "password": pwd})
        elif "token" in data:
            token = str(data["token"]).strip()
            if not token:
                return web.json_response({"status": "error", "error": "Token required"})
            existing = [acc for acc in existing if acc.get("token") != token]
            existing.append({"token": token})
        else:
            return web.json_response({"status": "error", "error": "Invalid payload"})

        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)

        bot_state.log(f"New account added: {data.get('uid') or 'Token'}", "success")

        if "on_account_added" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_account_added"](data))

        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_delete_account(request: web.Request) -> web.Response:
    """
    Fully deletes account:
    1. Remove from accounts.json
    2. Mark as paused (so loops see it as deleted)
    3. Delete from bot_state.accounts (loops will detect `None`)
    4. Cancel worker task
    5. Remove credentials
    """
    try:
        data = await request.json()
        uid = str(data.get("uid")).strip()

        # 1. Remove from accounts.json
        if os.path.exists(ACCOUNTS_FILE):
            try:
                with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                existing = [
                    acc for acc in existing
                    if str(acc.get("uid")) != uid
                    and str(acc.get("token", ""))[:20] != uid
                ]
                with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(existing, f, indent=2)
            except Exception as e:
                bot_state.log(f"Error updating accounts.json: {e}", "error", uid)

        # 2 & 3. Mark paused then remove from state
        if uid in bot_state.accounts:
            try:
                bot_state.accounts[uid]["is_paused"] = True
                bot_state.accounts[uid]["status"] = "OFFLINE"
            except Exception:
                pass
            try:
                del bot_state.accounts[uid]
            except Exception:
                pass

        # 4. Cancel worker task
        if uid in bot_state.account_workers:
            task = bot_state.account_workers.pop(uid)
            try:
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=5.0)
                except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                    pass
            except Exception:
                pass

        # 5. Remove credentials
        bot_state.account_credentials.pop(uid, None)
        # Also remove any token-based credentials
        keys_to_del = [k for k in bot_state.account_credentials if k.startswith(f"tok_{uid[:20]}")]
        for k in keys_to_del:
            bot_state.account_credentials.pop(k, None)

        bot_state.log(f"Account {uid} removed (offline)", "warning", uid)
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_pause_account(request: web.Request) -> web.Response:
    """
    Toggle pause. When paused:
    - is_paused=True
    - status=PAUSED
    - All loops (TCP, UDP, informational) will disconnect within 2-3 sec
    When resumed:
    - is_paused=False
    - status=ONLINE (login will restart)
    """
    try:
        data = await request.json()
        uid = str(data.get("uid")).strip()
        if uid in bot_state.accounts:
            acc = bot_state.accounts[uid]
            new_pause_state = not acc.get("is_paused", False)
            acc["is_paused"] = new_pause_state
            acc["status"] = "PAUSED" if new_pause_state else "ONLINE"
            acc["last_updated"] = time.strftime("%H:%M:%S")

            if new_pause_state:
                bot_state.log(f"Account {uid} PAUSED (offline)", "warning", uid)
            else:
                bot_state.log(f"Account {uid} RESUMED (online)", "success", uid)

            return web.json_response({
                "status": "ok",
                "is_paused": new_pause_state,
                "new_status": acc["status"]
            })
        return web.json_response({"status": "error", "error": "Account not found"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_pause_all(request: web.Request) -> web.Response:
    """Toggle all accounts. If any is running, pause all. Else resume all."""
    try:
        if not bot_state.accounts:
            return web.json_response({"status": "error", "error": "No accounts"})

        # If ALL are paused → resume all. Else pause all.
        all_paused = all(acc.get("is_paused", False) for acc in bot_state.accounts.values())
        new_state = not all_paused

        for acc in bot_state.accounts.values():
            acc["is_paused"] = new_state
            acc["status"] = "PAUSED" if new_state else "ONLINE"
            acc["last_updated"] = time.strftime("%H:%M:%S")

        if new_state:
            bot_state.log("All accounts PAUSED (offline)", "warning")
        else:
            bot_state.log("All accounts RESUMED (online)", "success")

        return web.json_response({"status": "ok", "all_paused": new_state})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_refresh_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid")).strip()
        if "on_refresh_account" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_refresh_account"](uid))
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_restart_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid")).strip()
        if uid in bot_state.account_workers:
            try:
                bot_state.account_workers[uid].cancel()
            except Exception:
                pass
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_clear_logs(request: web.Request) -> web.Response:
    try:
        bot_state.logs.clear()
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


# ==================== SERVER START ====================

async def start_web_dashboard(host: str = "0.0.0.0", port: int = 20337):
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/stats", handle_get_stats)
    app.router.add_post("/api/account/add", handle_add_account)
    app.router.add_post("/api/account/delete", handle_delete_account)
    app.router.add_post("/api/account/refresh", handle_refresh_account)
    app.router.add_post("/api/account/pause", handle_pause_account)
    app.router.add_post("/api/account/pause_all", handle_pause_all)
    app.router.add_post("/api/account/restart", handle_restart_account)
    app.router.add_post("/api/logs/clear", handle_clear_logs)

    # Static files (logo, images)
    if os.path.exists(STATIC_DIR):
        app.router.add_static("/static", STATIC_DIR)
        print(f"\033[92m[+] Static folder: {STATIC_DIR}\033[0m")
    else:
        os.makedirs(STATIC_DIR, exist_ok=True)
        print(f"\033[93m[!] Created static folder: {STATIC_DIR}\033[0m")
        print(f"\033[93m[!] Put your logo.png inside templates/static/\033[0m")

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"\033[92m[+] Web Dashboard: http://localhost:{port}\033[0m")
    print(f"\033[92m[+] Logo path: {os.path.join(STATIC_DIR, 'logo.png')}\033[0m")
