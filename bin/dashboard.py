#!/usr/bin/env python3
"""Entry point for media dashboard web application."""

from crownpipe.media.dashboard import app

if __name__ == "__main__":
    # Run development server
    app.run(host="0.0.0.0", port=5000, debug=False)
