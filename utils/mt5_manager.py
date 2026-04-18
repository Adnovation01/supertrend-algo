import queue
import multiprocessing

from utils.shared import shared_obj, lg, cy, ye, r, n


class MT5Worker(multiprocessing.Process):
    """
    A dedicated OS process that owns one MT5 terminal connection for a single user.
    Receives trade commands via cmd_queue and returns results via result_queue.
    Running in a separate process allows true parallel execution across users.
    """

    def __init__(self, user_id, login, password, server):
        super().__init__(daemon=True)
        self.user_id = user_id
        self.login = login
        self.password = password
        self.server = server
        self.cmd_queue = multiprocessing.Queue()
        self.result_queue = multiprocessing.Queue()
        self.connected = multiprocessing.Event()
        self.connection_error = multiprocessing.Value('b', 0)

    def run(self):
        # MetaTrader5 must be imported inside the subprocess
        import MetaTrader5 as mt5

        if not mt5.initialize():
            err = mt5.last_error()
            print(f"MT5 initialize failed for user {self.user_id}: {err}")
            self.connection_error.value = 1
            self.connected.set()
            return

        if not mt5.login(self.login, password=self.password, server=self.server):
            err = mt5.last_error()
            print(f"MT5 login failed for user {self.user_id}: {err}")
            self.connection_error.value = 1
            self.connected.set()
            mt5.shutdown()
            return

        self.connected.set()

        try:
            while True:
                try:
                    cmd = self.cmd_queue.get(timeout=60)
                except queue.Empty:
                    # Keepalive check
                    if mt5.terminal_info() is None:
                        # Lost connection — try to re-initialize
                        mt5.shutdown()
                        if mt5.initialize():
                            mt5.login(self.login, password=self.password, server=self.server)
                    continue

                cmd_type = cmd.get('type')

                if cmd_type == 'STOP':
                    break
                elif cmd_type == 'PLACE_ORDER':
                    result = self._place_order(mt5, cmd)
                    self.result_queue.put(result)
                elif cmd_type == 'CLOSE_POSITION':
                    result = self._close_position(mt5, cmd)
                    self.result_queue.put(result)
                else:
                    self.result_queue.put({'success': False, 'error': f'Unknown command: {cmd_type}'})
        finally:
            mt5.shutdown()

    def _place_order(self, mt5, cmd):
        symbol = cmd['symbol']
        volume = float(cmd['volume'])
        magic = int(cmd['magic'])
        is_long = cmd['is_long']

        # Ensure symbol is visible in Market Watch
        if not mt5.symbol_select(symbol, True):
            return {'success': False, 'error': f'Symbol {symbol} not found or not selectable', 'ticket': None}

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {'success': False, 'error': f'No tick data for {symbol}', 'ticket': None}

        sym_info = mt5.symbol_info(symbol)
        if sym_info is None:
            return {'success': False, 'error': f'No symbol info for {symbol}', 'ticket': None}

        price = tick.ask if is_long else tick.bid
        order_type = mt5.ORDER_TYPE_BUY if is_long else mt5.ORDER_TYPE_SELL

        # Determine filling mode supported by the broker/symbol
        filling_mode = sym_info.filling_mode
        if filling_mode & mt5.ORDER_FILLING_IOC:
            type_filling = mt5.ORDER_FILLING_IOC
        elif filling_mode & mt5.ORDER_FILLING_FOK:
            type_filling = mt5.ORDER_FILLING_FOK
        else:
            type_filling = mt5.ORDER_FILLING_RETURN

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": 20,
            "magic": magic,
            "comment": "TV signal",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": type_filling,
        }

        result = mt5.order_send(request)

        if result is None:
            return {'success': False, 'error': f'order_send returned None: {mt5.last_error()}', 'ticket': None}

        success = result.retcode == mt5.TRADE_RETCODE_DONE
        return {
            'success': success,
            'ticket': result.order,
            'retcode': result.retcode,
            'comment': result.comment,
            'price': result.price,
            'error': '' if success else f'retcode={result.retcode} {result.comment}',
        }

    def _close_position(self, mt5, cmd):
        symbol = cmd['symbol']
        magic = int(cmd['magic'])

        positions = mt5.positions_get(symbol=symbol)
        if positions is None:
            return {'success': False, 'error': f'positions_get failed: {mt5.last_error()}', 'closed': []}

        target_positions = [p for p in positions if p.magic == magic]

        if not target_positions:
            return {
                'success': False,
                'error': f'No open position with magic={magic} on {symbol}',
                'closed': [],
            }

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {'success': False, 'error': f'No tick data for {symbol}', 'closed': []}

        sym_info = mt5.symbol_info(symbol)
        filling_mode = sym_info.filling_mode if sym_info else 0
        if filling_mode & mt5.ORDER_FILLING_IOC:
            type_filling = mt5.ORDER_FILLING_IOC
        elif filling_mode & mt5.ORDER_FILLING_FOK:
            type_filling = mt5.ORDER_FILLING_FOK
        else:
            type_filling = mt5.ORDER_FILLING_RETURN

        closed = []
        for pos in target_positions:
            # Close by placing an opposite order referencing pos.ticket
            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": pos.volume,
                "type": close_type,
                "position": pos.ticket,
                "price": price,
                "deviation": 20,
                "magic": magic,
                "comment": "TV exit",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": type_filling,
            }

            result = mt5.order_send(request)
            success = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
            closed.append({
                'ticket': pos.ticket,
                'success': success,
                'retcode': result.retcode if result else None,
                'comment': result.comment if result else 'order_send returned None',
                'close_price': result.price if result else None,
            })

        all_ok = all(c['success'] for c in closed)
        return {'success': all_ok, 'closed': closed, 'error': '' if all_ok else 'One or more closes failed'}


class MT5Manager:
    """
    Manages a pool of MT5Worker processes — one per connected user.
    Provides thread-safe order placement and position closing.
    """

    def __init__(self):
        # user_id -> {'process': MT5Worker, 'cmd_queue': Queue, 'result_queue': Queue}
        self.workers: dict = {}

    def connect_user(self, user_id, login, password, server):
        """
        Spawn (or reuse) a worker process for this user and wait for it to connect.
        Returns (success: bool, error: str).
        """
        existing = self.workers.get(user_id)
        if existing and existing['process'].is_alive():
            return True, ''

        worker = MT5Worker(user_id, int(login), password, server)
        worker.start()

        # Wait up to 15 seconds for MT5 login to complete
        connected = worker.connected.wait(timeout=15)

        if not connected:
            worker.terminate()
            return False, 'MT5 connection timed out after 15 seconds'

        if worker.connection_error.value:
            worker.terminate()
            return False, f'MT5 login failed — check account number, password, and server name'

        self.workers[user_id] = {
            'process': worker,
            'cmd_queue': worker.cmd_queue,
            'result_queue': worker.result_queue,
        }
        return True, ''

    def place_order(self, user_id, symbol, volume, magic, is_long):
        """Send a PLACE_ORDER command to the user's worker and return the result."""
        worker_info = self.workers.get(user_id)
        if not worker_info:
            return {'success': False, 'error': 'MT5 not connected for this user', 'ticket': None}

        worker_info['cmd_queue'].put({
            'type': 'PLACE_ORDER',
            'symbol': symbol,
            'volume': volume,
            'magic': magic,
            'is_long': is_long,
        })

        try:
            result = worker_info['result_queue'].get(timeout=30)
        except queue.Empty:
            return {'success': False, 'error': 'MT5 order timed out after 30 seconds', 'ticket': None}

        return result

    def close_position(self, user_id, symbol, magic):
        """Send a CLOSE_POSITION command to the user's worker and return the result."""
        worker_info = self.workers.get(user_id)
        if not worker_info:
            return {'success': False, 'error': 'MT5 not connected for this user', 'closed': []}

        worker_info['cmd_queue'].put({
            'type': 'CLOSE_POSITION',
            'symbol': symbol,
            'magic': magic,
        })

        try:
            result = worker_info['result_queue'].get(timeout=30)
        except queue.Empty:
            return {'success': False, 'error': 'MT5 close timed out after 30 seconds', 'closed': []}

        return result

    def disconnect_user(self, user_id):
        """Gracefully stop a user's worker process."""
        worker_info = self.workers.pop(user_id, None)
        if worker_info:
            try:
                worker_info['cmd_queue'].put({'type': 'STOP'})
                worker_info['process'].join(timeout=5)
            except Exception:
                pass
            if worker_info['process'].is_alive():
                worker_info['process'].terminate()

    def is_connected(self, user_id):
        """Return True if the user has a live worker process."""
        worker_info = self.workers.get(user_id)
        return worker_info is not None and worker_info['process'].is_alive()

    def reconnect_user(self, user_id, login, password, server):
        """Disconnect then reconnect a user's MT5 worker."""
        self.disconnect_user(user_id)
        return self.connect_user(user_id, login, password, server)


# Module-level singleton — imported everywhere
mt5_manager = MT5Manager()


def load_user_mt5(user_id):
    """
    Called by Flask's user_loader on every request.
    Connects the user's MT5 worker if not already connected.
    """
    from web import db
    from web.models import User

    user = db.session.get(User, int(user_id))
    if user and user.mt5_account and not mt5_manager.is_connected(user.id):
        acc = user.mt5_account
        success, err = mt5_manager.connect_user(
            user.id, acc.login, acc.password, acc.server
        )
        if success:
            acc.status = 'connected'
        else:
            acc.status = 'disconnected'
            shared_obj.logger_global.warning(
                f'{ye}MT5 auto-connect failed for {user.username}: {err}{n}'
            )
        db.session.commit()

    return user


def load_all_users_mt5(reset=False):
    """Connect all users with saved MT5 credentials at startup."""
    from web import app, db
    from web.models import User

    with app.app_context():
        users = User.query.all()
        for user in users:
            if user.mt5_account:
                acc = user.mt5_account
                if reset or not mt5_manager.is_connected(user.id):
                    success, err = mt5_manager.connect_user(
                        user.id, acc.login, acc.password, acc.server
                    )
                    if success:
                        acc.status = 'connected'
                        shared_obj.logger_global.info(
                            f'{lg}MT5 connected: {cy}{user.username}{lg} on {cy}{acc.server}{n}'
                        )
                    else:
                        acc.status = 'disconnected'
                        shared_obj.logger_global.warning(
                            f'{ye}MT5 connect failed for {user.username}: {err}{n}'
                        )
        db.session.commit()
