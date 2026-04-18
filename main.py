import os
import sys
import signal
import pyfiglet

from pyngrok import ngrok
from getpass import getpass
from dotenv import load_dotenv
from gevent.pywsgi import WSGIServer
from geventwebsocket.handler import WebSocketHandler

from utils.shared import shared_obj, lg, cy, ye, r, n, mg, VERSION, handleYorN
from web import app, socketio, APP_PORT, create_app
from web.auth import create_super_user
from utils.mt5_manager import mt5_manager, load_all_users_mt5, load_user_mt5


thread  = None
running = True
server  = WSGIServer(('0.0.0.0', APP_PORT), app, handler_class=WebSocketHandler)


def signal_handler():
    global thread, running
    shared_obj.logger_global.info(f"{lg}Stopping the application gracefully..{n}")
    running = False
    server.stop()
    if thread:
        thread.shutdown(wait=False)
    sys.exit(0)


signal.signal(signal.SIGINT, lambda sig, frame: signal_handler())


def clr():
    if os.name == 'nt':
        os.system('cls')
    else:
        os.system('clear')


def banner(font, width):
    fig    = pyfiglet.Figlet(font=font, width=width)
    output = fig.renderText('SOFTWIRED TECH.')
    shared_obj.logger_global.info(f'{lg}\n{output}\n{n}')
    shared_obj.logger_global.info(f'''{lg}\nVERSION:\t{mg}{VERSION}
{lg}AUTHOR:\t\t{mg}SoftWired Technologies
{lg}WEBSITE:\t{mg}www.softwired.in
{lg}EMAIL:\t\t{mg}softwiredindia@gmail.com
{lg}MOB:\t\t{mg}+91 9039050122, +91 8602122334
{lg}DESCRIPTION:\t{mg}Supertrend Algo — TradingView → MetaTrader 5 execution bridge.
\t\tSupports Forex, Metals, Oils, and Indices across multiple brokers
\t\t(Exness, FundingPips, FundedNext, etc.){n}

''')


def init_console():
    clr()
    banner(font='slant', width=120)


def env_init():
    shared_obj.logger_global.info(f"{lg}Initializing .env variables{n}")
    ENV_FILENAME = '.env'

    if not os.path.isfile(ENV_FILENAME):
        shared_obj.logger_global.info(f'{lg}Running one-time setup..{n}')
        with open(ENV_FILENAME + '.template', 'r') as env_template_file:
            file_text = ""
            for line in env_template_file:
                temp           = line.split('#')
                display_string = temp[1].strip()

                if 'password' in display_string.lower() or 'pin' in display_string.lower():
                    input_string = getpass(f'{cy}Enter {display_string}: {n}')
                else:
                    input_string = input(f'{cy}Enter {display_string}: {n}')

                if '(y/n)' in display_string:
                    file_text += f"{temp[0].strip()}{str(handleYorN(input_string))}\n"
                else:
                    file_text += f"{temp[0].strip()}{input_string}\n"

            if file_text:
                with open(ENV_FILENAME, 'w') as env_file:
                    env_file.write(file_text)

    load_dotenv()


def foreverLoop(name):
    """
    Background task: runs continuously.
    Every 60 seconds checks that each user's MT5 worker process is still alive
    and reconnects it if it has died.
    """
    global running
    socketio.sleep(5)
    load_all_users_mt5(reset=True)

    check_interval = 0
    while running:
        socketio.sleep(1)
        check_interval += 1

        if check_interval >= 60:
            check_interval = 0
            _health_check_all_workers()


def _health_check_all_workers():
    """Reconnect any user whose MT5 worker process has died."""
    from web import app, db
    from web.models import User

    with app.app_context():
        users = User.query.all()
        for user in users:
            if user.mt5_account:
                acc = user.mt5_account
                if not mt5_manager.is_connected(user.id):
                    shared_obj.logger_global.warning(
                        f'{ye}MT5 worker dead for {user.username} — reconnecting..{n}'
                    )
                    success, err = mt5_manager.connect_user(
                        user.id, acc.login, acc.password, acc.server
                    )
                    if success:
                        acc.status = 'connected'
                        shared_obj.logger_global.info(
                            f'{lg}MT5 reconnected: {cy}{user.username}{n}'
                        )
                    else:
                        acc.status = 'disconnected'
                        shared_obj.logger_global.warning(
                            f'{ye}MT5 reconnect failed for {user.username}: {err}{n}'
                        )
                    db.session.commit()


def bg_task_setup():
    global thread
    from concurrent.futures import ThreadPoolExecutor
    thread = ThreadPoolExecutor()
    thread.submit(foreverLoop, 'foreverLoop')


def init():
    init_console()
    env_init()
    create_app(load_user_mt5)
    create_super_user()
    shared_obj.logger_global.info(
        f'{lg}NOTE: Delete instance/database.db if upgrading from the Dhan version.{n}'
    )


def open_browser():
    host    = os.getenv("PUBLIC_HOST", "138.252.201.204")
    app_url = f'http://{host}'
    shared_obj.logger_global.info(f"{lg}Running on {ye}{app_url}{n}")

    try:
        if os.getenv("NGROK_ENABLED") == '1':
            public_url            = ngrok.connect(APP_PORT)
            shared_obj.public_url = public_url.public_url
            shared_obj.logger_global.info(
                f"{lg}NGROK tunnel URL: {ye}{shared_obj.public_url}{n}"
            )
        else:
            shared_obj.public_url = app_url
            shared_obj.logger_global.warning(f'{ye}NGROK_ENABLED = False{n}')
    except Exception as err:
        shared_obj.logger_global.warning(f'{ye}NGROK setup failed: {err}{n}')
        shared_obj.public_url = app_url


def main():
    init()
    bg_task_setup()
    open_browser()
    server.serve_forever()


if __name__ == '__main__':
    main()
