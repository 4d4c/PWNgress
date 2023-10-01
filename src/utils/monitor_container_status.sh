#!/bin/bash

# @reboot .../PWNgress/src/utils/monitor_container_status.sh

CONTAINER_NAME="pwngress"

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

DISCORD_WEBHOOK_URL_ALERTS=`grep 'DISCORD_WEBHOOK_URL_ALERTS=' $DIR/../settings/PWNgress_settings.cfg | cut -d '=' -f 2`

while true
do
    if [ "$( docker container inspect -f '{{.State.Status}}' $CONTAINER_NAME )" != "running" ]
    then
        curl -X POST \
            -H "Content-Type: application/json" \
            -d '{"embeds": [{"title": "PWNgress container is down", "color": 16711680}]}' \
            $DISCORD_WEBHOOK_URL_ALERTS
    fi
    sleep 1800
done
