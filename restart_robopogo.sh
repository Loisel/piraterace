#!/bin/bash
docker-compose run --rm  web python manage.py collectstatic --noinput

docker-compose stop
docker-compose up -d
