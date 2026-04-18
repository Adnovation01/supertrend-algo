from flask import flash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, EmailField, IntegerField
from wtforms.validators import InputRequired, Length, ValidationError, NumberRange
from flask_login import UserMixin
from datetime import datetime

from . import db


class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id         = db.Column(db.Integer, primary_key=True)
    username   = db.Column(db.String(20), nullable=False, unique=True)
    name       = db.Column(db.String(80), nullable=False)
    email      = db.Column(db.String(80), nullable=True)
    password   = db.Column(db.String(80), nullable=False)
    role       = db.Column(db.String(20), nullable=False)
    tv_secret  = db.Column(db.String(12), nullable=True)

    mt5_account  = db.relationship('MT5Account', back_populates='user', uselist=False)
    tv_triggers  = db.relationship('TradingviewTrigger', back_populates='user')
    trades       = db.relationship('Trade', back_populates='user')


class MT5Account(db.Model):
    __tablename__ = 'mt5_accounts'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    login      = db.Column(db.Integer, nullable=True)          # MT5 account number
    password   = db.Column(db.String(100), nullable=True)      # MT5 password
    server     = db.Column(db.String(100), nullable=True)      # e.g. "Exness-MT5Real8"
    broker     = db.Column(db.String(50), nullable=True)       # e.g. "Exness"
    status     = db.Column(db.String(20), nullable=False, default='disconnected')

    user = db.relationship('User', back_populates='mt5_account')


class TradingviewTrigger(db.Model):
    __tablename__ = 'tradingview_triggers'

    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    secret        = db.Column(db.String(12), nullable=False)
    ticker        = db.Column(db.String(30), nullable=False)
    trigger_price = db.Column(db.Float, nullable=True)
    volume        = db.Column(db.Float, nullable=False)          # lot size e.g. 0.01
    magic         = db.Column(db.Integer, nullable=True)         # MT5 magic number
    alert_message = db.Column(db.String(80), nullable=False)
    status        = db.Column(db.String(20), nullable=False, default='received')
    datetime      = db.Column(db.DateTime, nullable=False, default=datetime.now)

    user  = db.relationship('User', back_populates='tv_triggers')
    trade = db.relationship('Trade', back_populates='tv_trigger', uselist=False)


class Trade(db.Model):
    __tablename__ = 'trades'

    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    tv_trigger_id = db.Column(db.Integer, db.ForeignKey('tradingview_triggers.id'), nullable=True)
    symbol        = db.Column(db.String(30), nullable=True)     # e.g. "XAUUSD"
    direction     = db.Column(db.String(10), nullable=True)     # "long" or "short"
    entry_exit    = db.Column(db.String(10), nullable=True)     # "entry" or "exit"
    volume        = db.Column(db.Float, nullable=True)          # lot size
    magic         = db.Column(db.Integer, nullable=True)        # MT5 magic number
    mt5_ticket    = db.Column(db.Integer, nullable=True)        # MT5 order ticket
    entry_price   = db.Column(db.Float, nullable=True)
    exit_price    = db.Column(db.Float, nullable=True)
    exit_reason   = db.Column(db.String(50), nullable=True)
    datetime      = db.Column(db.DateTime, nullable=False, default=datetime.now)

    user       = db.relationship('User', back_populates='trades')
    tv_trigger = db.relationship('TradingviewTrigger', back_populates='trade')


# ── Forms ─────────────────────────────────────────────────────────────────────

class LoginForm(FlaskForm):
    username = StringField(validators=[InputRequired(), Length(min=4, max=20)],
                           render_kw={"placeholder": "Username"})
    password = PasswordField(validators=[InputRequired(), Length(min=8, max=20)],
                             render_kw={"placeholder": "Password"})
    submit   = SubmitField('Login')


class RegisterForm(FlaskForm):
    username  = StringField('Username', validators=[InputRequired(), Length(min=4, max=20)],
                            render_kw={"placeholder": "Username"})
    name      = StringField('Name', validators=[InputRequired(), Length(min=4, max=80)],
                            render_kw={"placeholder": "Name"})
    password  = PasswordField('Password', validators=[InputRequired(), Length(min=8, max=20)],
                              render_kw={"placeholder": "Password"})
    secretKey = StringField('Secret Key', validators=[InputRequired(), Length(min=8, max=20)],
                            render_kw={"placeholder": "Secret Key"})
    submit    = SubmitField('Register')

    def validate_username(self, username):
        existing_user_username = User.query.filter_by(username=username.data).first()
        if existing_user_username:
            flash('That username already exists. Please choose a different one.', category='error')
            raise ValidationError('That username already exists. Please choose a different one.')


class ProfileForm(FlaskForm):
    name   = StringField("Name", validators=[InputRequired(), Length(min=4, max=80)])
    email  = EmailField("Email ID")
    submit = SubmitField('Save')


class MT5ApiForm(FlaskForm):
    login    = IntegerField("MT5 Account Number",
                            validators=[InputRequired(), NumberRange(min=1)])
    password = PasswordField("MT5 Password",
                             validators=[InputRequired(), Length(min=1, max=100)])
    server   = StringField("MT5 Server (e.g. Exness-MT5Real8)",
                           validators=[InputRequired(), Length(min=1, max=100)])
    broker   = StringField("Broker Name (e.g. Exness)",
                           validators=[InputRequired(), Length(min=1, max=50)])
    submit   = SubmitField('Connect')
