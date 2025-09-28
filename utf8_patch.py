from fastapi.responses import JSONResponse

# FastAPI'nin varsayılan JSON Content-Type'ına charset ekle
JSONResponse.media_type = "application/json; charset=utf-8"

def apply(app):
    @app.middleware("http")
    async def ensure_utf8_charset(request, call_next):
        resp = await call_next(request)
        ct = resp.headers.get("content-type")
        if ct and "application/json" in ct.lower() and "charset=" not in ct.lower():
            resp.headers["content-type"] = "application/json; charset=utf-8"
        return resp
