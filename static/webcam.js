// Webcam capture and streaming module
// 攝像頭擷取與串流模組

const WebcamCapture = {
    video: null,
    canvas: null,
    ctx: null,
    stream: null,
    isCapturing: false,
    captureInterval: null,
    maxWidth: 800,
    jpegQuality: 0.7,

    // 初始化攝像頭
    async init(videoElementId) {
        this.video = document.getElementById(videoElementId);
        this.canvas = document.createElement('canvas');
        this.ctx = this.canvas.getContext('2d');

        try {
            // 優先使用後置鏡頭
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    facingMode: 'environment',
                    width: { ideal: 1280 },
                    height: { ideal: 720 }
                },
                audio: false
            });

            this.video.srcObject = this.stream;
            await this.video.play();
            console.log('攝像頭已啟動');
            return true;
        } catch (error) {
            console.error('無法存取攝像頭:', error);
            // 嘗試使用任何可用的攝像頭
            try {
                this.stream = await navigator.mediaDevices.getUserMedia({
                    video: true,
                    audio: false
                });
                this.video.srcObject = this.stream;
                await this.video.play();
                console.log('攝像頭已啟動（備用模式）');
                return true;
            } catch (fallbackError) {
                console.error('無法存取任何攝像頭:', fallbackError);
                return false;
            }
        }
    },

    // 擷取並壓縮畫面
    captureFrame() {
        if (!this.video || !this.video.videoWidth) {
            return null;
        }

        // 計算壓縮後的尺寸
        let width = this.video.videoWidth;
        let height = this.video.videoHeight;

        if (width > this.maxWidth) {
            const ratio = this.maxWidth / width;
            width = this.maxWidth;
            height = Math.round(height * ratio);
        }

        // 設定 canvas 尺寸並繪製
        this.canvas.width = width;
        this.canvas.height = height;
        this.ctx.drawImage(this.video, 0, 0, width, height);

        // 轉換為 JPEG base64
        const base64Data = this.canvas.toDataURL('image/jpeg', this.jpegQuality);
        return base64Data;
    },

    // 開始擷取（每秒一次）
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
        }, 1000);  // 每秒一次

        console.log('開始擷取畫面');
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
        console.log('攝像頭已停止');
    },

    // 設定壓縮參數
    setCompression(maxWidth, jpegQuality) {
        this.maxWidth = maxWidth || 800;
        this.jpegQuality = jpegQuality || 0.7;
    }
};

// 將模組暴露到全域
window.WebcamCapture = WebcamCapture;


