#!/bin/bash

docker-compose run --rm backend sh -c "pip install black; black */"
