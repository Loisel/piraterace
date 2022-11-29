#!/bin/bash
SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="$(readlink -f $SCRIPTDIR/../)"

$PROJECT_ROOT/maint/backend_prettier.sh
$PROJECT_ROOT/maint/frontend_prettier.sh
