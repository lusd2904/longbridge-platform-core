import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

REFACTOR_ROOT = Path(__file__).resolve().parents[4]
if str(REFACTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(REFACTOR_ROOT))

from apps.market.module_shared import build_alert, build_dependency_status, build_health_payload, summarize_status


app = FastAPI(
    title="Refactor V2 Sentiment Service",
    version="0.1.0",
    description="Sentiment placeholder service for the refactor workspace.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    port = int(os.getenv("REF_SENTIMENT_SERVICE_PORT", "8106"))
    deps = {
        "collector": build_dependency_status("collector", "disabled", detail="舆情采集链路仍为占位实现", optional=True),
    }
    return build_health_payload(
        service="sentiment-service",
        version=app.version,
        port=port,
        status=summarize_status(deps.values()),
        deps=deps,
        alerts=[build_alert("sentiment-placeholder", "info", "舆情服务仍是占位实现，尚未接真实采集链路")],
        capabilities=["placeholder-contract"],
        extra={
            "mode": "placeholder",
        },
    )


@app.get("/api/v1/sentiment/config")
async def get_config():
    return {
        "enabled": False,
        "mode": "placeholder",
        "message": "Sentiment data collection is not implemented yet.",
        "reservedPort": int(os.getenv("REF_SENTIMENT_SERVICE_PORT", "8106")),
        "reservedPrefix": "/api/v1/sentiment",
    }


@app.post("/api/v1/sentiment/collect")
async def collect_sentiment():
    return {
        "success": False,
        "status": "placeholder",
        "message": "Sentiment collector is reserved but not implemented yet.",
    }


@app.post("/api/v1/sentiment/analyze")
async def analyze_sentiment():
    return {
        "success": False,
        "status": "placeholder",
        "message": "Sentiment analysis pipeline is reserved but not implemented yet.",
    }


@app.get("/api/v1/sentiment/symbol/{symbol}")
async def get_symbol_sentiment(symbol: str):
    return {
        "success": False,
        "status": "placeholder",
        "symbol": symbol.upper(),
        "message": "Symbol sentiment endpoint is reserved for future implementation.",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("REF_SENTIMENT_SERVICE_PORT", "8106")),
        reload=False,
    )
