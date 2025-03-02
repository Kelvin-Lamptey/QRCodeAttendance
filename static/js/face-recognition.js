async function loadModels() {
    try {
        if (typeof faceapi === 'undefined') {
            return false;
        }
        
        const MODEL_URL = '/static/models';
        
        await Promise.all([
            faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
            faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
            faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL)
        ]);
        
        return true;
    } catch (error) {
        return false;
    }
}

async function detectFace(videoElement) {
    try {
        const options = new faceapi.TinyFaceDetectorOptions({
            inputSize: 320,
            scoreThreshold: 0.5
        });

        const detection = await faceapi.detectSingleFace(videoElement, options)
            .withFaceLandmarks()
            .withFaceDescriptor();
        
        if (detection) {
            return detection;
        }
        return null;
    } catch (error) {
        return null;
    }
}

function drawFaceDetections(videoElement, canvas, detection) {
    if (!detection) return;
    
    const displaySize = { width: videoElement.width, height: videoElement.height };
    faceapi.matchDimensions(canvas, displaySize);
    
    const resizedDetection = faceapi.resizeResults(detection, displaySize);
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    faceapi.draw.drawDetections(canvas, [resizedDetection]);
    faceapi.draw.drawFaceLandmarks(canvas, [resizedDetection]);
}

// Add this helper function to check for camera support
function isCameraSupported() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
}

// Update the camera initialization function
async function initializeCamera() {
    try {
        // Check if camera is supported
        if (!isCameraSupported()) {
            throw new Error('Camera access is not supported on this device or browser. Please try with a modern browser on a device with a camera.');
        }
        
        const stream = await navigator.mediaDevices.getUserMedia({ 
            video: {
                width: { ideal: 640 },
                height: { ideal: 480 },
                facingMode: 'user'
            }
        });
        
        return stream;
    } catch (error) {
        // Handle specific errors
        if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
            throw new Error('Camera access denied. Please allow camera access to use this feature.');
        } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
            throw new Error('No camera found on this device.');
        } else if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
            throw new Error('Camera is already in use by another application.');
        } else if (error.name === 'OverconstrainedError' || error.name === 'ConstraintNotSatisfiedError') {
            throw new Error('Camera does not meet the required constraints.');
        } else if (error.name === 'TypeError' && error.message.includes('undefined')) {
            throw new Error('Camera access is not supported on this device or browser.');
        }
        
        throw error;
    }
} 