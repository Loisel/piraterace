#!/bin/bash

docker-compose run --rm web ./manage.py makemigrations pigame piplayer
docker-compose run --rm web ./manage.py migrate
