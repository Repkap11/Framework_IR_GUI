#!/bin/bash
set -e

make clean

PROJECT_NAME=framework_ir_gui

GITLAB_USER_NAME="gitlab-ci-token"
# CI_JOB_TOKEN set from gitlab-ci build env

if [ "$1" = "--prepka" ]; then
  GITLAB_USER_NAME="prepka"
  CI_JOB_TOKEN="$(cat /home/prepka/prepka-gitlab-token.txt)"
fi

if ! [ -v CI_JOB_TOKEN ]; then
  echo "CI_JOB_TOKEN is undefined. Either build from gitlab, or define your own token for development."
  exit 1
fi

docker build -f DockerfileLinux -t ${PROJECT_NAME}_linux \
		--network=host \
    --build-arg "user_id=$(id -u)" \
    --build-arg "gitlab_user_name=${GITLAB_USER_NAME}" \
    --build-arg "ci_job_token=${CI_JOB_TOKEN}" \
    .

docker build -f DockerfileWin -t ${PROJECT_NAME}_win \
		--network=host \
    --build-arg "user_id=$(id -u)" \
    --build-arg "gitlab_user_name=${GITLAB_USER_NAME}" \
    --build-arg "ci_job_token=${CI_JOB_TOKEN}" \
   .


docker run -i --rm --user "$(id -u):$(id -g)" -v "$(pwd)/:/home/six15/${PROJECT_NAME}:rw" ${PROJECT_NAME}_linux make debug-depends

docker run -i --rm --user "$(id -u):$(id -g)" -v "$(pwd)/out/:/home/six15/${PROJECT_NAME}/out:rw" ${PROJECT_NAME}_linux bash -c "pip list > out/python_linux.list"
docker run -i --rm --user "$(id -u):$(id -g)" -v "$(pwd)/out/:/home/six15/${PROJECT_NAME}/out:rw" ${PROJECT_NAME}_win bash -c ". /opt/mkuserwineprefix ; wine pip list > out/python_win.list"

docker run -i --rm --user "$(id -u):$(id -g)" -v "$(pwd)/src/:/home/six15/${PROJECT_NAME}/src:ro" -v "$(pwd)/out/:/home/six15/${PROJECT_NAME}/out:rw" ${PROJECT_NAME}_linux 2>&1 | sed -e 's/^/L: /;'
docker run -i --rm --user "$(id -u):$(id -g)" -v "$(pwd)/src/:/home/six15/${PROJECT_NAME}/src:ro" -v "$(pwd)/out/:/home/six15/${PROJECT_NAME}/out:rw" ${PROJECT_NAME}_win   2>&1 | sed -e 's/^/W: /;'

cp out/${PROJECT_NAME} "${PROJECT_NAME}_$(git describe --abbrev=8 --dirty --tags --long)"
cp out/${PROJECT_NAME}.exe "${PROJECT_NAME}_$(git describe --abbrev=8 --dirty --tags --long).exe"

mkdir sbom
cp out/python_linux.list sbom/
cp out/python_win.list sbom/
