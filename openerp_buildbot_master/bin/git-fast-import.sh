#!/bin/bash

IMPORT_MARKS="$1"
FI_PATHNAME="$2"

set -e
PGIT_FORCE=--force
cat "$FI_PATHNAME" | \
    git fast-import --quiet $PGIT_FORCE --import-marks="$IMPORT_MARKS" \
			--export-marks="$IMPORT_MARKS"

#eof
