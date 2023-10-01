#!/bin/bash

docker stop pwngress
docker rm -f pwngress
docker build -t pwngress .
docker run -t --detach -v ./logs:/app/logs -v ./database:/app/database -v ./images:/app/images --name pwngress pwngress
