#!/bin/bash

# Wrapper around 'git fast-export'

BRANCH_NAME="$1"
IMPORT_MARKS="$2"
FI_PATHNAME="$3"

set -e

git fast-export --signed-tags=warn --export-marks="$IMPORT_MARKS".new \
			 --import-marks="$IMPORT_MARKS" \
			"$BRANCH_NAME" > "$FI_PATHNAME"

mv -f "$IMPORT_MARKS" "$IMPORT_MARKS".bak
mv "$IMPORT_MARKS".new "$IMPORT_MARKS"
#eof
