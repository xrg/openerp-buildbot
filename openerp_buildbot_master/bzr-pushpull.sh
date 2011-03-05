#!/bin/bash

SLAVENAME=
BRANCH_URL=
REVISION=
REPO_MODE=
BUILDERNAME=
PROXY_PATH=
MASTER_DIR=$(dirname "$0")
DRY=
while [ -n "$1" ] ; do
    case "$1" in 
	-b)
	    BUILDERNAME="$2"
	;;
	-l)
	    BRANCH_URL="$2"
	;;
	-r)
	    REVISION="$2"
	;;
	-m)
	    REPO_MODE="$2"
	;;
	-s)
	    SLAVENAME="$2"
	;;
	-p)
	    PROXY_PATH="$2"
	;;
	--dry-run)
	    DRY=echo
	    shift 1
	    continue
	;;
	*)
	    echo "Invalid argument: $1"
	    exit 4
	;;
    esac
    shift 2
done

set -e

SLAVE_BASE_URL=$(grep "^$SLAVENAME" $MASTER_DIR/bzr-pushpull.cfg | tr -s ' ' | cut -d ' ' -f 2)
if [ -z "$SLAVE_BASE_URL" ] ; then
    echo "Don't know how to pull from $SLAVENAME"
    exit 2
fi

BUILDDIRNAME=$(basename $PROXY_PATH)

PROXY_PATH=$(echo $PROXY_PATH | sed 's|^file://||;s|%20| |g')

$DRY cd "$PROXY_PATH"
# ignoring revision so far
$DRY bzr pull -q --overwrite "$SLAVE_BASE_URL/$BUILDDIRNAME/$REPO_MODE"
$DRY bzr push -q "$BRANCH_URL"

#eof