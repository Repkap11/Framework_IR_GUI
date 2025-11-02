#!/usr/bin/env python3
import sys
import os
import datetime
import time
import struct
import traceback
import signal
import usb.core
from typing import Optional
from PySide6.QtWidgets import QMainWindow, QApplication, QWidget, QMessageBox, QSizePolicy, QSpacerItem, QGridLayout, QFileDialog, QLabel, QGroupBox, QFrame, QPushButton
from PySide6.QtCore import QThread, QSettings, QTimer, Qt, Signal
from PySide6.QtGui import QDragMoveEvent, QDropEvent, QPaintEvent, QCloseEvent, QColor, QIcon, QColorConstants
from generated import main_window_ui as Main_Window_UI
from generated import app_version as AppVersion
from ui_device_watcher import Framework_IR_DeviceListenThread, Framework_IR_DeviceDisconnectThread
from lib_six15_api.stm32_bootloader_finder_thread import BootloaderListenThread, BootloaderDisconnectThread
from lib_six15_api.sys_exception_hook import SysExceptionHook
import part_numbers as PartNumbers
from framework_ir import Framework_IR
from framework_ir_finder import Framework_IR_Finder
from lib_six15_api.serial_log_watcher import Serial_LogWatcher
from framework_ir_log_watcher import Framework_IR_LogWatcher
import framework_ir_six15_api as Six15_API
from lib_six15_api.logger import Logger, LogLevel, LoggerImpl
import lib_six15_api.version
from firmware_update_thread import FPGA_FirmwareUpdateThread
from thread_debug import DEBUG_THREADS
import lib_six15_api.stm32_firmware_updater as STM32_Firmware_Update

APPLICATION_NAME: str = "Framework_IR"

class Window(QMainWindow):
    ui: Main_Window_UI.Ui_Form
    backgroundDeviceThread: Optional[QThread] = None
    backgroundBootloaderThread: Optional[QThread] = None
    framework_ir: Optional[Framework_IR] = None
    framework_ir_bootloader: Optional[usb.core.Device] = None
    any_update_state_in_progress: bool = False

    event_log_lines: str = ""

    settings: QSettings = QSettings(QSettings.Scope.UserScope, "RepTech", APPLICATION_NAME)
    SETTING_STM32_FW_FILE_NAME: str = "stm32_fw_file_name"

    ##### Start Class Override Functions #####

    def __init__(self):
        super().__init__()
        SysExceptionHook()
        self.setWindowTitle(f"Framework_IR GUI Version: {AppVersion.GIT_VERSION} - Part Number: {PartNumbers.GUI_PART_NUMBER}")
        if hasattr(sys, '_MEIPASS'):
            icon_path = os.path.join(sys._MEIPASS, 'icon.ico')
        else:
            icon_path = 'icon.ico'
        self.setWindowIcon(QIcon(icon_path))

        self.isClosing = False
        main_window_content = QWidget(self)
        self.ui = Main_Window_UI.Ui_Form()
        self.logger = LoggerImpl(self.loggerImpl)
        self.logger.makeDefault(True)
        self.ui.setupUi(main_window_content)

        self.setInitialState()
        self.hookEvents()
        self.setCentralWidget(main_window_content)
        self.startLogThread()

        self.restartDeviceListenThread()
        self.backgroundBootloaderThread = BootloaderListenThread(self.onBootloaderConnectionChange)
        self.backgroundBootloaderThread.start()
        self.initial_show_called = False

    @staticmethod
    def validateDragEvent(event: QDragMoveEvent | QDropEvent) -> Optional[str]:
        urls = event.mimeData().urls()
        if (len(urls) != 1):
            return None
        url = urls[0]
        url_path = url.toLocalFile()
        if (url_path == None):
            return None
        if not url_path.endswith((".dfu")):
            return None
        return url_path

    def dragEnterEvent(self, event: QDragMoveEvent):
        fileName = Window.validateDragEvent(event)
        if fileName != None:
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        fileName = Window.validateDragEvent(event)
        if fileName != None:
            if fileName.endswith(".dfu"):
                self.ui.lineEdit_stm32_fw_file_name.setText(fileName)
            self.updateFlashEnableUiState()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.isClosing = True
        # print("Close Event")
        self.stopLogThread()
        if (self.backgroundDeviceThread):
            self.backgroundDeviceThread.requestInterruption()
        if (self.backgroundBootloaderThread):
            self.backgroundBootloaderThread.requestInterruption()
        if (self.backgroundLogThread):
            self.backgroundLogThread.requestInterruption()

        if (self.backgroundDeviceThread):
            self.backgroundDeviceThread.wait()
        if (self.backgroundBootloaderThread):
            self.backgroundBootloaderThread.wait()
        if (self.backgroundLogThread):
            self.backgroundLogThread.wait()

        self.backgroundDeviceThread = None
        self.backgroundBootloaderThread = None
        self.backgroundLogThread = None

        if (self.framework_ir):
            self.framework_ir.close()
            self.framework_ir = None
        return super().closeEvent(event)

    ##### End Class Override Functions #####

    ##### Start Helper Functions #####

    def startLogThread(self):
        if False:
            self.backgroundLogThread: QThread = Serial_LogWatcher(Six15_API.VID_SIX15, Six15_API.PID_FRAMEWORK_IR)
        else:
            self.backgroundLogThread: QThread = Framework_IR_LogWatcher()
        self.backgroundLogThread.start()

    def stopLogThread(self):
        if (self.backgroundLogThread):
            self.backgroundLogThread.requestInterruption()
            self.backgroundLogThread.wait()
        self.backgroundLogThread = None

    @staticmethod
    def setLabelTextColor(label: QLabel, color: Optional[QColor]):
        if color == None:
            style_sheet = ""
        else:
            style_sheet = "QLabel { color : "+color.name()+"; }"
        label.setStyleSheet(style_sheet)

    def restartDeviceListenThread(self):
        if self.backgroundDeviceThread:
            self.backgroundDeviceThread.requestInterruption()
            self.backgroundDeviceThread.wait()

        self.backgroundDeviceThread = Framework_IR_DeviceListenThread(self.onDeviceConnectionChange)
        self.backgroundDeviceThread.start()

    def restartDeviceDisconnectThread(self):
        if self.backgroundDeviceThread:
            self.backgroundDeviceThread.requestInterruption()
            self.backgroundDeviceThread.wait()

        self.backgroundDeviceThread: QThread = Framework_IR_DeviceDisconnectThread(self.onDeviceConnectionChange, self.framework_ir)
        if (self.backgroundDeviceThread):
            self.backgroundDeviceThread.start()

    def setInitialState(self):
        # Ideally everything here would be set in QT Creator, but some things can't
        self.ui.label_version_gui_version.setText(f"{AppVersion.GIT_VERSION}")
        self.ui.lineEdit_stm32_fw_file_name.setText(self.settings.value(Window.SETTING_STM32_FW_FILE_NAME))

        self.clearStateFromDisconnect()

    def loggerImpl(self, level: LogLevel, message: str):
        self.appendEventLog(self.ui, Logger.LOG_LEVEL_TO_COLOR[level], f"{message}")
        if (level == LogLevel.CRITICAL_ERROR):
            self.showErrorDialog(message)

    @staticmethod
    def appendEventLog(ui: Main_Window_UI.Ui_Form, color: QColor, message: str):
        time_str: str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S| ")
        message = time_str + message
        html = f"<p style=\"color:{color.name()};white-space:pre\">{message}</p>"
        ui.plainTextEdit_event_log.appendHtml(html)

    def showErrorDialog(self, message: str, title="Error") -> None:
        print(f"DialogError: {title}: {message}")

        error_message_box = QMessageBox()
        error_message_box.setIcon(QMessageBox.Icon.Critical)
        error_message_box.setInformativeText(message)
        error_message_box.setWindowTitle("Error")
        error_message_box.setText(title)
        try:
            # Just incase QT changes QMessageBox to not be a grid, catch any errors.
            spacer: QSpacerItem = QSpacerItem(300, 0, QSizePolicy.Policy.Minimum,  QSizePolicy.Policy.Expanding)
            layout: QGridLayout = error_message_box.layout()
            layout.addItem(spacer, layout.rowCount(),
                           0, 1, layout.columnCount())
        except:
            pass
        error_message_box.exec()

    def onBootloaderConnectionChange(self, framework_ir_bootloader: Optional[usb.core.Device]):
        if (framework_ir_bootloader == self.framework_ir_bootloader):
            Logger.warn(f"onBootloaderConnectionChange: nothing changed:{framework_ir_bootloader}")
            # No need to take action if nothing changed
            return
        self.framework_ir_bootloader = framework_ir_bootloader
        if (self.isClosing):
            return
        self.updateStateFromBootloaderConnection()
        if (framework_ir_bootloader == None):
            Logger.info("#### Device Disconnected: STM32 Bootloader")
            self.backgroundBootloaderThread = BootloaderListenThread(self.onBootloaderConnectionChange)
        else:
            Logger.info("#### Device Connected: STM32 Bootloader")
            self.backgroundBootloaderThread = BootloaderDisconnectThread(self.onBootloaderConnectionChange)
        self.backgroundBootloaderThread.start()

    def onDeviceConnectionChange(self, framework_ir: Framework_IR):
        if (framework_ir == self.framework_ir):
            # No need to take action if nothing changed
            return

        if (self.framework_ir is not None):
            self.framework_ir.close()
            self.framework_ir = None
        self.framework_ir = framework_ir
        if (self.isClosing):
            return

        if (isinstance(self.backgroundLogThread, Framework_IR_LogWatcher)):
            self.backgroundLogThread.set_Framework_IR(self.framework_ir)

        if (framework_ir == None):
            Logger.info("#### Device Disconnected: Framework IR")
        else:
            Logger.info("#### Device Connected: Framework IR")

        if (framework_ir == None):
            self.clearStateFromDisconnect()
            self.restartDeviceListenThread()
        else:
            try:
                self.queryStateFromDevice()
            except Exception as e:
                # error_msg = "Error querying device state: " + str(e) + "\ntraceback:  " + traceback.format_exc()
                error_msg = "Error querying device state: " + str(e)
                print(error_msg)
                Logger.error(error_msg)
            self.restartDeviceDisconnectThread()
            Window.applyEnabledState(self.ui, True)

    def updateStateFromBootloaderConnection(self):
        self.updateFlashEnableUiState()

    @staticmethod
    def applyEnabledState(ui: Main_Window_UI.Ui_Form, enabled):
        ui.label_version_micro_sw_version.setEnabled(enabled)
        ui.control_reboot.setEnabled(enabled)
        ui.control_reboot_bootloader.setEnabled(enabled)

        ui.control_brightness_up.setEnabled(enabled)
        ui.control_brightness_down.setEnabled(enabled)

    def clearStateFromDisconnect(self) -> None:
        if (self.framework_ir != None):
            Logger.error("Can't clearStateFromDisconnect, a Framework_IR is connected")
        self.ui.label_version_micro_sw_version.setText("N/A")
        self.updateFlashEnableUiState()
        self.ui.progress_bar_fw.setEnabled(False)
        self.ui.progress_bar_fw.setValue(0)
        self.readAndApplyStateToUI(False)
        Window.applyEnabledState(self.ui, False)

    def queryStateFromDevice(self) -> None:
        if (not self.framework_ir):
            Logger.error("Can't queryStateFromDevice, no Framework_IR connected")
            return

        version = self.framework_ir.queryMicroVersion()
        if (version != None):
            self.ui.label_version_micro_sw_version.setText(f"{version.major}.{version.minor} ({version.git_version})")


        self.updateFlashEnableUiState()
        self.readAndApplyStateToUI(True)

    def openFileNameDialog(self, title: str, name: str, extension: str):
        options: QFileDialog.Option = QFileDialog.Option(0)
        # options |= QFileDialog.DontUseNativeDialog
        fileName, _ = QFileDialog.getOpenFileName(self, title, "", name + " (*."+extension+");;All Files (*)", options=options)
        return fileName

    def updateFlashEnableUiState(self):
        stm32_fw_file_name = str(self.ui.lineEdit_stm32_fw_file_name.text())

        flashSTM32Enable = (not self.any_update_state_in_progress) and (self.framework_ir != None or self.framework_ir_bootloader != None) and (stm32_fw_file_name != "")

        self.ui.pushButton_update_stm32.setEnabled(flashSTM32Enable)


    @staticmethod
    def applyFramework_IR_StateToUi(ui: Main_Window_UI.Ui_Form, framework_ir_state: Optional[Six15_API.Response.Framework_IR_State]):
        enabled = framework_ir_state != None
        ui.state_val1.setEnabled(enabled)

        ui.state_val1.setText("N/A")

        if framework_ir_state != None:
            ui.state_val1.setText(f"{framework_ir_state.val1}")



    def hookEvents(self):
        self.ui.pushButton_clear_log.clicked.connect(self.clear_event_log_clicked)

        self.ui.pushButton_browse_stm32.clicked.connect(self.browse_button_stm32_clicked)
        self.ui.pushButton_update_stm32.clicked.connect(self.update_stm32_button_clicked)
        self.ui.lineEdit_stm32_fw_file_name.editingFinished.connect(self.filename_stm32_fw_edit_finished)

        self.ui.control_reboot.clicked.connect(self.button_reboot_clicked)
        self.ui.control_reboot_bootloader.clicked.connect(self.button_reboot_bootloader_clicked)

        self.ui.control_brightness_up.clicked.connect(self.brightness_up_clicked)
        self.ui.control_brightness_down.clicked.connect(self.brightness_down_clicked)

    def filename_stm32_fw_edit_finished(self):
        self.updateFlashEnableUiState()

    def filename_fpga_fw_edit_finished(self):
        self.updateFlashEnableUiState()

    def brightness_up_clicked(self):
        if (not self.framework_ir):
            Logger.error("Can't increase brightness, no Framework_IR connected")
            return
        brightness_result = self.framework_ir.sendAdjustBrightness(1)
        Logger.info(f"Increased brightness to:{brightness_result.brightness}")

    def brightness_down_clicked(self):
        if (not self.framework_ir):
            Logger.error("Can't decrease brightness, no Framework_IR connected")
            return
        brightness_result = self.framework_ir.sendAdjustBrightness(-1)
        Logger.info(f"Decreased brightness to:{brightness_result.brightness}")

    ##### End Helper Functions #####

    ##### Start UI Event Handlers #####

    def filename_stm32_fw_edit_finished(self):
        self.updateFlashEnableUiState()

    def clear_event_log_clicked(self):
        self.event_log_lines = ""
        self.ui.plainTextEdit_event_log.clear()

    def browse_button_stm32_clicked(self):
        fileName = self.openFileNameDialog("Select a STM32 DFU File", "DFU File", "dfu")
        if fileName:
            Logger.info(f"Selected DFU file:{fileName}")
            self.ui.lineEdit_stm32_fw_file_name.setText(fileName)
            self.updateFlashEnableUiState()

    def update_stm32_button_clicked(self):
        if (not self.framework_ir and not self.framework_ir_bootloader):
            Logger.error("Can't flash STM32, no Framework_IR or STM32 bootloader connected")
            return
        fw_file_name = str(self.ui.lineEdit_stm32_fw_file_name.text())
        if (not os.path.exists(fw_file_name)):
            Logger.critical_error(f"STM32 Firmware File: \"{fw_file_name}\" doesn't exist")
            return
        self.settings.setValue(Window.SETTING_STM32_FW_FILE_NAME, fw_file_name)

        self.any_update_state_in_progress = True
        self.updateFlashEnableUiState()
        Logger.info(f"STM32 Firmware Update Starting. File: {fw_file_name}")
        try:
            self.stopLogThread()
            if (self.framework_ir != None):
                self.framework_ir.rebootBootloader()
                QApplication.processEvents()
                time.sleep(Framework_IR.REBOOT_TO_DISCONNECT_DELAY_SECONDS)

            if (self.framework_ir_bootloader == None):
                delay_len = 0
                while delay_len < Framework_IR.REBOOT_TO_BOOTLOADER_DELAY_SECONDS:
                    time.sleep(0.1)
                    delay_len += 0.1
                    QApplication.processEvents()
                    if (self.framework_ir_bootloader != None):
                        break

            current_step_is_verify = None

            def stm32_fw_status_callback(finished: bool, is_verify: bool, percent_complete: float):
                nonlocal current_step_is_verify
                if (current_step_is_verify != is_verify):
                    if is_verify:
                        Logger.info("STM32 Firmware Update Starting Verify")
                    else:
                        Logger.info("STM32 Firmware Update Starting Flash")

                current_step_is_verify = is_verify
                self.ui.progress_bar_fw.setEnabled(True)
                self.ui.progress_bar_fw.setValue(percent_complete)
                # This avoids "not responding" in windows.
                QApplication.processEvents()

            verify_ok = STM32_Firmware_Update.flash_and_verify_STM32_FW(fw_file_name, True, True, stm32_fw_status_callback)
            if (verify_ok):
                Logger.info("STM32 Firmware Update Success. Verification: OK")
            else:
                Logger.critical_error("STM32 Firmware Update FAIL. Verification FAIL. Firmware is likely corrupt.")

        except Exception as err:
            error_msg = f"STM32 Firmware Update Failed: {err}\ntraceback:  {traceback.format_exc()}"
            Logger.critical_error(error_msg)

        self.any_update_state_in_progress = False
        self.startLogThread()
        self.updateFlashEnableUiState()

    def button_reboot_clicked(self):
        if (not self.framework_ir):
            Logger.error("Can't Reboot, no Framework_IR connected")
            return
        Logger.info("Reboot clicked")
        self.doReboot()

    def doReboot(self):
        self.stopLogThread()
        if (self.backgroundDeviceThread):
            self.backgroundDeviceThread.requestInterruption()
            self.backgroundDeviceThread.wait()
        self.backgroundDeviceThread = None
        self.framework_ir.reboot()
        QApplication.processEvents()
        self.onDeviceConnectionChange(None)
        time.sleep(Framework_IR.REBOOT_TO_DISCONNECT_DELAY_SECONDS)
        self.restartDeviceListenThread()
        self.startLogThread()

    def button_reboot_bootloader_clicked(self):
        if (not self.framework_ir):
            Logger.error("Can't Reboot to Bootloader, no Framework_IR connected")
            return
        Logger.info("Reboot Bootloader clicked")
        self.stopLogThread()
        if (self.backgroundDeviceThread):
            self.backgroundDeviceThread.requestInterruption()
            self.backgroundDeviceThread.wait()
        self.backgroundDeviceThread = None
        self.framework_ir.rebootBootloader()
        self.onDeviceConnectionChange(None)
        QApplication.processEvents()
        time.sleep(Framework_IR.REBOOT_TO_DISCONNECT_DELAY_SECONDS)
        self.restartDeviceListenThread()
        self.startLogThread()

    def readAndApplyStateToUI(self, doRead: bool):
        if doRead and self.framework_ir != None:
            self.framework_ir_state = self.framework_ir.queryFramework_IR_State()
        else:
            self.framework_ir_state = None

        Window.applyFramework_IR_StateToUi(self.ui, self.framework_ir_state)


    def read_from_hardware_clicked(self):
        if (not self.framework_ir):
            Logger.error("Can't Read from hardware, no Framework_IR connected")
            return

        self.readAndApplyStateToUI(False)
        # Show that the UI was cleared so it's clear that something changed.
        QApplication.processEvents()
        self.readAndApplyStateToUI(True)

    ##### END UI Event Handlers #####

##### Start non-class Functions #####


def run_cli() -> int:
    args = Framework_IR.parseForArgs()

    framework_ir_finder = Framework_IR_Finder()
    device = framework_ir_finder.getFramework_IR()

    if (device == None):
        ret = Framework_IR.handleArgsNoDevice(args)
        if (ret):
            Logger.warn('No Device found, exiting.')
        return ret

    ret = Framework_IR.handleArgs(device, args)
    device.close()
    return ret


def main():
    if (len(sys.argv) != 1):
        # Run the command line program if given command line args
        sys.exit(run_cli())
    else:
        app = QApplication(sys.argv)
        QApplication.setApplicationName(APPLICATION_NAME)

        def sigint_handler(*args):
            app.quit()

        signal.signal(signal.SIGINT, sigint_handler)

        timer = QTimer()
        timer.start(500)
        timer.timeout.connect(lambda: None)  # Let the interpreter run each 500 ms so it can process non-OS level signals.
        # app.setStyle('Windows')
        app.setStyle('Fusion')
        window = Window()
        window.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    main()

##### End non-class Functions #####
