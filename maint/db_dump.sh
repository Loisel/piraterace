#!/bin/bash
set -euo pipefail
SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="$(readlink -f $SCRIPTDIR/../)"

cd $PROJECT_ROOT

DB_VOLUME=$PROJECT_ROOT/volumes/db_backup/
mkdir -p $DB_VOLUME

FILE=$(date -u +"%Y-%m-%dT%H.%M.%SZ").db

docker-compose exec db pg_dumpall -U postgres &> >(tee $DB_VOLUME/$FILE)

ln -srf $DB_VOLUME/$FILE $DB_VOLUME/latest.db
echo Saved database dump to $DB_VOLUME/$FILE"
