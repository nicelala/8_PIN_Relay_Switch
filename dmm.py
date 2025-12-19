
# -*- coding: utf-8 -*-
"""
dmm.py
DmmClient：使用純 socket（SCPI over TCP）連 Keysight 34410A。
- 連線參數：IP=192.168.0.61、Port=5025（所有 SCPI 字串以 '\n' 結束；儀器回應亦以 '\n' 結束）。
- 每點 timeout 預設 1 秒；逾時/中斷要丟出例外，由上層統一記 Log。
- 提供 configure_dc_voltage(range,nplc) 與 measure_dc_voltage()；主流程採 *CLS + CONF:VOLT:DC + READ?。
- 可選：measure_dc_voltage_once() 以 MEAS:VOLT:DC? 一次到位。
- 可選：configure_limits(lower, upper, enable) 對儀器端啟用 CALC:LIM（若需同步硬體判定）。

SCPI 為何這樣下：
- *CLS 清空狀態與錯誤佇列；避免殘留影響。[3](https://www.keysight.com/us/en/assets/7018-02044/white-papers-archived/5990-3515.pdf)
- CONF:VOLT:DC 設定量測功能為 DCV；再以 SENS:VOLT:DC:RANG 與 SENS:VOLT:DC:NPLC 控制量程與整合時間。[4](https://www.keysight.com/us/en/assets/9018-05586/user-manuals/9018-05586.pdf)
- READ? 在已設定的量測條件下觸發並回傳一次讀值；MEAS:VOLT:DC? 可「一次到位」含暫時設定。[3](https://www.keysight.com/us/en/assets/7018-02044/white-papers-archived/5990-3515.pdf)
- Keysight 儀器標準以 5025 為 SCPI socket port；字串需以 '\n' 結束，回應亦以 '\n' 結束。[5](https://www.keysight.com/us/en/lib/resources/user-manuals/direct-instrument-connection-using-lan-572739.html)
"""
from __future__ import annotations
import socket
import logging
import random
from typing import Optional


class DmmError(RuntimeError):
    pass


class DmmClient:
    def __init__(self, host: str = '192.168.0.61', port: int = 5025,
                 timeout: float = 1.0, simulate: bool = False) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.simulate = simulate
        self._sock: Optional[socket.socket] = None
        self._last_value = None  # 可選：保存最近一次讀值
        self._limits = (None, None, False)  # (lower, upper, enable)


    def connect(self) -> None:
        if self.simulate:
            logging.warning("DMM 使用模擬模式（隨機 ±10V）。")
            return
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            s.connect((self.host, self.port))
            self._sock = s
            logging.info("DMM 已連線：%s:%d", self.host, self.port)
        except Exception as ex:
            raise DmmError(f"DMM 連線失敗：{ex}")

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def write(self, cmd: str) -> None:
        if self.simulate:
            return
        if not self._sock:
            raise DmmError("DMM 尚未連線")
        data = (cmd + '\n').encode('ascii')
        try:
            self._sock.sendall(data)
        except Exception as ex:
            raise DmmError(f"Socket 送出失敗：{ex}")

    def read_line(self) -> str:
        if self.simulate:
            # 模擬儀器回傳一行字串，以 '\n' 結束
            return f"{random.uniform(-10, 10):.6f}\n"
        if not self._sock:
            raise DmmError("DMM 尚未連線")
        chunks = []
        try:
            while True:
                b = self._sock.recv(1)
                if not b:
                    raise DmmError("Socket 中斷")
                chunks.append(b)
                if b == b'\n':
                    break
        except socket.timeout:
            raise DmmError("讀取逾時")
        except Exception as ex:
            raise DmmError(f"讀取失敗：{ex}")
        return b''.join(chunks).decode('ascii')

    # ===== 量測設定 =====
    def configure_dc_voltage(self, rng: Optional[float] = None,
                             nplc: Optional[float] = 1.0) -> None:
        """設定 DCV 量測。
        - rng：SENS:VOLT:DC:RANG <range>，若 None 則由儀器自動量程。
        - nplc：SENS:VOLT:DC:NPLC <nplc>；NPLC（每電源週期整合時間）影響解析度/速度。
          例如 50 Hz 時 1 NPLC ≈ 20 ms；60 Hz 時 ≈ 16.67 ms。[4](https://www.keysight.com/us/en/assets/9018-05586/user-manuals/9018-05586.pdf)
        """
        self.write('*CLS')
        self.write('CONF:VOLT:DC')
        if rng is not None:
            self.write(f'SENS:VOLT:DC:RANG {rng}')
        if nplc is not None:
            self.write(f'SENS:VOLT:DC:NPLC {nplc}')
        
    def configure_limits(self, lower, upper, enable=True):
        # 1) 選限值功能 + 開啟計算
        self.write('CALC:FUNC LIM')
        self.write(f'CALC:STAT {"ON" if enable else "OFF"}')
        # 2) 設定下限/上限（None 就用 MIN/MAX）
        self.write('CALC:LIM:LOW MIN' if lower is None else f'CALC:LIM:LOW {lower}')
        self.write('CALC:LIM:UPP MAX' if upper is None else f'CALC:LIM:UPP {upper}')

    def clear_limits(self):
        # 關掉計算並回到一般模式
        self.write('CALC:STAT OFF')
        self.write('CALC:FUNC NULL')

    def query_limit_fail(self) -> bool:
        # 優先嘗試問儀器：有沒有 Fail？
        # 有的機型支援：CALC:LIM:FAIL? → 1=Fail, 0=Pass
        try:
            return int(float(self.query('CALC:LIM:FAIL?'))) == 1
        except Exception:
            # 若不支援，改看 Questionable Data Register：
            # bit 11（2048）=低限失敗、bit 12（4096）=高限失敗
            cond = int(float(self.query('STAT:QUES:COND?')))
            return bool(cond & 2048 or cond & 4096)

    # ===== 量測 =====
    def measure_dc_voltage(self) -> float:
        """在既有設定下以 READ? 取一次值。"""
        if self.simulate:
            v = random.uniform(-10, 10)
            return float(f"{v:.6f}")
        self.write('READ?')
        line = self.read_line().strip()
        try:
            return float(line)
        except ValueError as ex:
            raise DmmError(f"解析讀值失敗：{line} → {ex}")

    def measure_dc_voltage_once(self, rng: Optional[float] = None,
                                res: Optional[float] = None) -> float:
        """使用 MEAS:VOLT:DC? 一次到位（可選 range/resolution）。"""
        if self.simulate:
            v = random.uniform(-10, 10)
            return float(f"{v:.6f}")
        if rng is None and res is None:
            self.write('MEAS:VOLT:DC?')
        elif res is None:
            self.write(f'MEAS:VOLT:DC? {rng}')
        else:
            self.write(f'MEAS:VOLT:DC? {rng},{res}')
        line = self.read_line().strip()
        try:
            return float(line)
        except ValueError as ex:
            raise DmmError(f"解析讀值失敗：{line} → {ex}")
