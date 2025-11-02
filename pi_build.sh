#!/bin/bash
set -e

make clean

docker build -f DockerfilePi -t framework_ir_gui_pi --network=host --build-arg "user_id=$(id -u)" .


docker run -i --rm --user "$(id -u):$(id -g)" -v "$(pwd)/:/home/six15/framework_ir_gui:rw" framework_ir_gui_pi make debug-depends

docker run -i --rm --user "$(id -u):$(id -g)" -v "$(pwd)/out/:/home/six15/framework_ir_gui/out:rw" framework_ir_gui_pi bash -c "pip list > out/python_pi.list"

docker run -i --rm --user "$(id -u):$(id -g)" -v "$(pwd)/src/:/home/six15/framework_ir_gui/src:ro" -v "$(pwd)/out/:/home/six15/framework_ir_gui/out:rw" framework_ir_gui_pi 2>&1 | sed -e 's/^/PI: /;'

cp out/framework_ir_gui "framework_ir_gui_pi_$(git describe --abbrev=8 --dirty --tags --long)"

mkdir sbom
cp out/python_pi.list sbom/
