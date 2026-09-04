"""Production WSGI entry point.

PythonAnywhere, gunicorn and waitress all import ``application`` from here.
The dev server in app.py is not used in production.
"""

from app import create_app

application = create_app()
