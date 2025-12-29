
# input_dialog.py
# -*- coding: utf-8 -*-
from PyQt5 import QtWidgets, QtCore

import re
_ALNUM = re.compile(r'^[A-Za-z0-9]+$')

# 測試
print(bool(_ALNUM.match("A123456")))  # True
print(bool(_ALNUM.match("A12345!")))  # False


class InputDialog(QtWidgets.QDialog):
    """
    輸入 OPID/MO/PN 的對話框：
    - OPID：必填，長度=7，英數字
    - MO：  必填，英數字
    - PN：  必填，長度=14，英數字
    - OK/Cancel；Enter=OK，Esc=Cancel
    - 不合法時顯示紅字錯誤訊息並停留於對話框
    """
    def __init__(self, parent=None, preset=None):
        super().__init__(parent)
        self.setWindowTitle("輸入作業資訊（OPID/MO/PN）")
        self.setModal(True)
        self.resize(420, 200)

        # 欄位
        self.edit_opid = QtWidgets.QLineEdit()
        self.edit_mo   = QtWidgets.QLineEdit()
        self.edit_pn   = QtWidgets.QLineEdit()

        if preset:
            self.edit_opid.setText(str(preset.get("OPID", "")))
            self.edit_mo.setText(str(preset.get("MO", "")))
            self.edit_pn.setText(str(preset.get("PN", "")))

        # 錯誤訊息
        self.msg = QtWidgets.QLabel("")
        self.msg.setStyleSheet("color: red;")

        # 版面
        form = QtWidgets.QFormLayout()
        form.addRow("OPID（7碼英數）", self.edit_opid)
        form.addRow("MO（英數）", self.edit_mo)
        form.addRow("PN（14碼英數）", self.edit_pn)

        btn_ok = QtWidgets.QPushButton("OK")
        btn_ok.setDefault(True)
        btn_ok.setAutoDefault(True)
        btn_ok.clicked.connect(self.on_ok)
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        hl = QtWidgets.QHBoxLayout()
        hl.addStretch(1)
        hl.addWidget(btn_ok)
        hl.addWidget(btn_cancel)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.msg)
        layout.addLayout(hl)

        # 去掉「？」說明鈕
        self.setWindowFlag(QtCore.Qt.WindowContextHelpButtonHint, False)

    def on_ok(self) -> None:
        opid = self.edit_opid.text().strip()
        mo   = self.edit_mo.text().strip()
        pn   = self.edit_pn.text().strip()

        # 檢核
        if not opid or not mo or not pn:
            self.msg.setText("全部欄位必填。")
            return
        if len(opid) != 7 or not _ALNUM.match(opid):
            self.msg.setText("OPID 必須為 7 碼英數字。")
            return
        if not _ALNUM.match(mo):
            self.msg.setText("MO 必須為英數字。")
            return
        if len(pn) != 14 or not _ALNUM.match(pn):
            self.msg.setText("PN 必須為 14 碼英數字。")
            return

        self._values = {"OPID": opid, "MO": mo, "PN": pn}
        self.accept()

    def get_values(self):
        return getattr(self, "_values", None)


# --- 單檔快速測試（直接執行本檔） ---
if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    dlg = InputDialog(preset={"OPID": "A123456", "MO": "MO001", "PN": "PN000012345678"})
    if dlg.exec_() == QtWidgets.QDialog.Accepted:
        print("OK:", dlg.get_values())
    else:
        print("Canceled")
