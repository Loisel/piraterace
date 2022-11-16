#!/bin/bash
SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="$(readlink -f $SCRIPTDIR/../)"

APK=$PROJECT_ROOT/frontend/android/app/build/outputs/apk/debug/app-debug.apk

if [ -e $APK ]; then
  echo "Found existing apk at $APK"
  echo "Is this the current version?"
  echo "Or shall we delete the file and run the build process again?"
  read -p "Build again? (y/n)?" CONT
  if [ "$CONT" = "y" ]; then
    echo "... on we go...."
    rm $APK

  else
    echo "... publishing $APK ..."
    scp frontend/android/app/build/outputs/apk/debug/app-debug.apk root@dev.piraterace.com:/opt/piraterace/volumes/static_volume/
    exit 0
  fi
fi

cd $PROJECT_ROOT
docker-compose run --rm frontend sh -c "ionic build --prod"
docker-compose run --rm frontend sh -c "ionic cap sync --prod"
$PROJECT_ROOT/maint/frontend_chown.sh

echo " Now, run"
echo "    ~/android-studio/bin/studio.sh"
echo " to build new apks!"
