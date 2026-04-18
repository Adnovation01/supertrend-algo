import os
from flask import Blueprint, render_template, flash, redirect, url_for
from flask_login import login_user, login_required, logout_user, current_user
from .models import LoginForm, RegisterForm, User
from . import db, bcrypt, app
from utils.shared import *

auth = Blueprint('auth', __name__)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user:
            if bcrypt.check_password_hash(user.password, form.password.data):
                login_user(user)
                flash('Login Successful.', category='success')
                return redirect(url_for('views.dashboard'))
            else:
                flash('Wrong Username or Password.', category='error')
        else:
            flash('Username does not exist.', category='error')

    return render_template('login.html', form=form, user=current_user)


@auth.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()

    if form.validate_on_submit():
        if form.secretKey.data != os.getenv("REGISTER_SECRETKEY"):
            flash('Invalid Secret Key. Registration not allowed!', category='error')
        else:
            hashed_password = bcrypt.generate_password_hash(form.password.data)
            while True:
                tv_secret = generate_alphanumeric_secret()
                existing_user = User.query.filter_by(
                    tv_secret=tv_secret).first()
                if not existing_user:
                    break
            new_user = User(username=form.username.data, role='user',
                            name=form.name.data, password=hashed_password, tv_secret=tv_secret)
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! You can now log in.', category='success')
            return redirect(url_for('auth.login'))

    return render_template('register.html', form=form, user=current_user)


def create_super_user():
    with app.app_context():
        if not User.query.all():
            hashed_password = bcrypt.generate_password_hash(
                os.getenv("SUPERUSER_PASSWORD"))
            tv_secret = generate_alphanumeric_secret()
            new_user = User(username=os.getenv("SUPERUSER_USERNAME"), role='super_user', name=os.getenv(
                "SUPERUSER_NAME"), password=hashed_password, tv_secret=tv_secret)
            db.session.add(new_user)
            db.session.commit()

            shared_obj.logger_global.info(f'{lg}Superuser created.{n}')
