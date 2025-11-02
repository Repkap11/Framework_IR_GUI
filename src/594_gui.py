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
from ui_device_watcher import OLED_2k_DeviceListenThread, OLED_2k_DeviceDisconnectThread
from lib_six15_api.stm32_bootloader_finder_thread import BootloaderListenThread, BootloaderDisconnectThread
from lib_six15_api.sys_exception_hook import SysExceptionHook
import part_numbers as PartNumbers
from oled_2k import OLED_2k
from oled_2k_finder import OLED_2k_Finder
from lib_six15_api.serial_log_watcher import Serial_LogWatcher
from oled_2k_log_watcher import OLED_2k_LogWatcher
import oled_2k_six15_api as Six15_API
from lib_six15_api.logger import Logger, LogLevel, LoggerImpl
import lib_six15_api.version
from firmware_update_thread import FPGA_FirmwareUpdateThread
from thread_debug import DEBUG_THREADS
import lib_six15_api.stm32_firmware_updater as STM32_Firmware_Update

APPLICATION_NAME: str = "OLEDWorks 2k"


class Window(QMainWindow):
    ui: Main_Window_UI.Ui_Form
    backgroundDeviceThread: Optional[QThread] = None
    backgroundBootloaderThread: Optional[QThread] = None
    oled_2k: Optional[OLED_2k] = None
    oled_2k_bootloader: Optional[usb.core.Device] = None
    any_update_state_in_progress: bool = False

    event_log_lines: str = ""
    event_log_selected_bay_number: Optional[int] = None

    settings: QSettings = QSettings(QSettings.Scope.UserScope, "Six15", APPLICATION_NAME)
    SETTING_STM32_FW_FILE_NAME: str = "stm32_fw_file_name"
    SETTING_FPGA_FW_FILE_NAME: str = "fpga_fw_file_name"

    ##### Start Class Override Functions #####

    def __init__(self):
        super().__init__()
        SysExceptionHook()
        self.setWindowTitle(f"OLED_2k GUI Version: {AppVersion.GIT_VERSION} - Part Number: {PartNumbers.GUI_PART_NUMBER}")
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
        if not url_path.endswith((".dfu", ".jed")):
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
            if fileName.endswith(".jed"):
                self.ui.lineEdit_fpga_fw_file_name.setText(fileName)
            if fileName.endswith(".dfu"):
                self.ui.lineEdit_stm32_fw_file_name.setText(fileName)
            self.updateFlashEnableUiState()

    def paintEvent(self, event: QPaintEvent) -> None:
        # Using showEvent here would be better, but it doesn't work. It must be too early.
        # Using a single shot QTimer in showEvent with a 0 timeout also doesn't work.
        # Using a non-0 value, like 50ms, works, but I hate it.#
        # Even paintEvent needs a 0 time event... whatever it works.
        if (not self.initial_show_called):
            self.initial_show_called = True
            QTimer.singleShot(0, lambda: self.ui.status_read_from_hardware.setFocus(Qt.FocusReason.OtherFocusReason))
            # self.ui.status_read_from_hardware.setFocus(Qt.FocusReason.TabFocusReason)
        super().paintEvent(event)

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

        if (self.oled_2k):
            self.oled_2k.close()
            self.oled_2k = None
        return super().closeEvent(event)

    ##### End Class Override Functions #####

    ##### Start Helper Functions #####

    def startLogThread(self):
        if True:
            self.backgroundLogThread: QThread = Serial_LogWatcher(Six15_API.VID_SIX15, Six15_API.PID_594)
        else:
            self.backgroundLogThread: QThread = OLED_2k_LogWatcher()
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

        self.backgroundDeviceThread = OLED_2k_DeviceListenThread(self.onDeviceConnectionChange)
        self.backgroundDeviceThread.start()

    def restartDeviceDisconnectThread(self):
        if self.backgroundDeviceThread:
            self.backgroundDeviceThread.requestInterruption()
            self.backgroundDeviceThread.wait()

        self.backgroundDeviceThread: QThread = OLED_2k_DeviceDisconnectThread(self.onDeviceConnectionChange, self.oled_2k)
        if (self.backgroundDeviceThread):
            self.backgroundDeviceThread.start()

    def setInitialState(self):
        # Ideally everything here would be set in QT Creator, but some things can't
        self.ui.label_version_gui_version.setText(f"{AppVersion.GIT_VERSION}")
        self.ui.lineEdit_stm32_fw_file_name.setText(self.settings.value(Window.SETTING_STM32_FW_FILE_NAME))
        self.ui.lineEdit_fpga_fw_file_name.setText(self.settings.value(Window.SETTING_FPGA_FW_FILE_NAME))

        for _, item in Six15_API.I2C_DEV_TO_BYTE.items():
            self.ui.control_i2c_device.addItem(item.prettyName, item)

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

    def onBootloaderConnectionChange(self, oled_2k_bootloader: Optional[usb.core.Device]):
        if (oled_2k_bootloader == self.oled_2k_bootloader):
            Logger.warn(f"onBootloaderConnectionChange: nothing changed:{oled_2k_bootloader}")
            # No need to take action if nothing changed
            return
        self.oled_2k_bootloader = oled_2k_bootloader
        if (self.isClosing):
            return
        self.updateStateFromBootloaderConnection()
        if (oled_2k_bootloader == None):
            Logger.info("#### Device Disconnected: STM32 Bootloader")
            self.backgroundBootloaderThread = BootloaderListenThread(self.onBootloaderConnectionChange)
        else:
            Logger.info("#### Device Connected: STM32 Bootloader")
            self.backgroundBootloaderThread = BootloaderDisconnectThread(self.onBootloaderConnectionChange)
        self.backgroundBootloaderThread.start()

    def onDeviceConnectionChange(self, oled_2k: OLED_2k):
        if (oled_2k == self.oled_2k):
            # No need to take action if nothing changed
            return

        if (self.oled_2k is not None):
            self.oled_2k.close()
            self.oled_2k = None
        self.oled_2k = oled_2k
        if (self.isClosing):
            return

        if (isinstance(self.backgroundLogThread, OLED_2k_LogWatcher)):
            self.backgroundLogThread.set_OLED_2k(self.oled_2k)

        if (oled_2k == None):
            Logger.info("#### Device Disconnected: OLED 2k Display")
        else:
            Logger.info("#### Device Connected: OLED 2k Display")

        if (oled_2k == None):
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
        ui.status_read_from_hardware.setEnabled(enabled)

        ui.pushButton_oled2k_button_1.setEnabled(enabled)
        ui.pushButton_oled2k_button_2.setEnabled(enabled)
        ui.pushButton_oled2k_button_3.setEnabled(enabled)
        ui.pushButton_oled2k_button_4.setEnabled(enabled)
        ui.pushButton_oled2k_button_5.setEnabled(enabled)
        ui.pushButton_oled2k_button_6.setEnabled(enabled)

        ui.label_version_fpga_version.setEnabled(enabled)
        ui.control_brightness_up.setEnabled(enabled)
        ui.control_brightness_down.setEnabled(enabled)
        ui.control_test_pattern_flat.setEnabled(enabled)
        ui.control_test_pattern_none.setEnabled(enabled)
        ui.control_test_pattern_smpte_color_bar.setEnabled(enabled)
        ui.control_test_pattern_100_color_bar.setEnabled(enabled)
        ui.control_test_pattern_mono_stair.setEnabled(enabled)
        ui.control_test_pattern_white_cross_on_black.setEnabled(enabled)
        ui.control_test_pattern_black_cross_on_white.setEnabled(enabled)
        ui.control_test_pattern_linear_ramp.setEnabled(enabled)
        ui.control_test_pattern_flat_r.setEnabled(enabled)
        ui.control_test_pattern_flat_g.setEnabled(enabled)
        ui.control_test_pattern_flat_b.setEnabled(enabled)
        ui.control_test_pattern_flat_slider.setEnabled(enabled)
        ui.control_test_pattern_flat_label.setEnabled(enabled)
        ui.control_test_pattern_disp_none.setEnabled(enabled)
        ui.control_test_pattern_disp_black.setEnabled(enabled)
        ui.control_test_pattern_disp_white.setEnabled(enabled)
        ui.control_i2c_read.setEnabled(enabled)
        ui.control_i2c_write.setEnabled(enabled)

    def clearStateFromDisconnect(self) -> None:
        if (self.oled_2k != None):
            Logger.error("Can't clearStateFromDisconnect, a OLED_2k is connected")
        self.ui.label_version_micro_sw_version.setText("N/A")
        self.ui.label_version_fpga_version.setText("N/A")
        self.updateFlashEnableUiState()
        self.ui.progress_bar_fw.setEnabled(False)
        self.ui.progress_bar_fw.setValue(0)
        self.readAndApplyStateToUI(False)
        Window.applyEnabledState(self.ui, False)

    def queryStateFromDevice(self) -> None:
        if (not self.oled_2k):
            Logger.error("Can't queryStateFromDevice, no OLED_2k connected")
            return

        version = self.oled_2k.queryMicroVersion()
        if (version != None):
            self.ui.label_version_micro_sw_version.setText(f"{version.major}.{version.minor} ({version.git_version})")

        fpga_version = self.oled_2k.queryFPGA_Version()
        if (fpga_version != None):
            self.ui.label_version_fpga_version.setText(f"{fpga_version.version}")
            self.ui.label_version_fpga_version.setText(f"{fpga_version.git_version if fpga_version.git_version != None else 'Unknown'}")


        self.updateFlashEnableUiState()
        self.readAndApplyStateToUI(True)

    def openFileNameDialog(self, title: str, name: str, extension: str):
        options: QFileDialog.Option = QFileDialog.Option(0)
        # options |= QFileDialog.DontUseNativeDialog
        fileName, _ = QFileDialog.getOpenFileName(self, title, "", name + " (*."+extension+");;All Files (*)", options=options)
        return fileName

    def updateFlashEnableUiState(self):
        stm32_fw_file_name = str(self.ui.lineEdit_stm32_fw_file_name.text())
        fpga_fw_file_name = str(self.ui.lineEdit_fpga_fw_file_name.text())

        flashSTM32Enable = (not self.any_update_state_in_progress) and (self.oled_2k != None or self.oled_2k_bootloader != None) and (stm32_fw_file_name != "")
        flashFPGAEnable = (not self.any_update_state_in_progress) and (self.oled_2k != None) and (fpga_fw_file_name != "")

        self.ui.pushButton_update_stm32.setEnabled(flashSTM32Enable)
        self.ui.pushButton_update_fpga.setEnabled(flashFPGAEnable)

    @staticmethod
    def applyOLED_2k_StateToUi(ui: Main_Window_UI.Ui_Form, oled_display_state: Optional[Six15_API.Response.OLED_DisplayState]):
        enabled = oled_display_state != None
        ui.state_oled_brightness.setEnabled(enabled)
        ui.state_oled_temperature.setEnabled(enabled)
        ui.state_oled_serial_number.setEnabled(enabled)

        ui.state_oled_brightness.setText("N/A")
        ui.state_oled_temperature.setText("N/A")
        ui.state_oled_serial_number.setText("N/A")

        if oled_display_state != None:
            ui.state_oled_temperature.setText(f"{oled_display_state.brightness}")
            ui.state_oled_temperature.setText(f"{oled_display_state.temperature_value}")
            ui.state_oled_serial_number.setText(f"{oled_display_state.serial_number}")


    @staticmethod
    def applyHDMI_StateToUi(ui: Main_Window_UI.Ui_Form, hdmi_state: Optional[Six15_API.Response.HDMI_State]):
        hasState = hdmi_state != None

        ui.state_hdmi_input_source_locked.setEnabled(hasState)
        ui.state_hdmi_resolution.setEnabled(hasState)
        ui.state_hdmi_fps.setEnabled(hasState)
        ui.state_hdmi_clock_freq.setEnabled(hasState)
        ui.state_hdmi_total_resolution.setEnabled(hasState)

        ui.state_hdmi_input_source_locked.setText("N/A")
        ui.state_hdmi_resolution.setText("N/A")
        ui.state_hdmi_fps.setText("N/A")
        ui.state_hdmi_clock_freq.setText("N/A")
        ui.state_hdmi_total_resolution.setText("N/A")

        if hasState:
            ui.state_hdmi_input_source_locked.setText(f"{hdmi_state.input_source_locked != 0}")
            if hdmi_state.input_source_locked:
                ui.state_hdmi_resolution.setText(f"{hdmi_state.active_width}x{hdmi_state.active_height}")
                ui.state_hdmi_fps.setText(f"{hdmi_state.fps:.2f}")
                ui.state_hdmi_clock_freq.setText(f"{hdmi_state.clock_freq:.2f} MHz")
                ui.state_hdmi_total_resolution.setText(f"{hdmi_state.total_width}x{hdmi_state.total_height}")


    @staticmethod
    def applyEDID_StateToUI(ui: Main_Window_UI.Ui_Form, edid_state: Optional[Six15_API.Response.EDID_State]):
        hasState = edid_state != None

        ui.state_edid_num_i2c_start.setEnabled(hasState)
        ui.state_edid_e_edid_page_addr_accessed.setEnabled(hasState)
        ui.state_edid_error_flag.setEnabled(hasState)

        ui.state_edid_num_i2c_start.setText("N/A")
        ui.state_edid_e_edid_page_addr_accessed.setText("N/A")
        ui.state_edid_error_flag.setText("N/A")

        if hasState:
            ui.state_edid_num_i2c_start.setText(f"{edid_state.num_start_conditions}")
            ui.state_edid_e_edid_page_addr_accessed.setText(f"{True if edid_state.e_edid_page_addr_accessed else False}")
            ui.state_edid_error_flag.setText(f"{True if edid_state.error_flag else False}")


    def hookEvents(self):
        self.ui.pushButton_clear_log.clicked.connect(self.clear_event_log_clicked)

        self.ui.pushButton_browse_stm32.clicked.connect(self.browse_button_stm32_clicked)
        self.ui.pushButton_update_stm32.clicked.connect(self.update_stm32_button_clicked)
        self.ui.pushButton_browse_fpga.clicked.connect(self.browse_button_fpga_clicked)
        self.ui.pushButton_update_fpga.clicked.connect(self.update_fpga_button_clicked)
        self.ui.lineEdit_stm32_fw_file_name.editingFinished.connect(self.filename_stm32_fw_edit_finished)
        self.ui.lineEdit_fpga_fw_file_name.editingFinished.connect(self.filename_fpga_fw_edit_finished)

        self.ui.control_reboot.clicked.connect(self.button_reboot_clicked)
        self.ui.control_reboot_bootloader.clicked.connect(self.button_reboot_bootloader_clicked)
        self.ui.status_read_from_hardware.clicked.connect(self.read_from_hardware_clicked)

        self.ui.control_brightness_up.clicked.connect(self.brightness_up_clicked)
        self.ui.control_brightness_down.clicked.connect(self.brightness_down_clicked)

        self.ui.control_i2c_read.clicked.connect(self.control_i2c_read_clicked)
        self.ui.control_i2c_address.returnPressed.connect(self.control_i2c_read_clicked_no_err)
        self.ui.control_i2c_write.clicked.connect(self.control_i2c_write_clicked)
        self.ui.control_i2c_write_value.returnPressed.connect(self.control_i2c_write_clicked_no_err)

        self.ui.control_test_pattern_flat.clicked.connect(self.sendFlatAndColor)
        self.ui.control_test_pattern_none.clicked.connect(lambda: self.send_I2C_TestPattern(1))
        self.ui.control_test_pattern_smpte_color_bar.clicked.connect(lambda: self.send_I2C_TestPattern(2))
        self.ui.control_test_pattern_100_color_bar.clicked.connect(lambda: self.send_I2C_TestPattern(3))
        self.ui.control_test_pattern_mono_stair.clicked.connect(lambda: self.send_I2C_TestPattern(4))
        self.ui.control_test_pattern_white_cross_on_black.clicked.connect(lambda: self.send_I2C_TestPattern(5))
        self.ui.control_test_pattern_black_cross_on_white.clicked.connect(lambda: self.send_I2C_TestPattern(6))
        self.ui.control_test_pattern_linear_ramp.clicked.connect(self.send_I2C_DispTestPatternLinearRamp)

        self.ui.control_test_pattern_flat_r.clicked.connect(self.send_I2C_TestPattern_Color)
        self.ui.control_test_pattern_flat_g.clicked.connect(self.send_I2C_TestPattern_Color)
        self.ui.control_test_pattern_flat_b.clicked.connect(self.send_I2C_TestPattern_Color)
        self.ui.control_test_pattern_flat_slider.valueChanged.connect(self.control_test_pattern_flat_slider_moved)

        self.ui.control_test_pattern_disp_black.clicked.connect(self.send_I2C_DispTestPatternBlack)
        self.ui.control_test_pattern_disp_white.clicked.connect(self.send_I2C_DispTestPatternWhite)
        self.ui.control_test_pattern_disp_none.clicked.connect(self.send_I2C_DispTestPatternNone)

        self.ui.pushButton_oled2k_button_1.clicked.connect(lambda: self.sendDebugAction(1))
        self.ui.pushButton_oled2k_button_2.clicked.connect(lambda: self.sendDebugAction(2))
        self.ui.pushButton_oled2k_button_3.clicked.connect(lambda: self.sendDebugAction(3))
        self.ui.pushButton_oled2k_button_4.clicked.connect(lambda: self.sendDebugAction(4))
        self.ui.pushButton_oled2k_button_5.clicked.connect(lambda: self.sendDebugAction(5))
        self.ui.pushButton_oled2k_button_6.clicked.connect(lambda: self.sendDebugAction(6))

    def sendDebugAction(self, index: int):
        if (not self.oled_2k):
            Logger.error(f"Can't do debug action {index}, no OLED_2k connected")
            return
        self.oled_2k.sendDebugAction(index)

    def sendFlatAndColor(self):
        self.send_I2C_TestPattern_Color()
        self.control_test_pattern_flat_slider_moved()
        self.send_I2C_TestPattern(0)

    def filename_stm32_fw_edit_finished(self):
        self.updateFlashEnableUiState()

    def filename_fpga_fw_edit_finished(self):
        self.updateFlashEnableUiState()

    def brightness_up_clicked(self):
        if (not self.oled_2k):
            Logger.error("Can't increase brightness, no OLED_2k connected")
            return
        brightness_result = self.oled_2k.sendAdjustBrightness(1)
        Logger.info(f"Increased brightness to:{brightness_result.brightness}")

    def brightness_down_clicked(self):
        if (not self.oled_2k):
            Logger.error("Can't decrease brightness, no OLED_2k connected")
            return
        brightness_result = self.oled_2k.sendAdjustBrightness(-1)
        Logger.info(f"Decreased brightness to:{brightness_result.brightness}")

    def control_i2c_read_clicked_no_err(self):
        if (not self.oled_2k):
            return
        self.control_i2c_read_clicked()

    def control_i2c_read_clicked(self):
        if (not self.oled_2k):
            Logger.error("Can't I2C read, no OLED_2k connected")
            return
        index = self.ui.control_i2c_device.currentIndex()
        itemData: Six15_API.I2C_Info = self.ui.control_i2c_device.itemData(index)

        addr_str = str(self.ui.control_i2c_address.text())
        if (addr_str == ""):
            addr_str = "0"
            self.ui.control_i2c_address.setText(addr_str)
        addr = int(addr_str,  0)

        result = self.oled_2k.sendI2C_CMD(0, itemData, addr, 0)
        if (result.value < 256):
            ascii_value = ascii(int(result.value).to_bytes(2).decode("utf-8", errors="replace"))
        else:
            ascii_value = "N/A"
            # ascii_value_high = ascii(int((result.value & 0xFF00)>>8).to_bytes().decode("utf-8", errors="replace"))
            # ascii_value_low = ascii(int(result.value & 0x00FF).to_bytes().decode("utf-8", errors="replace"))
            # ascii_value = ascii_value_high + ascii_value_low
        
        val_str = f"0x{result.value:04X} {result.value} {ascii_value}"
        self.ui.control_i2c_read_value.setText(val_str)
        Logger.info(f"I2C Read  {itemData.prettyName} addr:0x{addr:04X} val:{val_str}")
        if (self.ui.control_i2c_addr_auto_inc.isChecked()):
            self.ui.control_i2c_address.setText(f"0x{addr+1:02X}")

    def control_i2c_write_clicked_no_err(self):
        if (not self.oled_2k):
            return
        self.control_i2c_write_clicked()

    def control_i2c_write_clicked(self):
        if (not self.oled_2k):
            Logger.error("Can't I2C write, no OLED_2k connected")
            return
        index = self.ui.control_i2c_device.currentIndex()
        itemData: Six15_API.I2C_Info = self.ui.control_i2c_device.itemData(index)

        addr_str = str(self.ui.control_i2c_address.text())
        if (addr_str == ""):
            addr_str = "0"
            self.ui.control_i2c_address.setText(addr_str)
        addr = int(addr_str,  0)

        value_str = str(self.ui.control_i2c_write_value.text())
        if (value_str == ""):
            value_str = "0"
            self.ui.control_i2c_write_value.setText(value_str)
        value = int(value_str,  0)

        self.oled_2k.sendI2C_CMD(1, itemData, addr, value)
        val_str = f"0x{value:02X} {value}"
        Logger.info(f"I2C Write {itemData.prettyName} addr:0x{addr:04X} val:{val_str}")
        if (self.ui.control_i2c_addr_auto_inc.isChecked()):
            self.ui.control_i2c_address.setText(f"0x{addr+1:02X}")

    def control_test_pattern_flat_slider_moved(self):
        value = self.ui.control_test_pattern_flat_slider.value()
        self.ui.control_test_pattern_flat_label.setText(str(value))
        if (not self.ui.control_test_pattern_flat_slider.isEnabled()):
            return
        if (not self.oled_2k):
            Logger.error("Can't set test pattern level, no OLED_2k connected")
            return

        self.oled_2k.sendI2C_CMD(1, Six15_API.I2C_DEV_TO_BYTE["fpga"], 0x22, value)

    def send_I2C_TestPattern(self, pattern_sel):
        if (not self.oled_2k):
            Logger.error("Can't set test pattern, no OLED_2k connected")
            return
        self.oled_2k.sendI2C_CMD(1, Six15_API.I2C_DEV_TO_BYTE["fpga"], 0x20, pattern_sel)

        # if command is setting to 'none' also clear the linear ramp register
        if (pattern_sel == 1):
            self.oled_2k.sendI2C_CMD(1, Six15_API.I2C_DEV_TO_BYTE["fpga"], 0xF1, 0x00)

    def send_I2C_TestPattern_Color(self):
        if (not self.oled_2k):
            Logger.error("Can't set test pattern color, no OLED_2k connected")
            return
        enable_r = self.ui.control_test_pattern_flat_r.isChecked()
        enable_g = self.ui.control_test_pattern_flat_g.isChecked()
        enable_b = self.ui.control_test_pattern_flat_b.isChecked()
        enable_rgb = (enable_r << 2) | (enable_g << 1) | (enable_b << 0)
        self.oled_2k.sendI2C_CMD(1, Six15_API.I2C_DEV_TO_BYTE["fpga"], 0x21, enable_rgb)

    def send_I2C_DispTestPatternBlack(self):
        if (not self.oled_2k):
            Logger.error("Can't set test pattern, no OLED_2k connected")
            return
        self.oled_2k.sendI2C_CMD(1, Six15_API.I2C_DEV_TO_BYTE["sxga_display_device"], 0x1A, 0x0D)
        self.oled_2k.sendI2C_CMD(1, Six15_API.I2C_DEV_TO_BYTE["sxga_display_device"], 0x1E, 0x00)

    def send_I2C_DispTestPatternWhite(self):
        if (not self.oled_2k):
            Logger.error("Can't set test pattern, no OLED_2k connected")
            return
        self.oled_2k.sendI2C_CMD(1, Six15_API.I2C_DEV_TO_BYTE["sxga_display_device"], 0x1A, 0x0D)
        self.oled_2k.sendI2C_CMD(1, Six15_API.I2C_DEV_TO_BYTE["sxga_display_device"], 0x1E, 0x77)

    def send_I2C_DispTestPatternNone(self):
        if (not self.oled_2k):
            Logger.error("Can't set test pattern, no OLED_2k connected")
            return
        self.oled_2k.sendI2C_CMD(1, Six15_API.I2C_DEV_TO_BYTE["sxga_display_device"], 0x1A, 0x00)

    def send_I2C_DispTestPatternLinearRamp(self):
        if (not self.oled_2k):
            Logger.error("Can't set test pattern, no OLED_2k connected")
            return
        # Disable the FPGA pattern generation (set to NONE)
        self.oled_2k.sendI2C_CMD(1, Six15_API.I2C_DEV_TO_BYTE["fpga"], 0x20, 1)
        # set register to enable the linear ramp
        self.oled_2k.sendI2C_CMD(1, Six15_API.I2C_DEV_TO_BYTE["fpga"], 0xF1, 0x01)

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

    def browse_button_fpga_clicked(self):
        fileName = self.openFileNameDialog("Select an FPGA FW File", "JED File", "jed")
        if fileName:
            Logger.info(f"Flashing jed:{fileName}")
            self.ui.lineEdit_fpga_fw_file_name.setText(fileName)
            self.updateFlashEnableUiState()

    def update_stm32_button_clicked(self):
        if (not self.oled_2k and not self.oled_2k_bootloader):
            Logger.error("Can't flash STM32, no OLED_2k or STM32 bootloader connected")
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
            if (self.oled_2k != None):
                self.oled_2k.rebootBootloader()
                QApplication.processEvents()
                time.sleep(OLED_2k.REBOOT_TO_DISCONNECT_DELAY_SECONDS)

            if (self.oled_2k_bootloader == None):
                delay_len = 0
                while delay_len < OLED_2k.REBOOT_TO_BOOTLOADER_DELAY_SECONDS:
                    time.sleep(0.1)
                    delay_len += 0.1
                    QApplication.processEvents()
                    if (self.oled_2k_bootloader != None):
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

    def update_fpga_button_clicked(self):
        if (not self.oled_2k):
            Logger.error("Can't flash FPGA, no OLED_2k connected")
            return
        fw_file_name = str(self.ui.lineEdit_fpga_fw_file_name.text())
        if (not os.path.exists(fw_file_name)):
            Logger.critical_error(f"FPGA Firmware File: \"{fw_file_name}\" doesn't exist")
            return
        self.settings.setValue(Window.SETTING_FPGA_FW_FILE_NAME, fw_file_name)

        self.any_update_state_in_progress = True
        self.ui.lineEdit_fpga_fw_file_name.setFocus(Qt.FocusReason.OtherFocusReason)
        self.updateFlashEnableUiState()

        def fpga_fw_status_callback(finished: bool, percent_complete: float):
            if (not self.oled_2k):
                return
            self.ui.progress_bar_fw.setEnabled(True)
            self.ui.progress_bar_fw.setValue(percent_complete)
            if (finished):
                # Reboot so the new firmware is applied
                self.doReboot()
                self.any_update_state_in_progress = False
                self.updateFlashEnableUiState()

        self.firmwareUpdateThread = FPGA_FirmwareUpdateThread(fw_file_name, fpga_fw_status_callback, self.oled_2k)
        self.firmwareUpdateThread.start()

    def button_reboot_clicked(self):
        if (not self.oled_2k):
            Logger.error("Can't Reboot, no OLED_2k connected")
            return
        Logger.info("Reboot clicked")
        self.doReboot()

    def doReboot(self):
        self.stopLogThread()
        if (self.backgroundDeviceThread):
            self.backgroundDeviceThread.requestInterruption()
            self.backgroundDeviceThread.wait()
        self.backgroundDeviceThread = None
        self.oled_2k.reboot()
        QApplication.processEvents()
        self.onDeviceConnectionChange(None)
        time.sleep(OLED_2k.REBOOT_TO_DISCONNECT_DELAY_SECONDS)
        self.restartDeviceListenThread()
        self.startLogThread()

    def button_reboot_bootloader_clicked(self):
        if (not self.oled_2k):
            Logger.error("Can't Reboot to Bootloader, no OLED_2k connected")
            return
        Logger.info("Reboot Bootloader clicked")
        self.stopLogThread()
        if (self.backgroundDeviceThread):
            self.backgroundDeviceThread.requestInterruption()
            self.backgroundDeviceThread.wait()
        self.backgroundDeviceThread = None
        self.oled_2k.rebootBootloader()
        self.onDeviceConnectionChange(None)
        QApplication.processEvents()
        time.sleep(OLED_2k.REBOOT_TO_DISCONNECT_DELAY_SECONDS)
        self.restartDeviceListenThread()
        self.startLogThread()

    def readAndApplyStateToUI(self, doRead: bool):
        if doRead and self.oled_2k != None:
            self.oled_display_state = self.oled_2k.queryOLED_DisplayState()
            self.hdmi_state = self.oled_2k.queryHDMI_State()
            self.edid_state = self.oled_2k.queryEDID_State()

        else:
            self.oled_display_state = None
            self.hdmi_state = None
            self.edid_state = None

        Window.applyOLED_2k_StateToUi(self.ui, self.oled_display_state)
        Window.applyHDMI_StateToUi(self.ui, self.hdmi_state)
        Window.applyEDID_StateToUI(self.ui, self.edid_state)


    def read_from_hardware_clicked(self):
        if (not self.oled_2k):
            Logger.error("Can't Read from hardware, no OLED_2k connected")
            return

        self.readAndApplyStateToUI(False)
        # Show that the UI was cleared so it's clear that something changed.
        QApplication.processEvents()
        self.readAndApplyStateToUI(True)

    ##### END UI Event Handlers #####

##### Start non-class Functions #####


def run_cli() -> int:
    args = OLED_2k.parseForArgs()

    oled_2k_finder = OLED_2k_Finder()
    device = oled_2k_finder.getOLED_2k()

    if (device == None):
        ret = OLED_2k.handleArgsNoDevice(args)
        if (ret):
            Logger.warn('No Device found, exiting.')
        return ret

    ret = OLED_2k.handleArgs(device, args)
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
