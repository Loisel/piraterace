#!/bin/bash

docker-compose run --rm frontend sh -c "ionic build --prod"
docker-compose -f docker-compose-prod.yml up
