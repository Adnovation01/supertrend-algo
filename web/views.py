from flask import Blueprint, render_template, flash, request
from flask_login import login_required, current_user

from utils.shared import shared_obj, lg, cy, ye, r, n
from utils.mt5_manager import mt5_manager
from web import db
from .models import MT5Account, ProfileForm, MT5ApiForm, Trade

views = Blueprint('views', __name__)

MT5_ALERT_TEMPLATE = '''\
{{
  "secret": "{secret}",
  "ticker": "{{{{ticker}}}}",
  "volume": 0.01,
  "magic": 12345,
  "alert_message": "long entry"
}}'''


@views.route('/', methods=['GET', 'POST'])
@login_required
def dashboard():
    webhook_url      = f'{shared_obj.public_url}/tvwebhook'
    message_template = MT5_ALERT_TEMPLATE.format(secret=current_user.tv_secret)
    return render_template(
        'dashboard.html',
        user=current_user,
        webhook_url=webhook_url,
        message_template=message_template,
    )


@views.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    profile_form = ProfileForm()

    if profile_form.validate_on_submit():
        current_user.name  = profile_form.name.data
        current_user.email = profile_form.email.data
        db.session.commit()
        flash('Profile updated.', category='success')

    mt5_form = MT5ApiForm(prefix='mt5')

    if mt5_form.validate_on_submit():
        login    = mt5_form.login.data
        password = mt5_form.password.data
        server   = mt5_form.server.data.strip()
        broker   = mt5_form.broker.data.strip()

        # Create or update MT5Account record
        if not current_user.mt5_account:
            acc = MT5Account(
                user_id=current_user.id,
                login=login,
                password=password,
                server=server,
                broker=broker,
                status='disconnected',
            )
            db.session.add(acc)
        else:
            acc = current_user.mt5_account
            acc.login    = login
            acc.password = password
            acc.server   = server
            acc.broker   = broker
            acc.status   = 'disconnected'

        db.session.commit()

        # Reconnect MT5 worker with new credentials
        success, err = mt5_manager.reconnect_user(
            current_user.id, login, password, server
        )

        if success:
            acc.status = 'connected'
            db.session.commit()
            flash(f'MT5 connected — {broker} ({server})', category='success')
        else:
            acc.status = 'disconnected'
            db.session.commit()
            flash(f'MT5 connection failed: {err}', category='error')

    return render_template(
        'profile.html',
        user=current_user,
        profile_form=profile_form,
        mt5_form=mt5_form,
    )


@views.route('/mt5_reconnect', methods=['GET', 'POST'])
@login_required
def mt5_reconnect():
    profile_form = ProfileForm()
    mt5_form     = MT5ApiForm(prefix='mt5')

    if not current_user.mt5_account:
        flash('No MT5 credentials saved. Please fill in the form below.', category='error')
        return render_template('profile.html', user=current_user,
                               profile_form=profile_form, mt5_form=mt5_form)

    acc = current_user.mt5_account
    success, err = mt5_manager.reconnect_user(
        current_user.id, acc.login, acc.password, acc.server
    )

    if success:
        acc.status = 'connected'
        db.session.commit()
        flash('MT5 reconnected successfully.', category='success')
    else:
        acc.status = 'disconnected'
        db.session.commit()
        flash(f'MT5 reconnect failed: {err}', category='error')

    return render_template(
        'profile.html',
        user=current_user,
        profile_form=profile_form,
        mt5_form=mt5_form,
    )


@views.route('/trades', methods=['GET'])
@login_required
def trades():
    page        = request.args.get('page', 1, type=int)
    symbol      = request.args.get('symbol', '').strip()
    direction   = request.args.get('direction', '').strip()
    entry_exit  = request.args.get('entry_exit', '').strip()

    query = Trade.query.filter_by(user_id=current_user.id)
    if symbol:
        query = query.filter(Trade.symbol.ilike(f'%{symbol}%'))
    if direction:
        query = query.filter(Trade.direction == direction)
    if entry_exit:
        query = query.filter(Trade.entry_exit == entry_exit)

    pagination = query.order_by(Trade.datetime.desc()).paginate(page=page, per_page=25, error_out=False)

    return render_template(
        'trades.html',
        user=current_user,
        pagination=pagination,
        trades=pagination.items,
        symbol=symbol,
        direction=direction,
        entry_exit=entry_exit,
    )


@views.route('/alert_webhook', methods=['POST'])
def alert_webhook():
    return "test"
