#!/bin/bash

docker-compose stop
docker-compose rm web
docker-compose build --no-cache web
docker-compose up -d
