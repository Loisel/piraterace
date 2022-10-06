#!/bin/bash
SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="$(readlink -f $SCRIPTDIR/../)"

$PROJECT_ROOT/maint/backend_migrate.sh
$PROJECT_ROOT/maint/backend_collectstatic.sh
$PROJECT_ROOT/maint/frontend_npm_install.sh

cd $PROJECT_ROOT
docker-compose run --rm frontend sh -c "ionic build --prod"
docker-compose -f $PROJECT_ROOT/docker-compose-prod.yml down
docker-compose -f $PROJECT_ROOT/docker-compose-prod.yml up -d
