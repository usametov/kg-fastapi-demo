"""`python -m app` - start uvicorn bound to $HOST:$PORT (Factor VII: port binding).

The app is self-contained: it exports HTTP by binding a port itself rather
than relying on an external web server being injected at runtime.
"""

import uvicorn

from app.config import get_settings

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, log_config=None, timeout_graceful_shutdown=20)
