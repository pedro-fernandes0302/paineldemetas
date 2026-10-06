from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.routers import desempenho, admin, digisac, campanha

settings = get_settings()

app = FastAPI()

# Origens permitidas vêm de FRONTEND_ORIGIN (várias separadas por vírgula)
origens = [o.strip() for o in settings.frontend_origin.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origens,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(desempenho.router)
app.include_router(admin.router)
app.include_router(digisac.router)
app.include_router(campanha.router)

@app.get("/")
def health():
    return {"status": "ok"}

@app.get("/debug-cors")
def debug_cors():
    return {
        "total_middlewares": len(app.user_middleware),
        "all": [
            {"cls": str(m.cls), "kwargs": {k: v for k, v in m.kwargs.items() if k != "allow_headers"}}
            for m in app.user_middleware
        ],
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080)