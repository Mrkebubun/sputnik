from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy

from wtforms import validators

from flask.ext import admin
from flask.ext.admin.contrib import sqla
from flask.ext.admin.contrib.sqla import filters

# Create application
app = Flask(__name__)

# Create dummy secrey key so we can use sessions
app.config['SECRET_KEY'] = '123456790'

# Create in-memory database
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://penny:arcade@localhost/test'
app.config['SQLALCHEMY_ECHO'] = True
db = SQLAlchemy(app)


# Create models
class User(db.Model):
	users = Table('users', metadata, autoload=True)
	mapper(User, users)





class UserInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    key = db.Column(db.String(64), nullable=False)
    value = db.Column(db.String(64))

    user_id = db.Column(db.Integer(), db.ForeignKey(User.id))
    user = db.relationship(User, backref='info')

    def __str__(self):
        return '%s - %s' % (self.key, self.value)


# Flask views
@app.route('/')
def index():
    return '<a href="/admin/">Click me to get to Admin!</a>'


# Customized User model admin
class UserAdmin(sqla.ModelView):
    inline_models = (UserInfo,)


if __name__ == '__main__':
    # Create admin
    admin = admin.Admin(app, 'Testing')

    # Add views
    admin.add_view(UserAdmin(User, db.session))
    # Create DB
    db.create_all()

    # Start app
    app.run(host='0.0.0.0')
