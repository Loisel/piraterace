#!/bin/bash

docker-compose run --rm backend ./manage.py collectstatic --no-input
