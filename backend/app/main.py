from fastapi import FastAPI
import os

app = FastAPI(title="CLIMARISK-OG API", version="0.2.0")

@app.get("/")
def root():
    return {"status": "ok", "message": "CLIMARISK-OG backend running"}

@app.get("/health")
def health():
    return {"status": "ok"}
