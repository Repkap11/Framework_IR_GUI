#Install Python https://www.python.org/downloads/, make sure to check the box to add to PATH.
python -m venv .venv
. .\.venv\Scripts\activate
pip3 install -r requirements.txt
remove-item -path out -Force -Recurse -ErrorAction SilentlyContinue
remove-item -path src\generated -Force -Recurse -ErrorAction SilentlyContinue
remove-item -path "framework_ir_gui_$(git describe --abbrev=8 --dirty --tags --long).exe" -Force -ErrorAction SilentlyContinue
mkdir out
mkdir src\generated

pyside6-uic.exe .\src\qt_ui\main_window.ui | out-file src\generated\main_window_ui.py -encoding utf8
pyside6-uic.exe .\src\qt_ui\display_brightness.ui | out-file src\generated\display_brightness_ui.py -encoding utf8
pyside6-uic.exe .\src\qt_ui\scaling.ui | out-file src\generated\scaling_ui.py -encoding utf8
pyside6-uic.exe .\src\qt_ui\quantum_data.ui | out-file src\generated\quantum_data_ui.py -encoding utf8

Write-Output "GIT_VERSION = `"$(git describe --abbrev=8 --dirty --tags --long)`"" | out-file src\generated\app_version.py -encoding utf8
# EXE's built with this script are never released part numbers. Use the docker based windows build instead.
Write-Output "PART_NUMBER_VALID = False" | out-file src\generated\app_version.py -encoding utf8 -Append

pyinstaller.exe --upx-exclude=python3.dll --upx-exclude=python312.dll --onefile --noconsole --distpath out --icon src\icon.ico --add-binary "src\libusb-1.0.dll;." --add-data "src\icon.ico;." src\framework_ir_gui.py


# Output file is .\out\framework_ir_gui.exe
Move-Item .\out\framework_ir_gui.exe "framework_ir_gui_$(git describe --abbrev=8 --dirty --tags --long).exe"
exit $LASTEXITCODE