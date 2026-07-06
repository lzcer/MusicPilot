#!/bin/sh
set -eu

default_parser_config="/app/config/sites.parser.yaml"
parser_config="${MP_INDEXER_PARSER_CONFIG:-/config/sites.parser.yaml}"

if [ -n "$parser_config" ] \
    && [ "$parser_config" != "$default_parser_config" ] \
    && [ -f "$default_parser_config" ] \
    && [ ! -e "$parser_config" ]; then
    mkdir -p "$(dirname "$parser_config")"
    cp "$default_parser_config" "$parser_config"
fi

exec "$@"
