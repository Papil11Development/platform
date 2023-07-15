#!/bin/sh
source ./env.sh
set -x
set -e
if [[ $ENABLE_GTM ]]
then
  export INDEX_FILENAME='indexWithAnalytics.html'
else
  export INDEX_FILENAME='index.html'
fi

envsubst "$ENV_SUBSSTR" < /nginx.conf > /etc/nginx/nginx.conf

exec nginx -g 'daemon off;'
