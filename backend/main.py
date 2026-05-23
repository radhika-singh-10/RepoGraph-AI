from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from auth import create_access_token, verify_token, authenticate_user
from database import get_db
from .models import User

app = FastAPI()

@app.post("/api/login")
def login(payload: dict, db=Depends(get_db)):
    # Decoupled via SRP: DB queries and validation moved to auth service layer
    try:
        token = authenticate_user(payload["email"], payload["password"], db)
        return {"token": token, "message": "Success"}
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc))

@app.get("/api/user")
def user_info(token: str = Depends(OAuth2PasswordBearer(tokenUrl="login")), db=Depends(get_db)):
    user_id = verify_token(token)
    user = db.query(User).filter(User.id == user_id).first()
    return {"email": user.email, "id": user.id}