from aura.web.app import create_app

# Expose `app` for WSGI servers (gunicorn, uWSGI)
app = create_app()
