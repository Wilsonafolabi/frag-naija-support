from slowapi import Limiter
from fastapi import Request

def get_real_ip(request: Request) -> str:
    # Respect X-Forwarded-For for Render/Cloudflare deployments
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

limiter = Limiter(key_func=get_real_ip)