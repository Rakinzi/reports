import os

import uvicorn

from src.reports.app import app


def main() -> None:
    host = os.getenv("REPORTS_API_HOST", "127.0.0.1")
    port = int(os.getenv("REPORTS_API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
