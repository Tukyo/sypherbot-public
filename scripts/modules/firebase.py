import os
import firebase_admin
from firebase_admin import credentials, firestore, storage

#region Firebase
FIREBASE_TYPE= os.getenv('FIREBASE_TYPE')
FIREBASE_PROJECT_ID = os.getenv('FIREBASE_PROJECT_ID')
FIREBASE_PRIVATE_KEY_ID= os.getenv('FIREBASE_PRIVATE_KEY_ID')
FIREBASE_PRIVATE_KEY = os.getenv('FIREBASE_PRIVATE_KEY').replace('\\n', '\n')
FIREBASE_CLIENT_EMAIL= os.getenv('FIREBASE_CLIENT_EMAIL')
FIREBASE_CLIENT_ID= os.getenv('FIREBASE_CLIENT_ID')
FIREBASE_AUTH_URL= os.getenv('FIREBASE_AUTH_URL')
FIREBASE_TOKEN_URI= os.getenv('FIREBASE_TOKEN_URI')
FIREBASE_AUTH_PROVIDER_X509_CERT_URL= os.getenv('FIREBASE_AUTH_PROVIDER_X509_CERT_URL')
FIREBASE_CLIENT_X509_CERT_URL= os.getenv('FIREBASE_CLIENT_X509_CERT_URL')
FIREBASE_STORAGE_BUCKET = os.getenv('FIREBASE_STORAGE_BUCKET')

BLOB_EXPIRATION = 15 # Expiration time for uploaded files (minutes)

DATABASE = None
BUCKET = None

cred = credentials.Certificate({
    "type": FIREBASE_TYPE,
    "project_id": FIREBASE_PROJECT_ID,
    "private_key_id": FIREBASE_PRIVATE_KEY_ID,
    "private_key": FIREBASE_PRIVATE_KEY,
    "client_email": FIREBASE_CLIENT_EMAIL,
    "client_id": FIREBASE_CLIENT_ID,
    "auth_uri": FIREBASE_AUTH_URL,
    "token_uri": FIREBASE_TOKEN_URI,
    "auth_provider_x509_cert_url": FIREBASE_AUTH_PROVIDER_X509_CERT_URL,
    "client_x509_cert_url": FIREBASE_CLIENT_X509_CERT_URL
})

firebase_admin.initialize_app(cred, { 'storageBucket': FIREBASE_STORAGE_BUCKET })

def initialize_firebase():
    global DATABASE, BUCKET

    DATABASE = firestore.client()
    BUCKET = storage.bucket()

    print("Database: ", DATABASE)
    print("Bucket: ", BUCKET)
    print("Firebase initialized.")
#endregion Firebase