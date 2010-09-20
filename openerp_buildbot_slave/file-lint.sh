#!/bin/bash
#

PYFLAKES=$(dirname "$0")/pyflakes2.py

EXIT_CODE=0
for FNAME in "$@" ; do
	if [ ! -f "$FNAME" ] ; then
	    continue
	fi
	case $(basename "$FNAME") in
	*.py)
		$PYFLAKES "$FNAME" ; EXIT=$?
		
		if [ "$EXIT" == 1 ]; then
			echo "Pyflakes failed for: $FNAME" >&2
			EXIT_CODE=1
		elif [ "$EXIT" == 3 ] ; then
			echo "Please correct warnings for $FNAME" >&2
			# echo "$FNAME" >> .git/lint-failed
		fi
		if grep -HnF -m 10 '*-*' "$FNAME" ; then
		    echo "Not ready to commit: $FNAME" >&2
		    EXIT_CODE=1
		fi
		if [ "$ALLOW_PYTABS" != "y" ] && grep -HnP -m 10 '^ *\t' "$FNAME" ; then
			echo "You used tabs in $FNAME. Please expand them" >&2
			EXIT_CODE=1
		fi
	;;
	*.xml)
		if grep -HnF -m 10 '*-*' "$FNAME" ; then
		    echo "Not ready to commit: $FNAME" >&2
		    EXIT_CODE=1
		fi
		if ! xmllint --noout --nowarning "$FNAME" ; then
			echo "XmlLint failed for: $FNAME" >&2
			EXIT_CODE=1
		fi
	;;
	*.rml)
		if ! xmllint --noout --nowarning "$FNAME" ; then
			echo "XmlLint failed for: $FNAME" >&2
			exit 1
		fi
	;;
	*.po)
		msgcat -o /dev/null "$FNAME" || EXIT_CODE=$?
	;;
	*)
		echo "No lint for $FNAME" >&2
		;;
	esac
done

exit $EXIT_CODE

#eof
