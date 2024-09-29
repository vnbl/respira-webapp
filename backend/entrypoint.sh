#!/bin/bash
python manage.py collectstatic --noinput;

chmod -R o+r /static;
chmod -R o+x /static;
chown -R www-data:www-data /static;

gunicorn --bind :8000 --workers 2 backend.wsgi:application;

echo "Django failed, but keeping the container alive..."
tail -f /dev/null