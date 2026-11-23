from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import api

app = FastAPI(title="Smart Energy Factory API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.router)

@app.get("/")
def root():
    return {"status": "ok", "message": "Smart Energy Factory API"}
