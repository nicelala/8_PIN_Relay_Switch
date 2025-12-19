# 8_Pin_Relay_Switch (PyQt5)

一個使用 PyQt5 的桌面 GUI 專案。此倉庫已設定 GitHub Actions：自動於 Windows Runner 打包 `.exe`，並上傳到 Actions Artifacts；可選在推 tag 時建立 Release 並附上執行檔。

![creenshot

---

## 使用者：下載並執行
1. 打開 GitHub 倉庫的 **Actions** 頁籤，選擇最新的「Build Windows .exe」工作流。
2. 在工作流頁面右側找到 **Artifacts**，下載壓縮檔（內含 `MyApp.exe`）。
3. 解壓縮後，直接雙擊 `MyApp.exe` 執行。

> 若倉庫有發佈 Release（推送標籤觸發），也可至 **Releases** 頁面下載相同版本的 `.exe`。

---

## 開發者：安裝、啟動、打包

### 1. 安裝依賴
```bash
# 建議使用 Python 3.8+；若低於 3.8 請見下方相容性說明
pip install -r requirements.txt
pip install PyQt5 pyinstaller
