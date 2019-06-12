import asyncio
import kin
import smtplib
import psycopg2
from email.message import EmailMessage
from flask import Flask, render_template, request, redirect, url_for, abort, g, Response
from flask import jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSON
import firebase_admin
from firebase_admin import credentials, auth, messaging
from flask_httpauth import HTTPTokenAuth
import gunicorn


cred = credentials.Certificate('kino-extension-firebase-adminsdk-mrn7d-cca5ca5e4c.json')
default_app = firebase_admin.initialize_app(cred)
http_auth = HTTPTokenAuth(scheme='Token')
kin_env = kin.TEST_ENVIRONMENT
app_id = '9999'
kino_seed = ''
kino_public_address = ''
database_url = 'postgres://aueqysferuszbo:8eb6155fc340e1de1b38ce4eac1aa190f15bbc527ee52ce389612b1bde6d14b6@ec2-107-22-238-217.compute-1.amazonaws.com:5432/ddrnuulbba6300'


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


affiliate_links = {
        "www.berrylook.com": "https://click.linksynergy.com/deeplink?id=fw7GSdQ4wUE&mid=44303&murl=https%3A%2F%2Fwww.berrylook.com%2F",
        "www.bloomstoday.com": "https://click.linksynergy.com/deeplink?id=fw7GSdQ4wUE&mid=44085&murl=http%3A%2F%2Fwww.bloomstoday.com",
        "www.cheapoair.ca": "https://click.linksynergy.com/deeplink?id=fw7GSdQ4wUE&mid=37732&murl=https%3A%2F%2Fwww.cheapoair.ca%2F",
        "www.josbank.com": "https://click.linksynergy.com/deeplink?id=fw7GSdQ4wUE&mid=38377&murl=http%3A%2F%2Fwww.josbank.com",
        "www.shop.lego.com": "https://click.linksynergy.com/deeplink?id=fw7GSdQ4wUE&mid=13923&murl=http%3A%2F%2Fshop.lego.com",
        "www.macys.com": "https://click.linksynergy.com/deeplink?id=fw7GSdQ4wUE&mid=3184&murl=http%3A%2F%2Fwww.macys.com",
        "www.microsoft.com": "https://click.linksynergy.com/deeplink?id=fw7GSdQ4wUE&mid=24542&murl=http%3A%2F%2Fwww.microsoft.com"
}


class User(db.Model):

    __tablename__ = "users"

    uid = db.Column(db.String, primary_key=True, nullable=False)
    email = db.Column(db.String, unique=True, nullable=False)
    balance = db.Column(db.Integer, nullable=False)
    transactions = db.Column(JSON, nullable=False)
    web_fcm_token = db.Column(db.String)
    android_fcm_token = db.Column(db.String)
    public_address = db.Column(db.String)

    def __init__(self, uid, email, balance=0, transactions=[],
                 android_fcm_token=None, web_fcm_token=None, public_address=None):
        self.uid = uid
        self.email = email
        self.balance = balance
        self.transactions = transactions
        self.web_fcm_token = web_fcm_token
        self.android_fcm_token = android_fcm_token
        self.public_address = public_address


# Using this to verify authenticated calls where login is required
@http_auth.verify_token
def verify_token(fb_id_token):
    try:
        decoded_token = auth.verify_id_token(fb_id_token)
        g.uid = decoded_token['uid']
    except Exception as err:
        return False
    return True


def get_database_connection():
    conn = psycopg2.connect(database_url, sslmode='allow')
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    return conn, cur


async def init_kin():
    client = kin.KinClient(kin_env)
    account = client.kin_account(kino_seed, app_id=app_id)
    return client, account


@app.route('/register', methods=['POST'])
@http_auth.login_required
def register():
    conn, cur = get_database_connection()
    try:
        email = str(auth.get_user(g.uid).email)
        user = User(uid=g.uid, email=email)
        cur.execute(
            """
            INSERT into \"users\" 
                (uid, email, balance, transactions, web_fcm_token, android_fcm_token, public_address)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s)
            """,
            [user.uid, user.email, user.balance, user.transactions,
             user.web_fcm_token, user.android_fcm_token, user.public_address]
        )
        conn.commit()
        return jsonify(), 201
    except:
        return jsonify(), 500
    finally:
        cur.close()
        conn.close()


@app.route('/update_fcm_token', methods=['POST'])
@http_auth.login_required
def update_fcm_token():
    conn, cur = get_database_connection()
    try:
        if 'web_fcm_token' in request.json:
            web_fcm_token = request.json['web_fcm_token']
            cur.execute(
                """
                UPDATE \"users\" 
                SET
                    web_fcm_token = %s
                WHERE   
                    uid = %s
                """,
                [web_fcm_token, g.uid]
            )
            conn.commit()
        elif 'android_fcm_token' in request.json:
            android_fcm_token = request.json['android_fcm_token']
            cur.execute(
                """
                UPDATE \"users\" 
                SET
                    android_fcm_token = %s
                WHERE   
                    uid = %s
                """,
                [android_fcm_token, g.uid]
            )
            conn.commit()
        else:
            return jsonify(), 500
        return jsonify(), 201
    except:
        return jsonify(), 500
    finally:
        cur.close()
        conn.close()


async def onboard_account_async(json):
    conn, cur = get_database_connection()
    client, account = await init_kin()
    try:
        public_address = json['public_address']
        cur.execute(
            """
            SELECT
                *
            FROM
                \"users\"
            WHERE
                uid = %s
            """,
            [g.uid]
        )
        user = cur.fetchone()
        account = client.kin_account(kino_seed, app_id=app_id)
        fee = await client.get_minimum_fee()
        tx_hash = await account.create_account(public_address, 100, fee=fee, memo_text='create account')
        first_time = True
        if user['public_address']:
            first_time = False
        cur.execute(
            """
            UPDATE \"users\" 
            SET
                public_address = %s
            WHERE   
                uid = %s
            """,
            [public_address, g.uid]
        )
        conn.commit()
        # First time installing the app and balance is not 0, create a earn transaction for the user's balance
        if first_time and user['balance'] != 0:
            fee = await client.get_minimum_fee()
            tx_hash = await account.send_kin(user['public_address'], user['balance'], fee=fee, memo_text='balance')
        return jsonify(), 201
    except:
        return jsonify(), 500
    finally:
        cur.close()
        conn.close()
        await client.close()


@app.route('/onboard_account', methods=['POST'])
@http_auth.login_required
def onboard_account():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(onboard_account_async(request.get_json()))
    return response


@app.route('/stores', methods=['GET'])
@http_auth.login_required
def stores():
    return jsonify({"stores": list(affiliate_links.keys())}), 200


@app.route('/affiliate_link/<url>', methods=['GET'])
@http_auth.login_required
def affiliate_link(url):
    conn, cur = get_database_connection()
    try:
        cur.execute(
            """
            SELECT
                *
            FROM
                \"users\"
            WHERE
                uid = %s
            """,
            [g.uid]
        )
        user = cur.fetchone()
        link = affiliate_links[url]
        # Every url needs to have http(s):// at the start
        link += "&u1=" + user['uid']
    except:
        return jsonify(), 500
    finally:
        cur.close()
        conn.close()
    return jsonify({"url": link}), 200


def calc_kin_payout_amount(dollar_amount):
    EARN_PRICE_PER_DOLLAR = 100
    amount = dollar_amount * EARN_PRICE_PER_DOLLAR
    return min(amount, 50000)


def email_kino(user, account_creation="", earn_transaction="",
               spend_transaction="", withdraw_transaction="", error=""):
    msg = EmailMessage()
    msg.set_content(str(vars(user)) + "\n" + str(account_creation) + "\n" + str(earn_transaction) +
                    "\n" + str(spend_transaction) + "\n" + str(withdraw_transaction) + "\n" + error)
    if error:
        status = "Failed"
    else:
        status = "Succeeded"
    if account_creation:
        msg['Subject'] = "Account Creation: " + status
    if earn_transaction:
        msg['Subject'] = "Earn Transaction: " + status
    if spend_transaction:
        msg['Subject'] = "Buy Transaction: " + status
    if withdraw_transaction:
        msg['Subject'] = "Withdraw Transaction: " + status
    msg['From'] = "pythoncustomerservice@gmail.com"
    msg['To'] = "activity@earnwithkino.com"
    s = smtplib.SMTP('smtp.gmail.com:587')
    s.ehlo()
    s.starttls()
    s.login("pythoncustomerservice@gmail.com", "vdfv487g489b4")
    s.send_message(msg)
    s.quit()


def valid_order(order):

    GIFTCARD_TYPES = ['Amazon']
    GIFTCARD_AMOUNTS = [5, 10, 25]
    MAX_GIFTCARD_QUANTITY = 10
    MIN_GIFTCARD_QUANTITY = 1

    # Ensure all information is present
    if not all(x in order for x in ['email', 'type', 'amount', 'quantity', 'total']):
        return False

    type_ = order['type']
    amount = int(order['amount'])
    quanity = int(order['quantity'])
    total = float(order['total'])

    SPEND_PRICE_PER_DOLLAR = 10000
    # Ensure total is correct
    if total != quanity*amount*SPEND_PRICE_PER_DOLLAR:
        return False
    # Ensure the type of gift card exists
    if type_ not in GIFTCARD_TYPES:
        return False
    # Ensure the amount is one of the valid options
    if amount not in GIFTCARD_AMOUNTS:
        return False
    # Ensure the quantity is within bounds
    if not MIN_GIFTCARD_QUANTITY <= quanity <= MAX_GIFTCARD_QUANTITY:
        return False

    return True


async def buy_giftcard_async(json):
    user = None
    conn, cur = get_database_connection()
    client, account = await init_kin()
    try:
        cur.execute(
            """
            SELECT 
                *
            FROM 
                \"users\"
            WHERE   
                uid = %s
            """,
            [g.uid]
        )
        user = cur.fetchone()
        order = json
        if not valid_order(order):
            error = "Order validation failed"
            return jsonify(), 500
        total = float(order['total'])
        envelope = order['envelope']
        network_id = order['network_id']
        data = kin.decode_transaction(envelope, network_id)
        if data.operation.destination != kino_public_address:
            error = "Spend transaction to the wrong public address (not kino's)"
            return jsonify(), 500
        whitelisted_tx = account.whitelist_transaction(
            {"envelope": envelope,
             "network_id": network_id})
        user.balance -= total
        error = ""
        return jsonify({'tx': whitelisted_tx}), 201
    except Exception as e:
        try:
            error = str(e)
        except:
            error = "Spend transaction failed"
        return jsonify(), 500
    finally:
        cur.close()
        conn.close()
        await client.close()
        if user:
            email_kino(user, spend_transaction=request.json, error=error)


@app.route('/buy_giftcard', methods=['POST'])
@http_auth.login_required
def buy_giftcard():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(buy_giftcard_async(request.get_json()))
    return response


if __name__ == '__main__':
    app.run()


