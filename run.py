"""Entry point — start the VibeCoder server."""

import uvicorn

if __name__ == "__main__":
    print("Starting VibeCoder at http://localhost:8000")
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)
