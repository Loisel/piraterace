#!/bin/bash
SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="$(readlink -f $SCRIPTDIR/../)"

cd $PROJECT_ROOT
docker-compose run --rm frontend sh -c "ionic build --prod"
docker-compose run --rm frontend sh -c "ionic cap sync --prod"
$PROJECT_ROOT/maint/frontend_chown.sh

echo "Run ~/android-studio/bin/studio.sh to build apks"

scp frontend/android/app/build/outputs/apk/debug/app-debug.apk root@dev.piraterace.com:/opt/piraterace/volumes/static_volume/
