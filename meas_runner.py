
# -*- coding: utf-8 -*-
"""
meas_runner.py
MeasurementRunner：量測背景執行緒（QThread）。
- 流程：對 i=0..7 依序 → relay.select_index(i) → dmm.measure → 判定 PASS/FAIL → emit。
- 只用 signal/slot 回主執行緒更新 UI；子執行緒不直接改控件。
- 新增 interval（每點間隔，秒），預設 0.5 s；在每點完成後 sleep(interval)。
- 選用 use_inst_limits：於 DMM 端設定 CALC:LIM（不影響程式端判定）。
"""
from __future__ import annotations
import logging
import time
from typing import List, Tuple, Optional
from PyQt5.QtCore import QThread, pyqtSignal
from relay import RelayController
from dmm import DmmClient, DmmError
from logger import Logger


class MeasurementRunner(QThread):
    rowMeasured = pyqtSignal(int, float, float, float, bool)  # index, value, lower, upper, result
    status = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal(str)  # csv_path

    def __init__(self, relay: RelayController, dmm: DmmClient,
                 limits: List[Tuple[float, float]], logger: Logger,
                 use_meas_once: bool = False, rng: Optional[float] = None,
                 nplc: Optional[float] = 1.0, interval: float = 0.5,
                 use_inst_limits: bool = False) -> None:
        super().__init__()
        self.relay = relay
        self.dmm = dmm
        self.limits = limits
        self.logger = logger
        self.use_meas_once = use_meas_once
        self.rng = rng
        self.nplc = nplc
        self.interval = max(0.0, float(interval))
        self.use_inst_limits = use_inst_limits

    def run(self) -> None:
        try:
            # DMM 設定（CONF + SENS:RANG/NPLC）
            if not self.use_meas_once:
                self.dmm.configure_dc_voltage(self.rng, self.nplc)

            total = 8
            for i in range(total):
                self.status.emit(f"掃描中：選通 Y{i}")
                try:
                    self.relay.select_index(i)
                except Exception as ex:
                    msg = f"Phidget select_index({i}) 失敗：{ex}"
                    logging.error(msg)
                    self.error.emit(msg)

                # 儀器端限值（選用）
                lower, upper = self.limits[i]
                if self.use_inst_limits:
                    try:
                        self.dmm.configure_limits(lower, upper, True)
                    except DmmError as ex:
                        logging.warning("CALC:LIM 設定失敗：%s（程式端仍會判定）", ex)

                # 量測
                try:
                    if self.use_meas_once:
                        v = self.dmm.measure_dc_voltage_once(self.rng, None)
                    else:
                        v = self.dmm.measure_dc_voltage()
                except DmmError as ex:
                    msg = f"DMM 量測失敗（Y{i}）：{ex}"
                    logging.error(msg)
                    self.error.emit(msg)
                    v = float('nan')

                result = (lower <= v <= upper) if (not (v != v)) else False  # nan 判為 False
                self.logger.add_row(i, v, lower, upper, result,
                                    error=None if result else ("NaN" if (v != v) else None))
                self.rowMeasured.emit(i, v, lower, upper, result)
                self.status.emit(f"掃描第 {i} 點完成")

                # 每點間隔（額外的穩定時間）
                time.sleep(self.interval)

            csv_path = self.logger.save_csv()
            self.finished.emit(csv_path)

        except Exception as ex:
            msg = f"Runner 未預期錯誤：{ex}"
            logging.error(msg)
            self.error.emit(msg)
        finally:
            # 收尾
            try:
                self.dmm.close()
            except Exception:
                pass
            try:
                self.relay.close()
            except Exception:
                pass
