import kin
import asyncio
import time
import firebase_admin
from firebase_admin import credentials, auth, messaging

cred = credentials.Certificate('kino-extension-firebase-adminsdk-mrn7d-cca5ca5e4c.json')
default_app = firebase_admin.initialize_app(cred)

KINO_PUBLIC_ADDRESS = "SCTDXS2NGAKNMSJFJVEE7IQQDUM7KAXTHNRVFTXRGMUYNFIO6LJ5U5M6"
KINO_PRIVATE_ADDRESS = "SCTDXS2NGAKNMSJFJVEE7IQQDUM7KAXTHNRVFTXRGMUYNFIO6LJ5U5M6"
APP_ID = "1111"

PUBLIC_ADDRESS = "GADRVBN3MX7OLDQFFJ6JQCUQHSX6E2B3LMIZ7TM6BSB772VRMZVYVA4L"
ANDROID_FCM_TOKEN = "dfAD1dDHL8o:APA91bGgsV4ex91786xd9_CM0YqaFtYUgDVQohYiHxi0PY0Zp66z4_q3kq4dJh6Z0M6dOfxnC7Cla4ktDZbzfYtuUxxkRxyuunv7WWECgtPta9xlW21VT604qwmJS41Ob7wjoxnOx90Q"
WEB_FCM_TOKEN = "eMIvFBt0Y3M:APA91bG-UJm9tV2suFrNPe3vtP8besyX9J2z9gCfytjAId3JpQaaZWAc0zP3L61lodCrDJzRpHacmPp3IkMfAftBq9DIcqBQ1msEBbNX7AtO-CBvGqtnB0zm_le4CUy2jnCZXr2JfqRG"


async def pay(kin_amount):
    client = kin.KinClient(kin.TEST_ENVIRONMENT)
    try:
        account = client.kin_account(KINO_PRIVATE_ADDRESS)
        print(account.get_public_address())
        fee = await client.get_minimum_fee()
        tx_hash = await account.send_kin(PUBLIC_ADDRESS, kin_amount, fee=fee, memo_text="test memo 123")
    finally:
        await client.close()


def notify_extension(kin_amount, product_name):
    message = messaging.Message(
        data={
            'title': "Kino",
            'body': "You just earned {} Kin for your purchase of {}.".format(str(kin_amount), product_name)
        },
        token=WEB_FCM_TOKEN,
    )
    try:
        response = messaging.send(message)
    except Exception as err:
        print(err)
    return


def notify_app(kin_amount, product_name):
    # See documentation on defining a message payload.
    message = messaging.Message(
        data={
            'title': "Kino",
            'body': "You just earned {} Kin for your purchase of {}.".format(str(kin_amount), product_name)
        },
        token=ANDROID_FCM_TOKEN,
    )
    # Send a message to the device corresponding to the provided registration token.
    try:
        response = messaging.send(message)
    except Exception as err:
        print(err)
    return


async def test1():
    amt = 10
    await pay(amt)
    if WEB_FCM_TOKEN:
        notify_extension(amt, "test product")
    if ANDROID_FCM_TOKEN:
        notify_app(amt, "test_product")


async def test2():
    client = kin.KinClient(kin.TEST_ENVIRONMENT)
    try:
        keypair = kin.Keypair()
        await client.friendbot(keypair.public_address)
        account = client.kin_account(keypair.secret_seed)
        fee = await client.get_minimum_fee()
        await account.send_kin(PUBLIC_ADDRESS, 9900, fee=fee)
    finally:
        await client.close()

loop = asyncio.get_event_loop()
loop.run_until_complete(test1())

