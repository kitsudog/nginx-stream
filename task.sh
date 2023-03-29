#!/bin/sh
sleep 10
while true
do
  sleep ${DURATION:-600}
  echo reload
  nginx -s reload 2>&1
done
