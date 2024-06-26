from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
import os

app = Flask(__name__)

app_package_path = os.path.join(os.getcwd(), 'app')
app.config['SECRET_KEY'] = 'secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app_package_path, 'site.db')
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'

AUTHORIZED_USERNAMES = ['Cucu Raul']

db = SQLAlchemy(app)
migrate = Migrate(app, db)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('EMAIL_USER')
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASS')
app.config['TESTING'] = False
app.config['CHATBOT_KEY'] = os.environ.get('CHATBOT_KEY')
mail = Mail(app)

from app import routes
