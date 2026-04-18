from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_socketio import SocketIO
from flask_login import LoginManager

app           = Flask(__name__)
db            = SQLAlchemy()
bcrypt        = Bcrypt()
socketio      = SocketIO(app)
login_manager = LoginManager()

APP_PORT = 80


def create_app(load_user_mt5):
    import os
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'xK9#mP2$vL7@nQ4&')
    async_mode = 'gevent'
    CORS(app, origins="*")

    from .auth import auth
    from .views import views
    from .tvviews import tvviews

    app.register_blueprint(auth, url_prefix='/')
    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(tvviews, url_prefix='/')

    db.init_app(app)
    bcrypt.init_app(app)
    socketio.init_app(app, async_mode=async_mode,
                      cors_allowed_origins="*", transports=['websocket'])

    create_database()

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return load_user_mt5(user_id)

    return app


def create_database():
    with app.app_context():
        db.create_all()
