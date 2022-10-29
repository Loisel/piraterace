#!/bin/bash
set -euo pipefail
SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="$(readlink -f $SCRIPTDIR/../)"

cd $PROJECT_ROOT

FILE=${1:-latest.db}

echo "Restoring from $FILE"

docker-compose up -d db
docker-compose exec db bash -l -c " \
echo Restoring $FILE; \
ls -al /backup/$FILE; \
while [ ! pg_isready ]; do echo 'waiting for database'; done
psql -U postgres < /backup/$FILE \
"
