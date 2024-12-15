#!/bin/bash
python manage.py collectstatic --noinput;
python manage.py migrate api --fake-initial;
python manage.py migrate;

chmod -R o+r /static;
chmod -R o+x /static;
chown -R www-data:www-data /static;

gunicorn --bind :8000 --workers 4 backend.wsgi:application;

echo "Django failed, but keeping the container alive..."
tail -f /dev/null