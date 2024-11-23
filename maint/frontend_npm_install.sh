#!/bin/bash
docker-compose -f docker-compose.yml run --rm frontend npm install --verbose --save-dev
