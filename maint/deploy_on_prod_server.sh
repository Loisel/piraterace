#!/bin/bash
SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="$(readlink -f $SCRIPTDIR/../)"

$PROJECT_ROOT/maint/backend_migrate.sh
$PROJECT_ROOT/maint/backend_collectstatic.sh
$PROJECT_ROOT/frontend_npm_install.sh

docker-compose run --rm frontend sh -c "ionic build --prod"
docker-compose -f docker-compose-prod.yml up
