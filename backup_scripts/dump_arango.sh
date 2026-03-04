#!/bin/bash
set -e

if [ $# -ne 2 ]; then
    echo "Usage: $0 <arango_container_name> <output_dir>"
    exit 1
fi

CONTAINER_NAME="$1"
OUTPUT_DIR="$2"

docker exec -it "$CONTAINER_NAME" arangodump --overwrite true --all-databases true --server.password devpass --compress-output true --include-system-collections true --output-directory "$OUTPUT_DIR"

docker cp "$CONTAINER_NAME":"$OUTPUT_DIR" "$OUTPUT_DIR"

tar -cJf "$OUTPUT_DIR".tar.xz .

rm -r "$OUTPUT_DIR"