#!/bin/bash

HOST="dev.piraterace.com"
INSTALL_DIR="/opt/piraterace"

ssh root@${HOST} "mkdir -p ${INSTALL_DIR}"
rsync -avh --progress ../../backend root@${HOST}:${INSTALL_DIR}
rsync -avh --progress ../../fonts root@${HOST}:${INSTALL_DIR}
rsync -avh --progress ../../frontend root@${HOST}:${INSTALL_DIR}
rsync -avh --progress ../../images root@${HOST}:${INSTALL_DIR}
rsync -avh --progress ../../maint root@${HOST}:${INSTALL_DIR}
rsync -avh --progress ../../nginx root@${HOST}:${INSTALL_DIR}
rsync -avh --progress ../../docker-compose.yml root@${HOST}:${INSTALL_DIR}
