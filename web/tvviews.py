import json
import gevent.hub
import datetime

from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required

from utils.shared import shared_obj, lg, cy, ye, r, n
from utils.mt5_manager import mt5_manager
from . import db
from .models import User, TradingviewTrigger, Trade

tvviews = Blueprint('tvviews', __name__)

_start_time = datetime.datetime.now()


@tvviews.route('/health', methods=['GET'])
def health():
    from .models import Trade
    uptime_seconds = int((datetime.datetime.now() - _start_time).total_seconds())
    hours, rem     = divmod(uptime_seconds, 3600)
    minutes, secs  = divmod(rem, 60)
    total_trades   = Trade.query.count()
    return jsonify({
        "status":       "ok",
        "uptime":       f"{hours}h {minutes}m {secs}s",
        "total_trades": total_trades,
        "timestamp":    datetime.datetime.now().isoformat(),
    }), 200


@tvviews.route('/tvwebhook', methods=['GET', 'POST'])
def tvwebhook():
    shared_obj.logger_global.info(f"{lg}Received raw data: {cy}{request.data}{n}")
    status = 'failed'
    log_string = ''

    # ── Parse JSON ────────────────────────────────────────────────────────────
    try:
        data = json.loads(request.data)
        shared_obj.logger_global.info(f"{lg}Data dict: {cy}{data}{n}")
    except Exception as err:
        shared_obj.logger_global.warning(f"{ye}Invalid JSON from TradingView: {r}{err}{n}")
        return jsonify({"status": "failed", "error": "invalid json"}), 400

    tv_secret     = data.get('secret')
    ticker        = data.get('ticker', '').strip()
    volume        = data.get('volume')
    magic         = data.get('magic')
    alert_message = data.get('alert_message', '').strip().lower()

    # ── Validate required fields ──────────────────────────────────────────────
    if not all([tv_secret, ticker, volume, magic, alert_message]):
        shared_obj.logger_global.warning(
            f"{ye}Missing fields in webhook payload: {r}{data}{n}"
        )
        return jsonify({"status": "failed", "error": "missing required fields"}), 400

    try:
        volume = float(volume)
        magic  = int(magic)
        if volume < 0.01:
            raise ValueError("volume must be >= 0.01")
    except (TypeError, ValueError) as err:
        shared_obj.logger_global.warning(f"{ye}Invalid volume/magic: {r}{err}{n}")
        return jsonify({"status": "failed", "error": str(err)}), 400

    # ── Log trigger ───────────────────────────────────────────────────────────
    trigger = TradingviewTrigger(
        secret=tv_secret,
        ticker=ticker,
        volume=volume,
        magic=magic,
        alert_message=alert_message,
    )
    db.session.add(trigger)
    db.session.commit()

    while True:
        # ── Find user ─────────────────────────────────────────────────────────
        user: User = User.query.filter_by(tv_secret=tv_secret).first()
        if not user:
            log_string = f"User not found for secret: {tv_secret}"
            break

        trigger.user_id = user.id
        db.session.commit()

        # ── Check MT5 connection ──────────────────────────────────────────────
        if not mt5_manager.is_connected(user.id):
            log_string = (
                f"MT5 not connected for user: {user.name}. "
                f"Please configure MT5 credentials in your Profile."
            )
            break

        # ── Parse signal ──────────────────────────────────────────────────────
        is_long  = 'long'  in alert_message
        is_entry = 'entry' in alert_message
        direction   = 'long' if is_long else 'short'
        entry_exit  = 'entry' if is_entry else 'exit'
        parts       = alert_message.split()
        exit_reason = parts[2] if len(parts) > 2 else ''

        shared_obj.logger_global.info(
            f"{lg}Signal — user: {cy}{user.username}{lg}, ticker: {cy}{ticker}{lg}, "
            f"direction: {cy}{direction}{lg}, action: {cy}{entry_exit}{lg}, "
            f"volume: {cy}{volume}{lg}, magic: {cy}{magic}{n}"
        )

        # ── Execute order via MT5 worker (non-blocking gevent threadpool) ──────
        pool = gevent.get_hub().threadpool

        if is_entry:
            result = pool.spawn(
                mt5_manager.place_order,
                user.id, ticker, volume, magic, is_long
            ).get(timeout=35)

            if not result.get('success'):
                log_string = (
                    f"ENTRY order failed for {ticker} — "
                    f"{result.get('error', 'unknown error')}"
                )
                shared_obj.logger_global.warning(f"{ye}{log_string}{n}")
                break

            trade = Trade(
                user_id=user.id,
                tv_trigger_id=trigger.id,
                symbol=ticker,
                direction=direction,
                entry_exit='entry',
                volume=volume,
                magic=magic,
                mt5_ticket=result.get('ticket'),
                entry_price=result.get('price', 0.0),
                exit_price=0.0,
                exit_reason='',
            )
            db.session.add(trade)
            db.session.commit()

            log_string = (
                f"ENTRY order placed — {ticker} {direction.upper()} "
                f"{volume} lots @ {result.get('price')}, ticket={result.get('ticket')}"
            )

        else:
            result = pool.spawn(
                mt5_manager.close_position,
                user.id, ticker, magic
            ).get(timeout=35)

            if not result.get('success'):
                log_string = (
                    f"EXIT order failed for {ticker} magic={magic} — "
                    f"{result.get('error', 'unknown error')}"
                )
                shared_obj.logger_global.warning(f"{ye}{log_string}{n}")
                break

            closed = result.get('closed', [])
            for c in closed:
                trade = Trade(
                    user_id=user.id,
                    tv_trigger_id=trigger.id,
                    symbol=ticker,
                    direction=direction,
                    entry_exit='exit',
                    volume=volume,
                    magic=magic,
                    mt5_ticket=c.get('ticket'),
                    entry_price=0.0,
                    exit_price=c.get('close_price', 0.0),
                    exit_reason=exit_reason,
                )
                db.session.add(trade)
            db.session.commit()

            tickets = [str(c.get('ticket')) for c in closed]
            log_string = (
                f"EXIT order placed — {ticker} magic={magic}, "
                f"closed ticket(s): {', '.join(tickets)}"
            )

        status = 'complete'
        break

    # ── Finalise ──────────────────────────────────────────────────────────────
    if status == 'failed':
        shared_obj.logger_global.warning(f"{ye}{log_string}{n}")
    else:
        shared_obj.logger_global.info(f"{lg}{log_string}{n}")

    trigger.status = status
    db.session.commit()

    return jsonify({"status": "success"}), 200
