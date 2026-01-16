web: cd jarvis && gunicorn app:app --bind 0.0.0.0:$PORT --workers 3 --threads 3 --worker-class gthread --timeout 120 --graceful-timeout 30 --keep-alive 5
