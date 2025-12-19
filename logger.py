
# -*- coding: utf-8 -*-
"""
logger.py
Logger：收集每點量測資料並輸出 CSV（UTF-8），同目錄 logs/YYYYMMDD_HHMMSS.csv。
附摘要：Total、Fail、Max、Min、Average、Std Dev、CPK=None。
"""
from __future__ import annotations
import csv
import os
import logging
from datetime import datetime
from statistics import mean, pstdev
from typing import List, Optional, Tuple


class Logger:
    def __init__(self) -> None:
        self.rows: List[Tuple[int, float, float, float, bool, Optional[str]]] = []
        base = os.path.abspath('.')
        self.log_dir = os.path.join(base, 'logs')
        os.makedirs(self.log_dir, exist_ok=True)
        self.stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.csv_path = os.path.join(self.log_dir, f'{self.stamp}.csv')

    def add_row(self, index: int, value: float, lower: float, upper: float,
                result: bool, error: Optional[str] = None) -> None:
        self.rows.append((index, value, lower, upper, result, error))

    def save_csv(self) -> str:
        with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['Pin', 'Value', 'Lower', 'Upper', 'Result', 'Error'])
            for index, value, lower, upper, result, error in self.rows:
                
                # 這裡 self.pin_names 需由外部傳入；沒有就回退 Y{i}
                    if hasattr(self, "pin_names") and self.pin_names and index < len(self.pin_names):
                        pin = (self.pin_names[index].strip() or f'Y{index}')
                    else:
                        pin = f'Y{index}'

                    w.writerow([pin, f"{value:.6f}" if value == value else '', lower, upper,
                                        'PASS' if result else 'FAIL', error or ''])

            # 摘要
            values = [v for (_, v, _, _, _, _) in self.rows if v == v]
            total = len(self.rows)
            fail = sum(1 for (_, _, _, _, res, _) in self.rows if not res)
            mx = max(values) if values else ''
            mn = min(values) if values else ''
            avg = mean(values) if values else ''
            sd = pstdev(values) if values else ''
            w.writerow([])
            w.writerow(['Total', total])
            w.writerow(['Fail', fail])
            w.writerow(['Max', f"{mx:.6f}" if isinstance(mx, float) else mx])
            w.writerow(['Min', f"{mn:.6f}" if isinstance(mn, float) else mn])
            w.writerow(['Average', f"{avg:.6f}" if isinstance(avg, float) else avg])
            w.writerow(['Std Dev', f"{sd:.6f}" if isinstance(sd, float) else sd])
            w.writerow(['CPK', 'None'])
        logging.info("CSV 已輸出：%s", self.csv_path)
        return self.csv_path
