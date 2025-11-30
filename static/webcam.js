// Webcam capture and streaming module
// 攝像頭擷取與串流模組（高解析度版本）

const WebcamCapture = {
    video: null,
    canvas: null,
    ctx: null,
    stream: null,
    imageCapture: null,
    isCapturing: false,
    captureInterval: null,
    highResJpegQuality: 0.95,

    // 列舉所有攝像頭設備
    async getVideoDevices() {
        const devices = await navigator.mediaDevices.enumerateDevices();
        return devices.filter(device => device.kind === 'videoinput');
    },

    // 初始化攝像頭（選擇最後一個後置鏡頭，通常是主攝像頭，支持對焦）
    async init(videoElementId) {
        this.video = document.getElementById(videoElementId);
        this.canvas = document.createElement('canvas');
        this.ctx = this.canvas.getContext('2d');

        try {
            // 列舉所有攝像頭
            const videoDevices = await this.getVideoDevices();
            console.log('可用攝像頭數量:', videoDevices.length);
            videoDevices.forEach((device, i) => {
                console.log(`  攝像頭 ${i}: ${device.label || device.deviceId}`);
            });

            if (videoDevices.length === 0) {
                throw new Error('找不到任何攝像頭');
            }

            // 選擇最後一個攝像頭（通常是主攝像頭，支持對焦）
            const selectedDevice = videoDevices[videoDevices.length - 1];
            console.log('選擇攝像頭:', selectedDevice.label || selectedDevice.deviceId);

            // 使用指定的攝像頭
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    deviceId: { exact: selectedDevice.deviceId },
                    facingMode: 'environment',
                    width: { ideal: 1920 },
                    height: { ideal: 1080 }
                },
                audio: false
            });
            console.log('攝像頭已啟動（指定設備模式）');

        } catch (error) {
            console.warn('指定攝像頭失敗，嘗試備用設定:', error);
            try {
                // 備用：使用 facingMode 選擇後置攝像頭
                this.stream = await navigator.mediaDevices.getUserMedia({
                    video: {
                        facingMode: 'environment',
                        width: { ideal: 1920 },
                        height: { ideal: 1080 }
                    },
                    audio: false
                });
                console.log('攝像頭已啟動（備用模式）');
            } catch (fallbackError) {
                console.warn('備用設定失敗，使用最基本設定:', fallbackError);
                try {
                    this.stream = await navigator.mediaDevices.getUserMedia({
                        video: true,
                        audio: false
                    });
                    console.log('攝像頭已啟動（基本模式）');
                } catch (basicError) {
                    console.error('無法存取任何攝像頭:', basicError);
                    return false;
                }
            }
        }

        this.video.srcObject = this.stream;

        // 等待 video 載入 metadata（確保 videoWidth/videoHeight 有值）
        await new Promise((resolve) => {
            if (this.video.readyState >= 1) {
                resolve();
            } else {
                this.video.addEventListener('loadedmetadata', resolve, { once: true });
            }
        });

        await this.video.play();

        // 顯示實際解析度
        console.log(`實際視頻解析度: ${this.video.videoWidth}x${this.video.videoHeight}`);

        // 嘗試初始化 ImageCapture API 並設定連續對焦
        try {
            const videoTrack = this.stream.getVideoTracks()[0];
            if (typeof ImageCapture !== 'undefined') {
                this.imageCapture = new ImageCapture(videoTrack);
                console.log('ImageCapture API 已啟用');

                // 顯示實際的攝像頭能力
                const capabilities = videoTrack.getCapabilities();
                console.log('攝像頭能力:', capabilities);

                // 嘗試應用連續對焦（如果支援）
                if (capabilities.focusMode && capabilities.focusMode.includes('continuous')) {
                    await videoTrack.applyConstraints({
                        advanced: [{ focusMode: 'continuous' }]
                    });
                    console.log('連續自動對焦已啟用');
                }
            } else {
                console.warn('ImageCapture API 不支援，將使用 canvas 方式拍照');
            }
        } catch (e) {
            console.warn('ImageCapture 初始化失敗:', e);
        }

        return true;
    },

    // 傳輸用的最大尺寸（避免 WebSocket 超過大小限制）
    maxTransferWidth: 1920,
    transferJpegQuality: 0.85,

    // 壓縮圖片以便傳輸（限制大小避免 WebSocket 超限）
    compressForTransfer(sourceCanvas) {
        const srcWidth = sourceCanvas.width;
        const srcHeight = sourceCanvas.height;

        // 如果已經小於傳輸限制，直接返回
        if (srcWidth <= this.maxTransferWidth) {
            return sourceCanvas.toDataURL('image/jpeg', this.transferJpegQuality);
        }

        // 計算壓縮後的尺寸
        const ratio = this.maxTransferWidth / srcWidth;
        const newWidth = this.maxTransferWidth;
        const newHeight = Math.round(srcHeight * ratio);

        // 建立壓縮用的 canvas
        const compressCanvas = document.createElement('canvas');
        const compressCtx = compressCanvas.getContext('2d');
        compressCanvas.width = newWidth;
        compressCanvas.height = newHeight;

        // 繪製壓縮後的圖片
        compressCtx.drawImage(sourceCanvas, 0, 0, newWidth, newHeight);

        const base64Data = compressCanvas.toDataURL('image/jpeg', this.transferJpegQuality);
        console.log(`圖片已壓縮: ${srcWidth}x${srcHeight} -> ${newWidth}x${newHeight}`);
        return base64Data;
    },

    // 高解析度拍照（優先使用 ImageCapture API，然後壓縮傳輸）
    async captureHighResPhoto() {
        if (!this.video || !this.video.videoWidth) {
            console.error('視頻未就緒');
            return null;
        }

        // 方法一：使用 ImageCapture API（可獲得相機完整解析度）
        if (this.imageCapture) {
            try {
                console.log('使用 ImageCapture API 拍照...');
                const blob = await this.imageCapture.takePhoto({
                    imageWidth: 4096,  // 嘗試最高解析度
                    imageHeight: 3072
                });

                // Blob 轉換為 Image，然後繪製到 canvas 進行壓縮
                return new Promise((resolve, reject) => {
                    const img = new Image();
                    img.onload = () => {
                        // 先繪製到 canvas
                        const tempCanvas = document.createElement('canvas');
                        const tempCtx = tempCanvas.getContext('2d');
                        tempCanvas.width = img.width;
                        tempCanvas.height = img.height;
                        tempCtx.drawImage(img, 0, 0);

                        console.log(`ImageCapture 拍照成功: ${img.width}x${img.height}`);

                        // 壓縮後傳輸
                        const compressedData = this.compressForTransfer(tempCanvas);
                        resolve(compressedData);
                    };
                    img.onerror = reject;
                    img.src = URL.createObjectURL(blob);
                });
            } catch (e) {
                console.warn('ImageCapture.takePhoto 失敗，使用 canvas 方式:', e);
            }
        }

        // 方法二：使用 canvas 以視頻原始解析度截圖
        console.log('使用 canvas 方式拍照...');
        const width = this.video.videoWidth;
        const height = this.video.videoHeight;

        this.canvas.width = width;
        this.canvas.height = height;
        this.ctx.drawImage(this.video, 0, 0, width, height);

        console.log(`Canvas 拍照成功: ${width}x${height}`);

        // 壓縮後傳輸
        const compressedData = this.compressForTransfer(this.canvas);
        return compressedData;
    },

    // 擷取並壓縮畫面（用於預覽，保留但不再自動使用）
    captureFrame() {
        if (!this.video || !this.video.videoWidth) {
            return null;
        }

        const width = this.video.videoWidth;
        const height = this.video.videoHeight;

        this.canvas.width = width;
        this.canvas.height = height;
        this.ctx.drawImage(this.video, 0, 0, width, height);

        const base64Data = this.canvas.toDataURL('image/jpeg', 0.8);
        return base64Data;
    },

    // 開始連續擷取（保留但不再自動啟用）
    startCapture(onCaptureCallback) {
        if (this.isCapturing) {
            console.log('已經在擷取中');
            return;
        }

        this.isCapturing = true;
        this.captureInterval = setInterval(() => {
            const frameData = this.captureFrame();
            if (frameData && onCaptureCallback) {
                onCaptureCallback(frameData);
            }
        }, 500);

        console.log('開始連續擷取畫面');
    },

    // 停止擷取
    stopCapture() {
        if (this.captureInterval) {
            clearInterval(this.captureInterval);
            this.captureInterval = null;
        }
        this.isCapturing = false;
        console.log('停止擷取畫面');
    },

    // 停止攝像頭
    stop() {
        this.stopCapture();
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        if (this.video) {
            this.video.srcObject = null;
        }
        this.imageCapture = null;
        console.log('攝像頭已停止');
    },

    // 取得目前視頻解析度
    getResolution() {
        if (!this.video) {
            return null;
        }
        return {
            width: this.video.videoWidth,
            height: this.video.videoHeight
        };
    },

    // HTTP 上傳圖片（避免 WebSocket 大小限制）
    async uploadPhotoHTTP(base64Data) {
        try {
            console.log('使用 HTTP 上傳圖片...');
            const response = await fetch('/api/upload_photo', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ image: base64Data })
            });

            const result = await response.json();
            console.log('HTTP 上傳結果:', result);

            if (!response.ok) {
                // 422 或其他錯誤狀態碼
                return { success: false, error: result.detail || '未知錯誤' };
            }

            // 成功：添加 success 標記
            return { success: true, img_url: result.img_url };
        } catch (error) {
            console.error('HTTP 上傳失敗:', error);
            return { success: false, error: error.message };
        }
    },

    // 拍照並透過 HTTP 上傳
    async captureAndUploadHTTP() {
        // 拍照
        const photoData = await this.captureHighResPhoto();
        if (!photoData) {
            return { success: false, error: '拍照失敗' };
        }

        // 透過 HTTP 上傳
        return await this.uploadPhotoHTTP(photoData);
    }
};

// 將模組暴露到全域
window.WebcamCapture = WebcamCapture;
