ALL_UI_PY_FILES := $(patsubst src/qt_ui/%.ui,src/generated/%_ui.py, $(wildcard src/qt_ui/*.ui))

PROJECT_NAME := framework_ir_gui
MAIN_PY_FILE_NAME := framework_ir_gui

## Start Phony Targets
all: out/${PROJECT_NAME}

check-virtualenv:
	@if [ -z "$$VIRTUAL_ENV" ]; then \
		echo "**********************************************";\
		echo "Not in a virtualenv. Please activate one first."; \
		echo "**********************************************";\
		exit 1; \
	fi

dev: debug # I can never remember which one is correct.
debug: check-virtualenv debug-depends
	cd src ; python3 ${MAIN_PY_FILE_NAME}.py

debug-depends:  src/${MAIN_PY_FILE_NAME}.py $(ALL_UI_PY_FILES) src/generated/app_version.py src/icon.ico

.PRECIOUS:
	src/icon.ico

clean:
	rm -rf out
	rm -rf src/generated
	rm -rf ${PROJECT_NAME}_*
	rm -rf ${PROJECT_NAME}_*.exe
	rm -rf sbom

src/generated:
	mkdir -p src/generated

out:
	mkdir -p out

nothing:

FORCE:

.PHONY: all debug debug-depends run clean nothing FORCE dev designer

designer:
	pyside6-designer src/qt_ui/*.ui &

# End Phony Targets

out/${PROJECT_NAME}: src/icon.ico debug-depends
	pyinstaller --onefile --distpath out --add-data "src/icon.ico:." src/${MAIN_PY_FILE_NAME}.py

src/icon.ico: icon.png
	convert $< $@

src/generated/app_version.py: FORCE | out
	bash update_six15_git_version_if_needed.sh

src/generated/%_ui.py: src/qt_ui/%.ui | src/generated
	rm -f $@
	pyside6-uic $< > $@




# $(info Val: [${ALL_UI_PY_FILES}])