import sys
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger
from nicegui import app, ui
from pydantic import BaseModel

sys.path.append(str(Path(__file__).parent.parent))  # noqa
from libs.errors import CardDetectionError
from libs.img_processer import (
    get_flat_rgb_img,
    save_corrected_image,
    to_bgr_img,
)
from libs.utils import IMAGES_DIR

# 設定靜態檔案路徑
app.add_static_files("/static", str(Path(__file__).parent / "static"))
app.add_static_files("/images", str(IMAGES_DIR))
logger.info(f"圖片目錄: {IMAGES_DIR}")


class UploadPhotoPost(BaseModel):
    image: str  # base64 encoded image


class UploadPhotoOut(BaseModel):
    img_url: str


@app.exception_handler(CardDetectionError)
async def card_detection_error_handler(
    request: Request,
    exc: CardDetectionError,
) -> JSONResponse:
    logger.warning(f"卡片偵測失敗: {exc.message}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.message},
    )


@app.post("/api/upload_photo")
async def upload_photo_api(post: UploadPhotoPost) -> UploadPhotoOut:
    logger.info("收到 HTTP 上傳的圖片")
    bgr_img = to_bgr_img(img_b64_str=post.image)
    img_height_int, img_width_int = bgr_img.shape[:2]
    logger.info(f"收到高解析度圖片: {img_width_int}x{img_height_int}")

    flat_rgb_img = get_flat_rgb_img(bgr_img=bgr_img)
    logger.info("卡片擷取成功！")
    saved_path = save_corrected_image(flat_rgb_img)
    if saved_path and saved_path.exists():
        img_url = f"/images/{saved_path.name}"
        logger.info(f"圖片 URL: {img_url}")
    else:
        logger.error(f"儲存的圖片不存在: {saved_path}")
        img_url = ""

    return UploadPhotoOut(img_url=img_url)


@ui.page("/")
def index_page():
    # 頁面狀態（每個 client 獨立）
    is_processing = False
    is_camera_ready = False

    # 加上版本號避免瀏覽器快取舊版 JavaScript
    ui.add_head_html('<script src="/static/webcam.js?v=6"></script>')

    # 全屏樣式
    ui.add_head_html("""
    <style>
        body { margin: 0; overflow: hidden; }
        .fullscreen-container {
            position: fixed;
            inset: 0;
            background: #000;
        }
        #webcam-video {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        .card-guide {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 85%;
            max-width: 400px;
            aspect-ratio: 1.586 / 1;
            border: 4px dashed #FFD700;
            border-radius: 12px;
            pointer-events: none;
            box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.3);
        }
        .overlay-ui {
            position: fixed;
            left: 0;
            right: 0;
            z-index: 10;
            display: flex;
            flex-direction: column;
            align-items: center;
            pointer-events: none;
        }
        .overlay-ui > * { pointer-events: auto; }
        .top-ui { top: 20px; }
        .bottom-ui { bottom: 30px; }
        .status-text {
            background: rgba(0, 0, 0, 0.6);
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 14px;
        }
        .capture-btn {
            width: 70px;
            height: 70px;
            border-radius: 50%;
            background: white;
            border: 4px solid #FFD700;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            transition: transform 0.1s;
        }
        .capture-btn:hover { transform: scale(1.05); }
        .capture-btn:active { transform: scale(0.95); }
        .capture-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .result-container {
            position: fixed;
            inset: 0;
            background: #000;
            display: flex;
            flex-direction: column;
        }
        .result-image {
            flex: 1;
            object-fit: contain;
            width: 100%;
        }
        .retry-btn {
            background: #FFD700;
            color: #000;
            border: none;
            padding: 12px 32px;
            border-radius: 25px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            margin: 20px;
        }
    </style>
    """)

    # 攝像頭全屏容器
    video_container = ui.html(
        """
        <div class="fullscreen-container" id="video-container">
            <video id="webcam-video" autoplay playsinline muted></video>
            <div class="card-guide"></div>
        </div>
        """,
        sanitize=False,
    )

    # 結果顯示容器（初始隱藏）
    result_container = ui.html(
        """
        <div class="result-container hidden" id="result-container">
            <img class="result-image" id="result-image" src="" alt="結果">
            <div style="display: flex; justify-content: center;">
                <button class="retry-btn" onclick="location.reload()">🔄 重新拍攝</button>
            </div>
        </div>
        """,
        sanitize=False,
    )

    # 頂部狀態文字
    with ui.element("div").classes("overlay-ui top-ui"):
        status_label = ui.label("等待啟動攝像頭...").classes("status-text")

    # 底部拍照按鈕
    with ui.element("div").classes("overlay-ui bottom-ui"):
        capture_button = ui.button("📷").classes("capture-btn hidden")

        # 處理攝像頭就緒事件
        def on_camera_ready(event_args) -> None:
            nonlocal is_camera_ready
            import json

            logger.debug(
                f"收到 webcam_ready 事件, args={event_args}, type={type(event_args)}"
            )

            # 處理不同格式的事件參數
            resolution_dict = None

            if isinstance(event_args, str):
                try:
                    resolution_dict = json.loads(event_args)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON 解析失敗: {e}")
            elif isinstance(event_args, dict):
                resolution_dict = event_args
            elif isinstance(event_args, list) and len(event_args) > 0:
                first_item = event_args[0]
                if isinstance(first_item, str):
                    try:
                        resolution_dict = json.loads(first_item)
                    except json.JSONDecodeError:
                        pass
                elif isinstance(first_item, dict):
                    resolution_dict = first_item

            # 檢查是否有錯誤
            if resolution_dict and "error" in resolution_dict:
                error_msg = resolution_dict.get("error", "未知錯誤")
                status_label.set_text(f"攝像頭錯誤: {error_msg}")
                logger.error(f"攝像頭初始化錯誤: {error_msg}")
                return

            if resolution_dict and resolution_dict.get("width", 0) > 0:
                is_camera_ready = True
                width_int: int = resolution_dict.get("width", 0)
                height_int: int = resolution_dict.get("height", 0)
                logger.info(f"攝像頭就緒，解析度: {width_int}x{height_int}")

                status_label.set_text("將卡片對準黃框，按下拍照")
                capture_button.classes(remove="hidden")
            else:
                status_label.set_text("無法存取攝像頭，請確認權限")
                logger.warning(
                    f"攝像頭初始化失敗，resolution_dict={resolution_dict}"
                )

        # 監聽攝像頭就緒事件
        ui.on("webcam_ready", lambda e: on_camera_ready(e.args))

        # 拍照按鈕點擊處理（使用 HTTP 上傳）
        async def on_capture_click() -> None:
            nonlocal is_processing

            if is_processing:
                return

            is_processing = True
            capture_button.disable()
            status_label.set_text("拍照處理中...")

            try:
                # 呼叫 JavaScript 拍照並透過 HTTP 上傳
                result = await ui.run_javascript(
                    """
                    (async () => {
                        const result = await WebcamCapture.captureAndUploadHTTP();
                        return JSON.stringify(result);
                    })()
                    """,
                    timeout=30.0,
                )

                # 解析 JSON 結果
                import json
                if isinstance(result, str):
                    result_dict = json.loads(result)
                else:
                    result_dict = result

                logger.debug(f"HTTP 上傳結果: {result_dict}")

                if result_dict.get("success"):
                    img_url: str = result_dict.get("img_url", "")
                    logger.info(f"卡片擷取成功: {img_url}")

                    # 停止攝像頭並顯示結果
                    ui.run_javascript(f"""
                        WebcamCapture.stop();
                        document.getElementById('video-container').classList.add('hidden');
                        document.getElementById('result-container').classList.remove('hidden');
                        document.getElementById('result-image').src = '{img_url}';
                    """)

                    # 隱藏拍照按鈕和狀態
                    capture_button.classes(add="hidden")
                    status_label.set_text("擷取成功！")

                else:
                    # 失敗：顯示錯誤訊息
                    error_msg = result_dict.get("error", "未知錯誤")
                    status_label.set_text(f"{error_msg}，請重試")
                    capture_button.enable()

            except TimeoutError:
                logger.error("拍照/上傳超時")
                status_label.set_text("拍照超時，請重試")
                capture_button.enable()
            except Exception as e:
                logger.error(f"拍照/上傳錯誤: {e}")
                status_label.set_text(f"錯誤: {e}")
                capture_button.enable()
            finally:
                is_processing = False

        capture_button.on_click(on_capture_click)

        # 初始化攝像頭（使用 emitEvent 通知，不等待返回值）
        def init_camera() -> None:
            logger.debug("開始初始化攝像頭...")
            status_label.set_text("狀態：正在啟動攝像頭...")

            # 執行 JavaScript 初始化攝像頭，成功後用 emitEvent 通知
            # 注意：emitEvent 的第二個參數需要是字符串，所以使用 JSON.stringify
            ui.run_javascript(
                """
                (async () => {
                    console.log('[webcam] 開始初始化...');
                    try {
                        // 檢查 WebcamCapture 是否存在
                        if (typeof WebcamCapture === 'undefined') {
                            console.error('[webcam] WebcamCapture 未定義！');
                            emitEvent('webcam_ready', JSON.stringify({error: 'WebcamCapture undefined'}));
                            return;
                        }

                        // 檢查 video 元素是否存在
                        const videoEl = document.getElementById('webcam-video');
                        if (!videoEl) {
                            console.error('[webcam] video 元素不存在！');
                            emitEvent('webcam_ready', JSON.stringify({error: 'video element not found'}));
                            return;
                        }

                        console.log('[webcam] 開始呼叫 init...');
                        const success = await WebcamCapture.init('webcam-video');
                        console.log('[webcam] init 結果:', success);

                        if (success) {
                            const resolution = WebcamCapture.getResolution();
                            console.log('[webcam] 解析度:', resolution);
                            const jsonStr = JSON.stringify(resolution);
                            console.log('[webcam] 發送 emitEvent, data:', jsonStr);
                            emitEvent('webcam_ready', jsonStr);
                            console.log('[webcam] emitEvent 已發送');
                        } else {
                            console.error('[webcam] init 返回 false');
                            emitEvent('webcam_ready', JSON.stringify({error: 'init returned false'}));
                        }
                    } catch (error) {
                        console.error('[webcam] 初始化錯誤:', error);
                        console.error('[webcam] 錯誤堆疊:', error.stack);
                        emitEvent('webcam_ready', JSON.stringify({error: error.message || String(error)}));
                    }
                })();
                """
            )

        # 頁面載入後自動初始化攝像頭
        ui.timer(0.5, init_camera, once=True)


def main() -> None:
    port_int = 25331
    logger.info(f"啟動卡片擷取與校正，端口: {port_int}")

    ui.run(
        host="0.0.0.0",
        port=port_int,
        title="卡片擷取與校正",
        reload=False,
        show=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
