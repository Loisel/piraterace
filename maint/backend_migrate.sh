#!/bin/bash

docker-compose run --rm backend ./manage.py makemigrations pigame piplayer
docker-compose run --rm backend ./manage.py migrate
