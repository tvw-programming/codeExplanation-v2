"""Minimal FastAPI sample for visual extraction."""
from fastapi import FastAPI, Depends

app = FastAPI()

def get_db():
    return {}

@app.get("/users")
def list_users(db=Depends(get_db)):
    """List users."""
    return []

@app.post("/users")
def create_user():
    return {"ok": True}
