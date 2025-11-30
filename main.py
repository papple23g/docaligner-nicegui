import sys
from pathlib import Path

from fastapi import Request
from loguru import logger
from nicegui import app, ui

sys.path.append(str(Path(__file__).parent.parent))  # noqa
from libs.img_processer import (
    get_flat_rgb_img,
    save_corrected_image,
    to_bgr_img,
    to_img_b64_str,
)
from libs.utils import IMAGES_DIR

# 設定靜態檔案路徑
app.add_static_files("/static", str(Path(__file__).parent / "static"))
# 設定圖片目錄為靜態檔案路徑（讓前端可以直接存取校正後的圖片）
app.add_static_files("/images", str(IMAGES_DIR))
logger.info(f"圖片目錄: {IMAGES_DIR}")


# HTTP POST 端點：接收圖片並處理（避免 WebSocket 大小限制）
@app.post("/api/upload_photo")
async def upload_photo_api(request: Request) -> dict:
    try:
        # 解析 JSON 請求
        data = await request.json()
        img_b64_str = data.get("image")
        if not img_b64_str:
            raise ValueError("沒有收到圖片數據")

        logger.info("收到 HTTP 上傳的圖片")
        # 解碼圖片
        bgr_img = to_bgr_img(img_b64_str)
        # 記錄圖片尺寸
        img_height_int, img_width_int = bgr_img.shape[:2]
        logger.info(f"收到高解析度圖片: {img_width_int}x{img_height_int}")

        # 偵測並校正卡片
        success_bool, flat_rgb_img, poly_len_int = get_flat_rgb_img(
            bgr_img=bgr_img,
        )

        if success_bool and flat_rgb_img is not None:
            logger.info("卡片擷取成功！")

            # 儲存校正後的圖片
            saved_path = save_corrected_image(flat_rgb_img)

            # 取得輸出圖片尺寸
            out_height_int, out_width_int = flat_rgb_img.shape[:2]

            # 返回圖片 URL（避免 base64 太大超過 WebSocket 限制）
            if saved_path and saved_path.exists():
                image_url = f"/images/{saved_path.name}"
                logger.info(
                    f"圖片 URL: {image_url}, 檔案存在: {saved_path.exists()}"
                )
            else:
                logger.error(f"儲存的圖片不存在: {saved_path}")
                image_url = ""

            return {
                "success": True,
                "result_image_url": image_url,
                "input_size": f"{img_width_int}x{img_height_int}",
                "output_size": f"{out_width_int}x{out_height_int}",
            }
        else:
            # 偵測失敗
            error_msg = (
                "未偵測到卡片"
                if poly_len_int == 0
                else f"偵測到 {poly_len_int} 個角點，需要 4 個角點"
            )
            logger.warning(f"卡片偵測失敗: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "input_size": f"{img_width_int}x{img_height_int}",
                "poly_count": poly_len_int,
            }

    except Exception as e:
        logger.error(f"HTTP 上傳處理錯誤: {e}")
        return {"success": False, "error": str(e)}


@ui.page("/")
def index_page():
    # 頁面狀態（每個 client 獨立）
    is_processing = False
    is_camera_ready = False

    # 加上版本號避免瀏覽器快取舊版 JavaScript
    ui.add_head_html('<script src="/static/webcam.js?v=4"></script>')

    with ui.column().classes("w-full items-center p-4"):
        ui.label("📷 卡片擷取與校正").classes("text-2xl font-bold mb-4")

        # 影像預覽區域
        video_card = ui.card().classes("w-full max-w-lg")
        with video_card:
            ui.html(
                '<video id="webcam-video" autoplay playsinline muted '
                'style="width: 100%; border-radius: 8px; background: #000;"></video>',
                sanitize=False,
            )

        # 結果圖片區域（拍照成功後顯示）
        result_card = ui.card().classes("w-full max-w-lg hidden")
        with result_card:
            result_image = ui.image().classes("w-full rounded-lg")

        # 狀態顯示
        status_label = ui.label("狀態：等待啟動攝像頭...").classes(
            "mt-4 text-gray-600"
        )

        # Debug 資訊顯示
        debug_label = ui.label("").classes(
            "mt-2 text-sm text-blue-500 font-mono"
        )

        # 按鈕容器
        button_container = ui.row().classes("mt-4 gap-4")

        with button_container:
            # 拍照按鈕（初始隱藏，攝像頭就緒後顯示）
            capture_button = ui.button(
                "📸 拍照",
            ).classes("hidden").props("color=primary size=lg")

            # 重新拍攝按鈕（初始隱藏）
            retry_button = ui.button(
                "🔄 重新拍攝",
                on_click=lambda: ui.run_javascript("location.reload()"),
            ).classes("hidden").props("color=secondary size=lg")

        # 處理拍照結果
        def on_photo_received(base64_data: str) -> None:
            nonlocal is_processing

            if is_processing:
                return

            if not base64_data or not isinstance(base64_data, str):
                logger.warning("收到無效的圖片數據")
                status_label.set_text("狀態：拍照失敗，請重試")
                capture_button.enable()
                return

            is_processing = True
            status_label.set_text("狀態：處理中...")

            try:
                # 解碼圖片
                bgr_img = to_bgr_img(base64_data)
                if bgr_img is None:
                    logger.error("圖片解碼失敗")
                    status_label.set_text("狀態：圖片解碼失敗，請重試")
                    capture_button.enable()
                    return

                # Debug: 記錄圖片尺寸
                img_height_int, img_width_int = bgr_img.shape[:2]
                logger.info(f"收到高解析度圖片: {img_width_int}x{img_height_int}")
                debug_label.set_text(
                    f"原始圖片尺寸: {img_width_int}x{img_height_int}")

                # 偵測並校正卡片
                success_bool, flat_rgb_img, poly_len_int = get_flat_rgb_img(
                    bgr_img=bgr_img,
                )

                if success_bool and flat_rgb_img is not None:
                    logger.info("卡片擷取成功！")

                    # 儲存校正後的圖片
                    save_corrected_image(flat_rgb_img)

                    # 取得輸出圖片尺寸
                    out_height_int, out_width_int = flat_rgb_img.shape[:2]

                    # 編碼結果圖片為 base64（高品質）
                    result_base64 = to_img_b64_str(
                        rgb_img=flat_rgb_img,
                        jpeg_quality_int=95,
                    )

                    # 更新前端 UI
                    status_label.set_text("狀態：卡片擷取成功！")
                    debug_label.set_text(
                        f"原始: {img_width_int}x{img_height_int} → "
                        f"輸出: {out_width_int}x{out_height_int}"
                    )

                    # 停止攝像頭
                    ui.run_javascript("WebcamCapture.stop();")

                    # 隱藏 video，顯示結果
                    video_card.classes(add="hidden")
                    result_card.classes(remove="hidden")
                    result_image.set_source(result_base64)

                    # 隱藏拍照按鈕，顯示重新拍攝按鈕
                    capture_button.classes(add="hidden")
                    retry_button.classes(remove="hidden")

                else:
                    # 偵測失敗
                    if poly_len_int == 0:
                        status_label.set_text("狀態：未偵測到卡片，請調整位置後重試")
                    else:
                        status_label.set_text(
                            f"狀態：偵測到 {poly_len_int} 個角點，需要 4 個角點，請重試"
                        )
                    debug_label.set_text(
                        f"尺寸: {img_width_int}x{img_height_int}, 角點數: {poly_len_int}"
                    )
                    capture_button.enable()

            except Exception as e:
                logger.error(f"處理錯誤: {e}")
                status_label.set_text(f"狀態：處理錯誤: {e}")
                capture_button.enable()

            finally:
                is_processing = False

        # 使用全域事件監聽拍照結果
        ui.on("webcam_photo", lambda e: on_photo_received(e.args))

        # 處理攝像頭就緒事件
        def on_camera_ready(event_args) -> None:
            nonlocal is_camera_ready
            import json

            # Debug: 打印完整的事件參數
            logger.debug(
                f"收到 webcam_ready 事件, args={event_args}, type={type(event_args)}"
            )

            # 處理不同格式的事件參數
            resolution_dict = None

            # 嘗試解析 JSON 字符串（emitEvent 傳遞的數據）
            if isinstance(event_args, str):
                try:
                    resolution_dict = json.loads(event_args)
                    logger.debug(f"JSON 解析成功: {resolution_dict}")
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
            elif event_args is not None:
                logger.warning(f"未預期的事件參數格式: {type(event_args)}")

            # 檢查是否有錯誤
            if resolution_dict and "error" in resolution_dict:
                error_msg = resolution_dict.get("error", "未知錯誤")
                status_label.set_text(f"狀態：攝像頭錯誤 - {error_msg}")
                debug_label.set_text(f"錯誤: {error_msg}")
                logger.error(f"攝像頭初始化錯誤: {error_msg}")
                return

            if resolution_dict and resolution_dict.get("width", 0) > 0:
                is_camera_ready = True
                width_int = resolution_dict.get("width", 0)
                height_int = resolution_dict.get("height", 0)
                resolution_str = f"{width_int}x{height_int}"
                status_label.set_text("狀態：請將卡片對準鏡頭，對焦後按下拍照按鈕")
                debug_label.set_text(f"攝像頭解析度: {resolution_str}")
                logger.info(f"攝像頭就緒，解析度: {resolution_str}")

                # 顯示拍照按鈕
                capture_button.classes(remove="hidden")
            else:
                status_label.set_text("狀態：無法存取攝像頭，請確認權限設定")
                logger.warning(
                    f"攝像頭初始化失敗，resolution_dict={resolution_dict}"
                )

        # 監聯攝像頭就緒事件
        ui.on("webcam_ready", lambda e: on_camera_ready(e.args))

        # 拍照按鈕點擊處理（使用 HTTP 上傳）
        async def on_capture_click() -> None:
            nonlocal is_processing

            if is_processing:
                return

            is_processing = True
            capture_button.disable()
            status_label.set_text("狀態：拍照並上傳中...")

            try:
                # 呼叫 JavaScript 拍照並透過 HTTP 上傳
                result = await ui.run_javascript(
                    """
                    (async () => {
                        console.log('[webcam] 開始拍照並上傳...');
                        const result = await WebcamCapture.captureAndUploadHTTP();
                        console.log('[webcam] 上傳結果:', result);
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
                    # 成功：顯示結果圖片（使用 URL 而不是 base64）
                    result_url = result_dict.get("result_image_url", "")
                    input_size = result_dict.get("input_size", "?")
                    output_size = result_dict.get("output_size", "?")

                    status_label.set_text("狀態：卡片擷取成功！")
                    debug_label.set_text(
                        f"原始: {input_size} → 輸出: {output_size}"
                    )

                    # 停止攝像頭
                    ui.run_javascript("WebcamCapture.stop();")

                    # 隱藏 video，顯示結果
                    video_card.classes(add="hidden")
                    result_card.classes(remove="hidden")
                    result_image.set_source(result_url)

                    # 隱藏拍照按鈕，顯示重新拍攝按鈕
                    capture_button.classes(add="hidden")
                    retry_button.classes(remove="hidden")

                else:
                    # 失敗：顯示錯誤訊息
                    error_msg = result_dict.get("error", "未知錯誤")
                    input_size = result_dict.get("input_size", "?")
                    poly_count = result_dict.get("poly_count", 0)

                    status_label.set_text(f"狀態：{error_msg}，請重試")
                    debug_label.set_text(
                        f"尺寸: {input_size}, 角點數: {poly_count}")
                    capture_button.enable()

            except TimeoutError:
                logger.error("拍照/上傳超時")
                status_label.set_text("狀態：拍照超時，請重試")
                capture_button.enable()
            except Exception as e:
                logger.error(f"拍照/上傳錯誤: {e}")
                status_label.set_text(f"狀態：錯誤 - {e}")
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
