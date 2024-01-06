#!/bin/bash

docker stop pwngress
docker rm -f pwngress
docker build -t pwngress .
docker run -t --detach -v /$(pwd)/logs:/app/logs -v /$(pwd)/database:/app/database -v /$(pwd)/images:/app/images --dns 1.1.1.1 --name pwngress pwngress
