from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"status": "CLIMARISK-OG backend running"}

@app.get("/health")
def health():
    return {"ok": True}
