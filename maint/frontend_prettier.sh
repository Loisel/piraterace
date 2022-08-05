#!/bin/bash

docker-compose run --rm frontend sh -c "npm install --save-dev --save-exact -g prettier; prettier -w src/app/"
