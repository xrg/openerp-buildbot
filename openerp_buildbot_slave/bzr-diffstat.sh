#!/bin/bash

set -e

bzr diff -c branch: | diffstat

#eof