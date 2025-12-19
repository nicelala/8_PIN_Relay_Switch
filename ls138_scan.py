# -*- coding: utf-8 -*-
"""
互動控制：
輸入 1~8 → 對應 SN74LS138 的 Y0~Y7 Active-Low 選通。
A=LSB, B=次位, C=MSB；Index = A + 2*B + 4*C。

Phidget22（Python）正確開啟：openWaitForAttachment(timeout)。
參考：Phidgets Opening a Channel（Python 用 openWaitForAttachment）、
Language - Python 範例、SN74LS138 datasheet 真值表。
"""

import os
import sys
import time
import argparse
import logging
from datetime import datetime

from Phidget22.PhidgetException import PhidgetException
from Phidget22.Devices.DigitalOutput import DigitalOutput

# --------- 共用工具 ---------
def app_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.dirname(__file__))

def setup_logging(log_level=logging.INFO) -> str:
    base = app_dir()
    log_dir = os.path.join(base, "logs")
    os.makedirs(log_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"LS138_Interactive_{stamp}.log")

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.info("Log file = %s", log_path)
    return log_path

def open_relay(ch: int, serial: int = None) -> DigitalOutput:
    """開啟 1014 的某個繼電器通道；ch=0→A, 1→B, 2→C"""
    d = DigitalOutput()
    d.setChannel(ch)
    if serial is not None:
        d.setDeviceSerialNumber(serial)  # 鎖板，避免連錯
    try:
        d.openWaitForAttachment(5000)  # Python 版阻塞開啟
        logging.info("Relay channel %d attached.", ch)
    except PhidgetException as ex:
        logging.error("Attach failed on channel %d: %s", ch, ex)
        raise
    return d

def set_abc(relayA: DigitalOutput, relayB: DigitalOutput, relayC: DigitalOutput, index: int):
    """
    將目標 index(0..7) 轉為 A/B/C 三位元（A=LSB），
    設定三個繼電器：True=吸合→COM→NO導通→對 SN74LS138 即 High。
    因輸出 Active-Low，選通的 Y[index] 會拉低。
    """
    if not (0 <= index <= 7):
        raise ValueError("index 必須在 0..7")

    a = bool(index & 0b001)  # A=LSB
    b = bool(index & 0b010)  # B
    c = bool(index & 0b100)  # C=MSB

    relayA.setState(a)
    relayB.setState(b)
    relayC.setState(c)

    # 機械繼電器 on/off 典型 ~10ms，留 20ms 緩衝
    time.sleep(0.02)

    logging.info("已設定 ABC=%d%d%d → SN74LS138: Y%d LOW（其餘 HIGH）",
                 int(c), int(b), int(a), index)

def main():
    parser = argparse.ArgumentParser(description="SN74LS138 互動選通：輸入 1~8 控制三路 Phidget（A/B/C）")
    parser.add_argument("--serial", type=int, default=None, help="指定 Phidget 裝置序號")
    parser.add_argument("--pause", action="store_true", help="結束暫停")
    parser.add_argument("--debug", action="store_true", help="啟用 DEBUG log")
    args = parser.parse_args()

    log_path = setup_logging(logging.DEBUG if args.debug else logging.INFO)
    logging.info("Start Interactive LS138 (A=LSB, C=MSB；Active-Low 單選)")

    try:
        # 開三路繼電器：0→A, 1→B, 2→C
        relayA = open_relay(0, args.serial)
        relayB = open_relay(1, args.serial)
        relayC = open_relay(2, args.serial)

        print("\n操作說明：輸入 1~8 → 對應選通 Y0~Y7；輸入 q 或 Ctrl+C 退出。\n")

        while True:
            try:
                s = input("請輸入 [1~8]：").strip().lower()
            except EOFError:
                break

            if s in ("q", "quit", "exit"):
                break

            if not s.isdigit():
                print("請輸入數字 1~8 或 q 退出。")
                continue

            n = int(s)
            if not (1 <= n <= 8):
                print("範圍 1~8。")
                continue

            idx = n - 1  # 1→Y0, 8→Y7
            set_abc(relayA, relayB, relayC, idx)

            # 視覺/量測提示：此時 Y[idx] 應為 LOW（0V 近似），其餘 HIGH（~Vdd）
            print(f"→ 期望：Y{idx} = LOW；請用 DMM/LED 觀察八路是否跟著動作。")

        logging.info("Exit interactive.")
    except Exception:
        import traceback
        logging.error("UNHANDLED EXCEPTION:\n%s", traceback.format_exc())
        print("\n發生未預期錯誤，詳細請見：", log_path)
        if args.pause:
            input("\n按 Enter 關閉...")
        sys.exit(1)
    finally:
        try:
            relayA.close(); relayB.close(); relayC.close()
        except Exception:
            pass

    if args.pause:
        input("\n執行完畢，按 Enter 關閉...")

if __name__ == "__main__":
    main()