import base64
from datetime import datetime
from pathlib import Path

from loguru import logger
from nicegui import app, ui

# 設定圖片儲存路徑
IMAGES_DIR = Path(__file__).parent / "images"
IMAGES_DIR.mkdir(exist_ok=True)

# 統計資料
capture_stats = {"count": 0}


def save_image(base64_data: str) -> bool:
    try:
        # 移除 base64 header (data:image/jpeg;base64,)
        if "," in base64_data:
            base64_data = base64_data.split(",")[1]

        # 解碼並儲存
        image_bytes = base64.b64decode(base64_data)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{timestamp_str}.jpg"
        filepath = IMAGES_DIR / filename

        filepath.write_bytes(image_bytes)
        capture_stats["count"] += 1
        logger.info(f"已儲存圖片: {filename} (總計: {capture_stats['count']})")
        return True
    except Exception as e:
        logger.error(f"儲存圖片失敗: {e}")
        return False


# 設定靜態檔案路徑
app.add_static_files("/static", Path(__file__).parent / "static")


@ui.page("/")
def index_page():
    # 頁面狀態
    is_capturing = {"value": False}

    ui.add_head_html('<script src="/static/webcam.js"></script>')

    with ui.column().classes("w-full items-center p-4"):
        ui.label("📷 Webcam 即時擷取").classes("text-2xl font-bold mb-4")

        # 影像預覽區域
        with ui.card().classes("w-full max-w-lg"):
            ui.html(
                '<video id="webcam-video" autoplay playsinline muted '
                'style="width: 100%; border-radius: 8px; background: #000;"></video>',
                sanitize=False,
            )

        # 狀態顯示
        status_label = ui.label("狀態：等待啟動攝像頭...").classes("mt-4 text-gray-600")
        count_label = ui.label("已儲存圖片：0 張").classes("text-gray-600")

        # 控制按鈕
        with ui.row().classes("mt-4 gap-4"):
            start_btn = ui.button("🎬 開始錄製", color="green")
            stop_btn = ui.button("⏹️ 停止錄製", color="red")
            stop_btn.disable()

        # 定義接收圖片的處理函數
        def on_frame_received(base64_data: str):
            if base64_data and isinstance(base64_data, str):
                save_image(base64_data)
                count_label.set_text(f"已儲存圖片：{capture_stats['count']} 張")

        # 使用全域事件監聽
        ui.on("webcam_frame", lambda e: on_frame_received(e.args))

        # 初始化攝像頭
        async def init_camera():
            try:
                result = await ui.run_javascript(
                    """
                    (async () => {
                        const success = await WebcamCapture.init('webcam-video');
                        return success;
                    })()
                    """,
                    timeout=10.0,
                )
                if result:
                    status_label.set_text("狀態：攝像頭已就緒，點擊「開始錄製」")
                else:
                    status_label.set_text("狀態：無法存取攝像頭，請確認權限設定")
                return result
            except TimeoutError:
                status_label.set_text("狀態：等待連線中...")
                logger.warning("JavaScript 初始化超時，等待客戶端連接")
                return False

        # 開始錄製
        async def start_capture():
            if is_capturing["value"]:
                return

            is_capturing["value"] = True
            start_btn.disable()
            stop_btn.enable()
            status_label.set_text("狀態：錄製中...")

            # 啟動 JS 端的擷取，使用 emitEvent 發送數據到後端
            await ui.run_javascript(
                """
                WebcamCapture.startCapture((frameData) => {
                    emitEvent('webcam_frame', frameData);
                });
                """,
            )

        # 停止錄製
        async def stop_capture():
            if not is_capturing["value"]:
                return

            is_capturing["value"] = False
            start_btn.enable()
            stop_btn.disable()
            status_label.set_text("狀態：已停止錄製")

            await ui.run_javascript("WebcamCapture.stopCapture();")

        start_btn.on_click(start_capture)
        stop_btn.on_click(stop_capture)

        # 頁面載入後自動初始化攝像頭
        ui.timer(0.5, init_camera, once=True)


def get_local_ip() -> str:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def main():
    port_int = 8080
    logger.info(f"啟動 Webcam Capture，端口: {port_int}")

    ui.run(
        host="0.0.0.0",
        port=port_int,
        title="Webcam Capture",
        reload=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
