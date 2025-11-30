import base64
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from capybara import imwarp_quadrangle
from docaligner import DocAligner
from loguru import logger

sys.path.append(str(Path(__file__).parent.parent))  # noqa
from libs.errors import CardDetectionError
from libs.utils import IMAGES_DIR

MAX_IMAGES_COUNT = 30

OUTPUT_WIDTH_INT = 860
OUTPUT_HEIGHT_INT = 540

logger.info("正在載入 DocAligner 模型...")
DOC_ALIGNER = DocAligner()
logger.info("DocAligner 模型載入完成！")


def get_flat_rgb_img(
    bgr_img: np.ndarray,
) -> np.ndarray:
    """ 偵測卡片並進行透視校正
    Raises:
        CardDetectionError: 未偵測到卡片
    """
    poly_arr = DOC_ALIGNER(img=bgr_img, do_center_crop=True)
    poly_len_int = len(poly_arr)
    if poly_len_int != 4:
        raise CardDetectionError(
            message=f"未偵測到卡片: 偵測到 {poly_len_int} 個角點",
        )

    logger.success("偵測到卡片！正在進行透視校正...")
    rgb_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)
    flat_rgb_img = imwarp_quadrangle(
        img=rgb_img,
        polygon=poly_arr,
        dst_size=(OUTPUT_WIDTH_INT, OUTPUT_HEIGHT_INT),
    )
    return flat_rgb_img


def save_corrected_image(rgb_img: np.ndarray) -> Path | None:
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"corrected_{timestamp_str}.jpg"
    filepath = IMAGES_DIR / filename

    # 轉換 RGB 到 BGR
    bgr_img = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2BGR)

    # 使用 imencode + 手動寫入（避免 cv2.imwrite 中文路徑問題）
    success, buffer = cv2.imencode(
        ".jpg",
        bgr_img,
        [cv2.IMWRITE_JPEG_QUALITY, 98],
    )
    if not success:
        raise ValueError("圖片編碼失敗")

    # 手動寫入檔案（支援中文路徑）
    with open(filepath, "wb") as f:
        f.write(buffer.tobytes())
    logger.info(f"已儲存校正後圖片: {filename}")

    # 刪除過多的圖片
    image_path_list = sorted(
        IMAGES_DIR.glob("*.jpg"),
        key=lambda p: p.stat().st_mtime,
    )
    while len(image_path_list) > MAX_IMAGES_COUNT:
        oldest_path = image_path_list.pop(0)
        oldest_path.unlink()
        logger.info(f"已刪除舊圖片: {oldest_path.name}")

    return filepath


def to_bgr_img(img_b64_str: str) -> np.ndarray:
    if "," in img_b64_str:
        img_b64_str = img_b64_str.split(",")[1]
    return cv2.imdecode(
        np.frombuffer(base64.b64decode(img_b64_str), np.uint8),
        flags=cv2.IMREAD_COLOR_BGR,
    )


def to_img_b64_str(
    rgb_img: np.ndarray,
    jpeg_quality_int: int = 95,
) -> str:
    bgr_img = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2BGR)
    success_bool, buffer = cv2.imencode(
        ".jpg",
        bgr_img,
        [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality_int],
    )
    if not success_bool:
        raise ValueError("圖片編碼失敗")
    return f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"


if __name__ == "__main__":
    import pylab as plt
    img_path = Path(__file__).parent.parent / "tests/imgs" / "S__44711952.jpg"
    bgr_img = cv2.imdecode(
        np.fromfile(
            img_path,
            dtype=np.uint8
        ), flags=cv2.IMREAD_COLOR_BGR
    )
    flat_rgb_img = get_flat_rgb_img(bgr_img)
    plt.imshow(flat_rgb_img)
    plt.show()
