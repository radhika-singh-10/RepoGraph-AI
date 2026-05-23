import jwt
from datetime import datetime, timedelta
from database import SECRET_KEY
from .models import User

def create_access_token(user_id: int) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(token: str) -> int:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload["sub"]
    except jwt.PyJWTError:
        raise Exception("Invalid token")

def authenticate_user(email: str, password_raw: str, db) -> str:
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.verify_password(password_raw):
        raise Exception("Invalid credentials")
    return create_access_token(user.id)