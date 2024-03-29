from . import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin,AnonymousUserMixin
from . import login_manager
from flask import current_app
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from datetime import datetime
import hashlib

#Permissions defined as per usage of the app
class Permission:
    USER = 0
    ADMIN = 1

#The insert_roles is used for initial set-up of the roles table with default permission and elevated permissions as defined in the permissions class above
class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    default = db.Column(db.Boolean, default=False, index=True)
    permissions = db.Column(db.Integer)
    users = db.relationship('User', backref='role', lazy='dynamic')

    def __init__(self, **kwargs):
        super(Role, self).__init__(**kwargs)
        if self.permissions is None:
            self.permissions = 0

#used for initial setup of roles tables during db init
    @staticmethod
    def insert_roles():
        roles = {
            'User': [Permission.USER],
            'Administrator': [Permission.ADMIN,Permission.USER],
        }
        default_role = 'User'
        for r in roles:
            role = Role.query.filter_by(name=r).first()
            if role is None:
                role = Role(name=r)
            role.reset_permissions()
            for perm in roles[r]:
                role.add_permission(perm)
            role.default = (role.name == default_role)
            db.session.add(role)
        db.session.commit()

    def add_permission(self, perm):
        if not self.has_permission(perm):
            self.permissions += perm

    def remove_permission(self, perm):
        if self.has_permission(perm):
            self.permissions -= perm

    def reset_permissions(self):
        self.permissions = 0

#checks if the permissions of the user matches with that defined for the role in roles table 
    def has_permission(self, perm):
        return self.permissions == perm

    def __repr__(self):
        return '<Role %r>' % self.name

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))



#User model that has relations defined for orders and cart tables
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(64), unique=True, index=True)
    username = db.Column(db.String(64), unique=True, index=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    password_hash = db.Column(db.String(128))
    confirmed = db.Column(db.Boolean, default=False)
    name = db.Column(db.String(64))
    location = db.Column(db.String(64))
    about_me = db.Column(db.Text())
    member_since = db.Column(db.DateTime(), default=datetime.utcnow)
    last_seen = db.Column(db.DateTime(), default=datetime.utcnow)
    avatar_hash = db.Column(db.String(32))
    cart_id = db.Column(db.Integer)
    item_count = db.Column(db.Integer)
    carts = db.relationship('Cart', backref='User', lazy='dynamic') 
    orders = db.relationship('Order', backref='User', lazy='dynamic') 


#initialization of an user and assignment of role based on the email id. This role contains permissions defined in roles table 
    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if self.role is None:
            if self.email == current_app.config['APP_ADMIN']:
                self.role = Role.query.filter_by(name='Administrator').first()
            if self.role is None:
                self.role = Role.query.filter_by(default=True).first()
        if self.email is not None and self.avatar_hash is None:
            self.avatar_hash = self.gravatar_hash()

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_confirmation_token(self, expiration=3600):
        s = Serializer(current_app.config['SECRET_KEY'], expiration)
        return s.dumps({'confirm': self.id}).decode('utf-8')

    def confirm(self, token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token.encode('utf-8'))
        except:
            return False
        if data.get('confirm') != self.id:
            return False
        self.confirmed = True
        db.session.add(self)
        return True

    def generate_reset_token(self, expiration=3600):
        s = Serializer(current_app.config['SECRET_KEY'], expiration)
        return s.dumps({'reset': self.id}).decode('utf-8')

    @staticmethod
    def reset_password(token, new_password):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token.encode('utf-8'))
        except:
            return False
        user = User.query.get(data.get('reset'))
        if user is None:
            return False
        user.password = new_password
        db.session.add(user)
        return True

    def generate_email_change_token(self, new_email, expiration=3600):
        s = Serializer(current_app.config['SECRET_KEY'], expiration)
        return s.dumps(
            {'change_email': self.id, 'new_email': new_email}).decode('utf-8')

    def change_email(self, token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token.encode('utf-8'))
        except:
            return False
        if data.get('change_email') != self.id:
            return False
        new_email = data.get('new_email')
        if new_email is None:
            return False
        if self.query.filter_by(email=new_email).first() is not None:
            return False
        self.email = new_email
        self.avatar_hash = self.gravatar_hash()
        db.session.add(self)
        return True

    def can(self, perm):
        return self.role is not None and self.role.has_permission(perm)

    def is_administrator(self):
        return self.can(Permission.ADMIN)

    def ping(self):
        self.last_seen = datetime.utcnow()
        db.session.add(self)

    def gravatar_hash(self):
        return hashlib.md5(self.email.lower().encode('utf-8')).hexdigest()

    def gravatar(self, size=100, default='identicon', rating='g'):
        url = 'https://secure.gravatar.com/avatar'
        hash = self.avatar_hash or self.gravatar_hash()
        return '{url}/{hash}?s={size}&d={default}&r={rating}'.format(
            url=url, hash=hash, size=size, default=default, rating=rating)

    def __repr__(self):
        return '<User %r>' % self.username


class AnonymousUser(AnonymousUserMixin):
    def can(self, permissions):
        return False

    def is_administrator(self):
        return False

login_manager.anonymous_user = AnonymousUser


#Cart is used to hold items added to cart
class Cart(db.Model):
    __tablename__ = 'carts'
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    product_id = db.Column(db.Integer)
    quantity = db.Column(db.Integer)
    price = db.Column(db.Float)
    image = db.Column(db.String(64))
    title = db.Column(db.String(64))

#    users = db.relationship('User', backref='cart', lazy='dynamic')
    def __init__(self, _cart_id, _product_id,_quantity,_price,_image,_title):
        self.cart_id = _cart_id
        self.product_id = _product_id
        self.quantity = _quantity
        self.price = _price
        self.image = _image
        self.title = _title
class Product:
    def __init__(self, productId,quantity,price):
        self.productId = productId
        self.quantity = quantity
        self.price = price



#Order model that is used to store orders placed successfully
class Order(db.Model):
    __tablename__ = 'orders'
    order_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    user_name = db.Column(db.String(64))
    address_first = db.Column(db.String(64))
    address_last = db.Column(db.String(64))
    address_zipcode = db.Column(db.String(64))
    address_city = db.Column(db.String(64))
    address_state = db.Column(db.String(64))
    order_cost = db.Column(db.Float)
    item_count = db.Column(db.Integer)
    order_status = db.Column(db.String(64))
    payment_status = db.Column(db.String(64))
    #users = db.relationship('Order', backref='User', lazy='dynamic') #TODO May create issue

    # def __init__(self, **kwargs):
    #     super(Order, self).__init__(**kwargs)

    def __init__(self, user_id,user_name,address_first,address_last,address_zipcode,address_city,address_state,order_cost,item_count,order_status,payment_status):
        #self.order_id = order_id
        self.user_id = user_id
        self.user_name = user_name
        self.address_first = address_first
        self.address_last = address_last
        self.address_zipcode = address_zipcode
        self.address_city = address_city
        self.address_state = address_state
        self.order_cost = order_cost
        self.item_count = item_count
        self.order_status = order_status
        self.payment_status = payment_status

    def __repr__(self):
        return '<Order %r>' % self.order_id
