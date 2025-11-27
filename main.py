import base64
from datetime import datetime
from pathlib import Path

from loguru import logger
from nicegui import app, ui

# 設定圖片儲存路徑
IMAGES_DIR = Path(__file__).parent / "images"
IMAGES_DIR.mkdir(exist_ok=True)

# 最多保留的圖片數量
MAX_IMAGES_COUNT = 30


def cleanup_old_images() -> None:
    image_path_list = sorted(
        IMAGES_DIR.glob("*.jpg"),
        key=lambda p: p.stat().st_mtime,
    )
    while len(image_path_list) > MAX_IMAGES_COUNT:
        oldest_path = image_path_list.pop(0)
        oldest_path.unlink()
        logger.info(f"已刪除舊圖片: {oldest_path.name}")


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
        logger.info(f"已儲存圖片: {filename}")
        cleanup_old_images()
        return True
    except Exception as e:
        logger.error(f"儲存圖片失敗: {e}")
        return False


# 設定靜態檔案路徑
app.add_static_files("/static", Path(__file__).parent / "static")


@ui.page("/")
def index_page():
    # 頁面狀態（每個 client 獨立）
    capture_count = 0

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

        # 定義接收圖片的處理函數
        def on_frame_received(base64_data: str):
            nonlocal capture_count
            if base64_data and isinstance(base64_data, str):
                if save_image(base64_data):
                    capture_count += 1
                    count_label.set_text(f"已儲存圖片：{capture_count} 張")

        # 使用全域事件監聽
        ui.on("webcam_frame", lambda e: on_frame_received(e.args))

        # 初始化攝像頭並自動開始擷取
        async def init_camera():
            try:
                result = await ui.run_javascript(
                    """
                    (async () => {
                        const success = await WebcamCapture.init('webcam-video');
                        if (success) {
                            WebcamCapture.startCapture((frameData) => {
                                emitEvent('webcam_frame', frameData);
                            });
                        }
                        return success;
                    })()
                    """,
                    timeout=10.0,
                )
                if result:
                    status_label.set_text("狀態：錄製中...")
                else:
                    status_label.set_text("狀態：無法存取攝像頭，請確認權限設定")
                return result
            except TimeoutError:
                status_label.set_text("狀態：等待連線中...")
                logger.warning("JavaScript 初始化超時，等待客戶端連接")
                return False

        # 頁面載入後自動初始化攝像頭
        ui.timer(0.5, init_camera, once=True)


def main():
    port_int = 25331
    logger.info(f"啟動 Webcam Capture，端口: {port_int}")

    ui.run(
        host="0.0.0.0",
        port=port_int,
        title="Webcam Capture",
        reload=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
