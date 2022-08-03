#!/bin/bash

ID=${1:-1000}
docker-compose run --rm frontend sh -c "/bin/chown -R ${ID}:${ID} *"
