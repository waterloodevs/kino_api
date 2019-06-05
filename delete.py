import requests
import json
import psycopg2
import psycopg2.extras
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, abort, g, Response
from flask import jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSON
import firebase_admin
from firebase_admin import credentials, auth, messaging
from flask_httpauth import HTTPTokenAuth
from flask_ngrok import run_with_ngrok

http_auth = HTTPTokenAuth(scheme='Token')

cred = credentials.Certificate('kino-extension-firebase-adminsdk-mrn7d-cca5ca5e4c.json')
default_app = firebase_admin.initialize_app(cred)

DATABASE_URL = 'postgresql://postgres:postgres@localhost:5432/postgres'


app = Flask(__name__)
run_with_ngrok(app)
db = SQLAlchemy(app)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
SSL_mode = 'allow'

AFFILIATE_LINKS = {
    "www.berrylook.com": "https://click.linksynergy.com/deeplink?id=fw7GSdQ4wUE&mid=44303&murl=https%3A%2F%2Fwww.berrylook.com%2F",
    "www.bloomstoday.com": "https://click.linksynergy.com/deeplink?id=fw7GSdQ4wUE&mid=44085&murl=http%3A%2F%2Fwww.bloomstoday.com",
    "www.cheapoair.ca": "https://click.linksynergy.com/deeplink?id=fw7GSdQ4wUE&mid=37732&murl=https%3A%2F%2Fwww.cheapoair.ca%2F",
    "www.josbank.com": "https://click.linksynergy.com/deeplink?id=fw7GSdQ4wUE&mid=38377&murl=http%3A%2F%2Fwww.josbank.com",
    "www.shop.lego.com": "https://click.linksynergy.com/deeplink?id=fw7GSdQ4wUE&mid=13923&murl=http%3A%2F%2Fshop.lego.com",
    "www.macys.com": "https://click.linksynergy.com/deeplink?id=fw7GSdQ4wUE&mid=3184&murl=http%3A%2F%2Fwww.macys.com",
    "www.microsoft.com": "https://click.linksynergy.com/deeplink?id=fw7GSdQ4wUE&mid=24542&murl=http%3A%2F%2Fwww.microsoft.com"
}

EARN_PRICE_PER_DOLLAR = 100
SPEND_PRICE_PER_DOLLAR = 10000

GIFTCARD_TYPES = ['Amazon']
GIFTCARD_AMOUNTS = [5, 10, 25]
MAX_GIFTCARD_QUANTITY = 10
MIN_GIFTCARD_QUANTITY = 1


class User(db.Model):

    __tablename__ = "users"

    uid = db.Column(db.String, primary_key=True, nullable=False)
    email = db.Column(db.String, unique=True, nullable=False)
    balance = db.Column(db.Integer, nullable=False)
    transactions = db.Column(JSON, nullable=False)
    android_fcm_token = db.Column(db.String)
    web_fcm_token = db.Column(db.String)
    public_address = db.Column(db.String)

    def __init__(self, uid, email, balance=0, transactions=None,
                 android_fcm_token=None, web_fcm_token=None, public_address=None):
        self.uid = uid
        self.email = email
        self.balance = balance
        self.transactions = transactions
        self.android_fcm_token = android_fcm_token
        self.web_fcm_token = web_fcm_token
        self.public_address = public_address

    def __repr__(self):
        return "email: {}, balance: {}"\
            .format(self.email, self.balance)


def fetch_access_token():
    request_token = "OGZiY0JCR0o3Zmh1RGg3MFh0OTQyeVRZU0JRYTp1VHhvREZfZGNxMTBnZENGX0NmenJNNlB0REVh"
    response = requests.post(
        "https://api.rakutenmarketing.com/token",
        headers={"Authorization": "Basic " + request_token},
        data={
            "grant_type": "password",
            "username": "jeevansidhu",
            "password": "ballislife99",
            "scope": "3612359"
        }
    )
    access_token = response.json()['access_token']
    return access_token


def fetch_transactions(access_token):
    start_date = datetime.utcnow()
    start_date -= timedelta(days=25)
    start_date = start_date.strftime("%Y-%m-%d %H:%M:%S")
    response = requests.get(
        "https://api.rakutenmarketing.com/events/1.0/transactions",
        headers={
            "Accept": "text/json",
            "Authorization": "Bearer " + access_token
        },
        params={"transaction_date_start=": start_date}
    )
    transactions = response.json()
    return transactions


def process_transaction(transaction):
    u1 = transaction["u1"]
    user = User.query.filter_by(uid=u1).first()
    email_kino(user, earn_transaction=transaction)
    sale_amount = transaction["sale_amount"]
    kin_amount = calc_kin_payout_amount(sale_amount)
    # Update user's balance in db
    user.balance += kin_amount
    # Update user's transactions in db
    if user.transactions:
        temp = user.transactions
        temp = temp.copy()
        temp.update({transaction["etransaction_id"]: transaction})
        user.transactions = temp
    else:
        user.transactions = {transaction["etransaction_id"]: transaction}
    try:
        db.session.commit()
    except AssertionError as err:
        db.session.rollback()
    if user.public_address:
        # Build earn transaction based on user's public address if present
        pay(user, kin_amount)
    try:
        notify_app(user, kin_amount, transaction['product_name'])
    except:
        pass
    try:
        notify_extension(user, kin_amount, transaction['product_name'])
    except:
        pass


def calc_kin_payout_amount(dollar_amount):
    amount = dollar_amount * EARN_PRICE_PER_DOLLAR
    return min(amount, 50000)


def pay(user, kin_amount):
    return


def notify_extension(user, kin_amount, product_name):
    message = messaging.Message(
        data={
            'title': "Kino",
            'body': "You just earned {} Kin for your purchase of {}.".format(kin_amount, product_name)
        },
        token=user.web_fcm_token,
    )
    try:
        response = messaging.send(message)
    except Exception as err:
        raise err
    return


def notify_app(user, kin_amount, product_name):
    # See documentation on defining a message payload.
    message = messaging.Message(
        data={
            'title': "Kino",
            'body': "You just earned {} Kin for your purchase of {}.".format(kin_amount, product_name)
        },
        token=user.android_fcm_token,
    )
    # Send a message to the device corresponding to the provided registration token.
    try:
        response = messaging.send(message)
    except Exception as err:
        raise err
    return


def email_kino(user, earn_transaction=None, spend_transaction=None):
    msg = EmailMessage()
    msg.set_content(str(vars(user)) + "\n" + str(earn_transaction) + "\n" + str(spend_transaction))
    if earn_transaction:
        msg['Subject'] = "Earn Transaction"
    if spend_transaction:
        msg['Subject'] = "Buy Transaction"
    msg['From'] = "waterloodevs@gmail.com"
    msg['To'] = "waterloodevs@gmail.com"
    s = smtplib.SMTP('smtp.gmail.com:587')
    s.ehlo()
    s.starttls()
    s.login("waterloodevs@gmail.com", "ballislife99.")
    s.send_message(msg)
    s.quit()


y = {
    "etransaction_id": "hell oth this is jeevan tra",
    "advertiser_id": 1111,
    "sid": 22222,
    "order_id": "333333333",
    "member_id": "444444",
    "sku_number": "5555555",
    "sale_amount": 10,
    "quantity": 1,
    "commissions": 0,
    "process_date": "Wed Apr 30 2014 03:07:13 GMT+0000 (UTC)",
    "transaction_date": "Wed Apr 30 2014 03:07:00 GMT+0000 (UTC)",
    "transaction_type": "realtime",
    "product_name": "Something really fancy",
    "u1": "2JwiP18UnubcWlAAgElFWYR3vKU2",
    "currency": "USD",
    "is_event": "Y"
}
access_token = fetch_access_token()
transactions = fetch_transactions(access_token)
transactions = [y]
for transaction in transactions:
    process_transaction(transaction)



