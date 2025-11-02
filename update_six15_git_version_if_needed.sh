#!/bin/bash
SIX15_GIT_VERSION=$(git describe --abbrev=8 --dirty --tags --long)
SIX15_API_VERSION_MAJOR=$(echo "${SIX15_GIT_VERSION}" | sed -s 's#^\([0-9]*\)\.\([0-9]*\).*#\1#')
SIX15_API_VERSION_MINOR=$(echo "${SIX15_GIT_VERSION}" | sed -s 's#^\([0-9]*\)\.\([0-9]*\).*#\2#')

# Is "1" when there is exactly 1 tag on this commit, otherwise 0.
PART_NUMBER_VALID=$([ $(git tag --points-at | wc -l) -ne 1 ] ; echo $?)

FILE_CONTENTS=$(echo "GIT_VERSION = \"${SIX15_GIT_VERSION}\"
PART_NUMBER_VALID = ${PART_NUMBER_VALID}
")

mkdir -p src/generated
diff -N -q src/generated/app_version.py <(echo "${FILE_CONTENTS}") || (echo "${FILE_CONTENTS}" > src/generated/app_version.py)