# -*- coding: utf-8 -*-
"""
relay.py

RelayController：使用 Phidget22 DigitalOutput 控制 SN74LS138 的 ABC 線路。
通道對應：0→A, 1→B, 2→C（A=LSB、C=MSB）。索引 index = A + 2*B + 4*C。

實作要點：
- openWaitForAttachment(5000) 以阻塞方式開啟（比非阻塞 open() 更簡單，避免未附加時就下指令）。
- select_index(i)：內部位元轉換後 setState(True/False)，機械繼電器切換後 sleep 20 ms 再進行量測。
- 僅使用 setState()；不要使用 DutyCycle（對機械繼電器不建議 PWM）。
- 支援 simulate 模式（未接硬體時仍可執行）。

此設計與使用者提供的 ls138_scan.py 一致：A/B/C 採 0/1/2 通道與 20ms 延遲。參考見 gui 說明文件。
"""
from __future__ import annotations
import time
import logging
from typing import Optional

try:
    from Phidget22.PhidgetException import PhidgetException
    from Phidget22.Devices.DigitalOutput import DigitalOutput
    _PHIDGET_AVAILABLE = True
except Exception:
    _PHIDGET_AVAILABLE = False
    PhidgetException = Exception  # type: ignore
    DigitalOutput = object        # type: ignore


class RelayController:
    """Phidget22 三路數位輸出控制器，用於選通 SN74LS138 的 A/B/C。

    通道：0→A、1→B、2→C。
    """
    def __init__(self, serial: Optional[int] = None, simulate: bool = False) -> None:
        self.serial = serial
        self.simulate = simulate or (not _PHIDGET_AVAILABLE)
        self._chA = None
        self._chB = None
        self._chC = None
        if not self.simulate:
            try:
                self._chA = DigitalOutput(); self._chA.setChannel(0)
                self._chB = DigitalOutput(); self._chB.setChannel(1)
                self._chC = DigitalOutput(); self._chC.setChannel(2)
                if serial is not None:
                    self._chA.setDeviceSerialNumber(serial)
                    self._chB.setDeviceSerialNumber(serial)
                    self._chC.setDeviceSerialNumber(serial)
                # 阻塞等待附加
                self._chA.openWaitForAttachment(5000)
                self._chB.openWaitForAttachment(5000)
                self._chC.openWaitForAttachment(5000)
                logging.info("Phidget DigitalOutput 0/1/2 已附加（A/B/C）。")
            except PhidgetException as ex:
                logging.error("Phidget 開啟失敗：%s → 進入 simulate 模式。", ex)
                self.simulate = True
        else:
            logging.warning("Phidget22 不可用或 simulate=True → 使用模擬模式。")

    def select_index(self, i: int) -> None:
        """選通索引 i (0..7)。
        內部將 i 轉為 A/B/C 位元（A=LSB、B=次位、C=MSB），然後 setState。
        由於外接的是機械繼電器，切換後 sleep 20 ms 再量測。
        """
        if not (0 <= i <= 7):
            raise ValueError("index 必須在 0..7")
        a = bool(i & 0b001)  # A=LSB
        b = bool(i & 0b010)  # B
        c = bool(i & 0b100)  # C=MSB
        logging.debug("select_index(%d) → A=%d B=%d C=%d", i, int(a), int(b), int(c))
        if self.simulate:
            # 只有等待，模擬切換
            time.sleep(0.02)
        else:
            assert self._chA and self._chB and self._chC
            self._chA.setState(a)
            self._chB.setState(b)
            self._chC.setState(c)
            time.sleep(0.02)

    def close(self) -> None:
        if self.simulate:
            return
        try:
            assert self._chA and self._chB and self._chC
            self._chA.close(); self._chB.close(); self._chC.close()
        except Exception:
            pass
