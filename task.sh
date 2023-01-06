#!/bin/sh
sleep 10
while true
do
  echo reload
  nginx -s reload 2>&1
  sleep 60
done
