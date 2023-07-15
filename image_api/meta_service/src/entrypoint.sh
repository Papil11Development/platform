#!/bin/bash
set -x
set -e

echo "Server is running on the path $ROOT_PATH"

gunicorn --workers=$WORKERS \
    --bind="0.0.0.0:$PORT" \
    --timeout 120 \
    -k uvicorn.workers.UvicornWorker \
    --access-logfile - \
    --error-logfile - \
    --keep-alive 600 \
    main:app

# uvicorn main:app --host 0.0.0.0 --port $PORT --root-path "$ROOT_PATH" --workers=$WORKERS --limit-concurrency 500
