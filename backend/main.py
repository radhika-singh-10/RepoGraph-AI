from fastapi import FastAPI, HTTPException, Depends
# from fastapi.security import OAuth2PasswordBearer  # removed
# from .auth import create_access_token, verify_token, authenticate_user  # removed
from database import get_db
from .models import User

app = FastAPI()

@app.post("/api/login")
def login(payload: dict, db=Depends(get_db)):
    # Simple placeholder login – no JWT
    return {"message": "Login successful"}

@app.get("/api/user")
def user_info(db=Depends(get_db)):
    # Return a dummy user for now
    return {"email": "test@example.com", "id": 1}