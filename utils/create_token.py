import os
from dotenv import load_dotenv
load_dotenv()
secret_key = os.getenv("secret_key")
import jwt
import datetime as dt
from datetime import timezone


def create_token():
    module_name='bot'
    payload = {
        "iss": module_name,  # Issuer
        "iat": dt.datetime.utcnow(),  # Issued At
        "exp": dt.datetime.utcnow() + dt.timedelta(minutes=2),  # Expiration
        "nbf": dt.datetime.utcnow(),  # Not Before
        "jti": module_name,  # JWT ID
        "sub": module_name  # Subject
    }

    # Encode the JWT
    token = jwt.encode(payload, secret_key, algorithm="HS256")

    # Set up headers with the JWT token
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    return headers