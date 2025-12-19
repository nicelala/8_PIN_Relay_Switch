
# gui_main.py
# -*- coding: utf-8 -*-
"""
PyQt5 GUI（加入 settings.ini 命名 Y0..Y7）：
- 讀取 ./settings.ini 的 [Pins] Y0..Y7 名稱，顯示在 Pin 欄位（長字串顯示省略號…）
- 按鈕：Start（執行量測）、Reload INI（重載接腳名稱）
- 模擬模式、表格 PASS/FAIL 著色、Status、logs 輸出
- 表格欄位寬度控制：
    Pin 欄可伸展，其餘欄固定寬度（Value=90、Lower=60、Upper=60、Result=80）
    視窗變窄先出水平捲動，不壓縮固定欄位
"""
from __future__ import annotations
import sys
import os
import logging
import configparser
import importlib
import inspect
from datetime import datetime
from typing import List, Tuple
from PyQt5 import QtCore, QtGui, QtWidgets

from relay import RelayController
from dmm import DmmClient
from logger import Logger
import meas_runner  # 你改名的 runner 檔案，內含 MeasurementRunner

COL_PIN, COL_VAL, COL_LOW, COL_UP, COL_RES = range(5)
INI_PATH = os.path.join(os.path.abspath('.'), 'settings.ini')

# 固定欄位寬度（需求指定）
PIN_MIN_WIDTH = 120
VAL_WIDTH = 90
LOW_WIDTH = 60
UP_WIDTH = 60
RES_WIDTH = 80


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle('Phidget + Keysight 34410A 掃描工具（支援 INI 命名）')
        self.resize(980, 560)

        cw = QtWidgets.QWidget(self)
        self.setCentralWidget(cw)
        layout = QtWidgets.QVBoxLayout(cw)

        # DMM 參數區
        form = QtWidgets.QFormLayout()
        self.ip_edit = QtWidgets.QLineEdit('192.168.100.12')  # 依你的預設
        self.port_edit = QtWidgets.QLineEdit('5025')
        self.timeout_edit = QtWidgets.QLineEdit('1.0')
        self.range_edit = QtWidgets.QLineEdit('10')
        self.nplc_edit = QtWidgets.QLineEdit('1.0')
        self.interval_spin = QtWidgets.QDoubleSpinBox()
        self.interval_spin.setRange(0.0, 10.0)
        self.interval_spin.setDecimals(3)
        self.interval_spin.setSingleStep(0.1)
        self.interval_spin.setValue(0.5)  # 預設 0.5 s
        self.simulate_chk = QtWidgets.QCheckBox('Simulate（未接硬體時啟用）')
        self.inst_limit_chk = QtWidgets.QCheckBox('Enable instrument limit (CALC:LIM)')
        form.addRow('DMM IP', self.ip_edit)
        form.addRow('Port', self.port_edit)
        form.addRow('Timeout (s)', self.timeout_edit)
        form.addRow('Range (V)', self.range_edit)
        form.addRow('NPLC', self.nplc_edit)
        form.addRow('Interval (s)', self.interval_spin)
        form.addRow('', self.simulate_chk)
        form.addRow('', self.inst_limit_chk)
        layout.addLayout(form)

        # 表格
        self.table = QtWidgets.QTableWidget(8, 5)
        self.table.setHorizontalHeaderLabels(['Pin', 'Value', 'Lower', 'Upper', 'Result'])
        self.table.verticalHeader().setVisible(False)

        # === 重要修改：欄位寬度與捲動策略 ===
        hdr = self.table.horizontalHeader()
        # 讓 Pin 欄可互動調整（不使用 Stretch，以便視窗變窄時出水平捲動）
        hdr.setSectionResizeMode(COL_PIN, QtWidgets.QHeaderView.Interactive)
        # 其他欄位固定寬度
        hdr.setSectionResizeMode(COL_VAL, QtWidgets.QHeaderView.Fixed)
        hdr.setSectionResizeMode(COL_LOW, QtWidgets.QHeaderView.Fixed)
        hdr.setSectionResizeMode(COL_UP, QtWidgets.QHeaderView.Fixed)
        hdr.setSectionResizeMode(COL_RES, QtWidgets.QHeaderView.Fixed)
        # 不把最後一欄自動撐滿，避免 Stretch 行為導致不出捲動
        hdr.setStretchLastSection(False)

        # 設定固定欄位寬度
        self.table.setColumnWidth(COL_VAL, VAL_WIDTH)
        self.table.setColumnWidth(COL_LOW, LOW_WIDTH)
        self.table.setColumnWidth(COL_UP, UP_WIDTH)
        self.table.setColumnWidth(COL_RES, RES_WIDTH)
        # Pin 欄最小寬度（視窗太窄時，先出水平捲動）
        self.table.setColumnWidth(COL_PIN, PIN_MIN_WIDTH)

        # 讓 Pin 欄在視窗變動時填滿剩餘空間（透過自訂計算）
        # 同時保留使用者可以拖拉調整（Interactive 模式）
        self.table.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustIgnored)
        self.table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        # 避免換行；超長字串用省略號
        self.table.setWordWrap(False)
        self.table.setTextElideMode(QtCore.Qt.ElideRight)

        # 表格列高（可保留原先設定）
        self.table.verticalHeader().setDefaultSectionSize(42)
        layout.addWidget(self.table)

        # 控制列
        hl = QtWidgets.QHBoxLayout()
        self.reload_btn = QtWidgets.QPushButton('Reload INI')
        self.start_btn = QtWidgets.QPushButton('Start')
        self.status_lbl = QtWidgets.QLabel('待命')
        hl.addWidget(self.reload_btn)
        hl.addWidget(self.start_btn)
        hl.addStretch(1)
        hl.addWidget(self.status_lbl)
        layout.addLayout(hl)

        # 事件
        self.reload_btn.clicked.connect(self.on_reload_ini)
        self.start_btn.clicked.connect(self.on_start)
        self.runner = None  # type: MeasurementRunner | None

        # logging
        log_dir = os.path.join(os.path.abspath('.'), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_path = os.path.join(log_dir, f'{stamp}.log')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[
                logging.FileHandler(log_path, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        logging.info('Log file = %s', log_path)

        # 載入 INI 名稱 & 初始化表格
        self.pin_names: List[str] = self.load_pin_names()
        self.init_table()

        # 首次顯示後計算 Pin 欄寬（避免尚未佈局時 viewport 寬度不準）
        QtCore.QTimer.singleShot(0, self.update_pin_column_width)

    # ---------- INI 讀取 ----------
    def load_pin_names(self) -> List[str]:
        """從 settings.ini 讀取 [Pins] 的 Y0..Y7 名稱。若缺失則回傳空字串陣列。"""
        names = [''] * 8
        cfg = configparser.ConfigParser()
        try:
            if not os.path.exists(INI_PATH):
                logging.warning("找不到 settings.ini，將使用預設 Yi 顯示。")
                return names
            cfg.read(INI_PATH, encoding='utf-8')
            if 'Pins' not in cfg:
                logging.warning("settings.ini 缺少 [Pins] 區塊，將使用預設。")
                return names
            sec = cfg['Pins']
            for i in range(8):
                key = f'Y{i}'
                names[i] = sec.get(key, '').strip()
            logging.info("Pins 名稱載入完成：%s", names)
            return names
        except Exception as ex:
            logging.error("讀取 settings.ini 失敗：%s", ex)
            return names

    def init_table(self) -> None:
        # 初始化 Pin 欄（字串可能較長 → 禁止換行並用省略號；同時提供 tooltip 看完整字串）
        for i in range(8):
            title = self.pin_label(i)          # 單行顯示（\n 轉為 ' / '）
            pin_item = QtWidgets.QTableWidgetItem(title)
            pin_item.setFlags(QtCore.Qt.ItemIsEnabled)
            pin_item.setToolTip(self.pin_names[i].strip() or f"Y{i}")
            self.table.setItem(i, COL_PIN, pin_item)

            self.table.setItem(i, COL_VAL, QtWidgets.QTableWidgetItem(''))
            low_item = QtWidgets.QTableWidgetItem('-10')
            up_item = QtWidgets.QTableWidgetItem('10')
            self.table.setItem(i, COL_LOW, low_item)
            self.table.setItem(i, COL_UP, up_item)
            self.table.setItem(i, COL_RES, QtWidgets.QTableWidgetItem(''))

        # 初始化完後計算一次 Pin 欄寬
        self.update_pin_column_width()

    def pin_label(self, i: int) -> str:
        """若 INI 有名稱就顯示名稱；沒有就顯示 Y{i}（預設）。
        並將換行轉為單行避免自動換行。
        """
        name = self.pin_names[i].strip()
        name = name.replace('\n', ' / ').replace('\r', ' / ')
        return name if name else f"Y{i}"

    @QtCore.pyqtSlot()
    def on_reload_ini(self) -> None:
        """重新載入 settings.ini 並更新 Pin 欄位顯示。"""
        self.pin_names = self.load_pin_names()
        for i in range(8):
            text = self.pin_label(i)
            self.table.item(i, COL_PIN).setText(text)
            self.table.item(i, COL_PIN).setToolTip(self.pin_names[i].strip() or f"Y{i}")
        self.update_pin_column_width()

    # ---------- 新增：表格讀取上下限 ----------
    def limits_from_table(self) -> List[Tuple[float, float]]:
        limits: List[Tuple[float, float]] = []
        for i in range(8):
            try:
                lower = float(self.table.item(i, COL_LOW).text())
                upper = float(self.table.item(i, COL_UP).text())
            except Exception:
                lower, upper = float('-inf'), float('inf')
            limits.append((lower, upper))
        return limits

    # ---------- 新增：Start 事件（量測主流程） ----------
    @QtCore.pyqtSlot()
    def on_start(self) -> None:
        self.start_btn.setEnabled(False)
        self.status_lbl.setText('掃描中...')
        simulate = self.simulate_chk.isChecked()

        # Relay
        relay = RelayController(serial=None, simulate=simulate) if False else RelayController(simulate=simulate)

        # DMM
        dmm = DmmClient(
            host=self.ip_edit.text().strip() or '192.168.0.61',
            port=int(self.port_edit.text().strip() or '5025'),
            timeout=float(self.timeout_edit.text().strip() or '1.0'),
            simulate=simulate
        )
        try:
            dmm.connect()
        except Exception as ex:
            logging.error("DMM 連線失敗：%s → 進入 simulate 模式。", ex)
            dmm.simulate = True

        limits = self.limits_from_table()
        logger = Logger()
        logger.pin_names = self.pin_names[:]   # 傳入 INI 讀到的名稱
        try:
            rng = float(self.range_edit.text().strip())
        except Exception:
            rng = None
        try:
            nplc = float(self.nplc_edit.text().strip())
        except Exception:
            nplc = 1.0

        interval = float(self.interval_spin.value())
        use_inst_limits = bool(self.inst_limit_chk.isChecked())

        # 動態載入 MeasurementRunner（避免舊版簽名不相容）
        importlib.reload(meas_runner)
        RunnerClass = meas_runner.MeasurementRunner
        sig = inspect.signature(RunnerClass.__init__)
        kwargs = dict(use_meas_once=False, rng=rng, nplc=nplc)
        if 'interval' in sig.parameters:
            kwargs['interval'] = interval
        if 'use_inst_limits' in sig.parameters:
            kwargs['use_inst_limits'] = use_inst_limits

        self.runner = RunnerClass(relay, dmm, limits, logger, **kwargs)
        self.runner.rowMeasured.connect(self.on_row_measured)
        self.runner.status.connect(self.status_lbl.setText)
        self.runner.error.connect(self.on_error)
        self.runner.finished.connect(self.on_finished)
        self.runner.start()

    # ---------- 新增：量測更新 / 錯誤 / 完成 ----------
    @QtCore.pyqtSlot(int, float, float, float, bool)
    def on_row_measured(self, i: int, v: float, low: float, up: float, ok: bool) -> None:
        self.table.item(i, COL_VAL).setText(f"{v:.6f}" if v == v else '')
        item = self.table.item(i, COL_RES)
        item.setText('PASS' if ok else 'FAIL')
        color = QtGui.QColor('#88ff88') if ok else QtGui.QColor('#ff8888')
        for col in (COL_VAL, COL_RES):
            self.table.item(i, col).setBackground(QtGui.QBrush(color))

    @QtCore.pyqtSlot(str)
    def on_error(self, msg: str) -> None:
        self.status_lbl.setText(msg)

    @QtCore.pyqtSlot(str)
    def on_finished(self, csv_path: str) -> None:
        self.status_lbl.setText(f'完成：{csv_path}')
        self.start_btn.setEnabled(True)

    # ---------- 新增：Pin 欄寬計算與視窗/表格尺寸事件 ----------
    def update_pin_column_width(self) -> None:
        """將剩餘寬度全部給 Pin 欄；不足時維持最小寬度並產生水平捲動。"""
        if not self.table or not self.table.viewport():
            return
        vp_w = self.table.viewport().width()
        fixed_sum = (
            self.table.columnWidth(COL_VAL)
            + self.table.columnWidth(COL_LOW)
            + self.table.columnWidth(COL_UP)
            + self.table.columnWidth(COL_RES)
        )
        # 剩餘空間全部給 Pin；不足時維持最小寬度（水平捲動由 Qt 自動顯示）
        pin_w = max(vp_w - fixed_sum, PIN_MIN_WIDTH)
        self.table.setColumnWidth(COL_PIN, pin_w)

    def resizeEvent(self, e: QtGui.QResizeEvent) -> None:
        super().resizeEvent(e)
        # 視窗改變大小時更新 Pin 欄寬
        self.update_pin_column_width()

    def showEvent(self, e: QtGui.QShowEvent) -> None:
        super().showEvent(e)
        # 顯示後再計算一次，確保佈局完成
        QtCore.QTimer.singleShot(0, self.update_pin_column_width)


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
