#!/bin/bash

# A script to initialize the OpenERP submodules, with local proxying

REPODIR=/home/buildbot/repos
subm_update() {
    grep -v '^#' | grep -v '^$' | \
    while read SUBM PROXY_PATH ; do
	git submodule update --reference "$PROXY_PATH" $SUBM
    done
}

cat '-' << EOF | subm_update
addons	$REPODIR/openobject-addons
# addons-koo	$REPODIR/openobject-addons-koo
#bi 	$REPODIR/openobject-bi
# buildbot
client	$REPODIR/openobject-client
client-kde	$REPODIR/openobject-client-kde
client-web	$REPODIR/openobject-client-web
doc	$REPODIR/openobject-doc
extra-addons	$REPODIR/openobject-addons
libcli	$REPODIR/openerp-libcli
server	$REPODIR/openobject-server

EOF
