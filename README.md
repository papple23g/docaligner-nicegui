# 📷 卡片擷取與校正

使用手機攝像頭拍攝卡片（如名片、證件、信用卡等），自動偵測卡片邊緣並進行透視校正，輸出方正的卡片影像。

## 功能特色

- 🎥 **全屏攝像頭預覽** - 手機瀏覽器全屏顯示攝像頭畫面
- 📐 **卡片對齊框** - 黃色虛線框幫助對準卡片位置
- 🔍 **自動邊緣偵測** - 使用 DocAligner 模型偵測卡片四個角點
- ✨ **透視校正** - 自動校正傾斜的卡片，輸出方正影像
- 📱 **行動裝置優化** - 專為手機瀏覽器設計的 UI

## 安裝

### 前置需求

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) 套件管理工具

### 安裝步驟

```bash
# 複製專案
git clone <repo-url>
cd webcam_nicegui

# 使用 uv 安裝依賴
uv sync
```

## 使用方式

### 啟動伺服器

```bash
uv run main.py
```

伺服器會在 `http://localhost:25331` 啟動。

### 外網存取（使用 ngrok）

```bash
ngrok http 25331
```

使用 ngrok 提供的公開網址，即可在手機上存取。

### 操作步驟

1. 用手機瀏覽器開啟網頁
2. 允許攝像頭權限
3. 將卡片對準畫面中央的黃色虛線框
4. 對焦後按下拍照按鈕
5. 系統自動偵測卡片並輸出校正後的影像

## 專案結構

```
webcam_nicegui/
├── main.py              # 主程式（NiceGUI 伺服器）
├── libs/
│   ├── errors.py        # 自訂例外類別
│   ├── img_processer.py # 影像處理（偵測、校正）
│   └── utils.py         # 工具函數
├── static/
│   └── webcam.js        # 前端攝像頭控制
├── pyproject.toml       # 專案設定與依賴
└── README.md
```

## 技術棧

- **後端**: [NiceGUI](https://nicegui.io/) + FastAPI
- **卡片偵測**: [DocAligner](https://github.com/DocsaidLab/DocAligner) (ONNX)
- **影像處理**: OpenCV, Capybara
- **日誌**: Loguru