// Add these variables at the top
let livenessChecks = [];
const LIVENESS_THRESHOLD = 3; // Number of successful checks needed
const MOVEMENT_THRESHOLD = 0.05; // Threshold for detecting movement

async function loadModels() {
    try {
        if (typeof faceapi === 'undefined') {
            return false;
        }
        
        const MODEL_URL = '/static/models';
        
        // Preload models in the background
        const modelPromises = [
            faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
            faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
            faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL)
        ];
        
        await Promise.all(modelPromises);
        
        return true;
    } catch (error) {
        console.error('Error loading models:', error);
        return false;
    }
}

// Add this function to check for liveness
async function checkLiveness(detection) {
    if (!detection) return false;
    
    // Get current face position and expression
    const currentPosition = {
        x: detection.detection.box.x,
        y: detection.detection.box.y,
        width: detection.detection.box.width,
        height: detection.detection.box.height,
        landmarks: detection.landmarks.positions.map(p => ({ x: p.x, y: p.y }))
    };
    
    // If this is the first check, store it and return false
    if (livenessChecks.length === 0) {
        livenessChecks.push(currentPosition);
        return false;
    }
    
    // Compare with last position
    const lastPosition = livenessChecks[livenessChecks.length - 1];
    
    // Check for movement
    const movement = {
        x: Math.abs(currentPosition.x - lastPosition.x) / currentPosition.width,
        y: Math.abs(currentPosition.y - lastPosition.y) / currentPosition.height
    };
    
    // Check for facial landmark changes
    const landmarkChanges = currentPosition.landmarks.map((landmark, i) => ({
        x: Math.abs(landmark.x - lastPosition.landmarks[i].x),
        y: Math.abs(landmark.y - lastPosition.landmarks[i].y)
    }));
    
    const hasMovement = movement.x > MOVEMENT_THRESHOLD || movement.y > MOVEMENT_THRESHOLD;
    const hasLandmarkChanges = landmarkChanges.some(change => 
        change.x > MOVEMENT_THRESHOLD || change.y > MOVEMENT_THRESHOLD
    );
    
    // Store current position
    livenessChecks.push(currentPosition);
    
    // Keep only last 10 checks
    if (livenessChecks.length > 10) {
        livenessChecks.shift();
    }
    
    // Check if we have enough variation in positions
    const uniquePositions = new Set(livenessChecks.map(check => 
        Math.round(check.x / MOVEMENT_THRESHOLD) + ',' + 
        Math.round(check.y / MOVEMENT_THRESHOLD)
    ));
    
    return uniquePositions.size >= LIVENESS_THRESHOLD && (hasMovement || hasLandmarkChanges);
}

// Update the detectFace function
async function detectFace(videoElement) {
    try {
        const options = new faceapi.TinyFaceDetectorOptions({
            inputSize: 320,
            scoreThreshold: 0.6
        });

        const canvas = document.createElement('canvas');
        canvas.width = videoElement.videoWidth;
        canvas.height = videoElement.videoHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);

        const detection = await faceapi.detectSingleFace(canvas, options)
            .withFaceLandmarks()
            .withFaceDescriptor();

        if (detection) {
            // Check if the face is frontal enough
            const landmarks = detection.landmarks;
            const leftEye = landmarks.getLeftEye();
            const rightEye = landmarks.getRightEye();
            
            const eyeLevelDiff = Math.abs(leftEye[0].y - rightEye[0].y);
            const eyeDistance = Math.abs(leftEye[0].x - rightEye[0].x);
            
            if (eyeLevelDiff > eyeDistance * 0.15) {
                return { detection: null, isLive: false };
            }

            // Check for liveness
            const isLive = await checkLiveness(detection);
            return { detection, isLive };
        }
        return { detection: null, isLive: false };
    } catch (error) {
        console.error('Error in detectFace:', error);
        return { detection: null, isLive: false };
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

// Add this function to get multiple samples
async function getAverageFaceDescriptor(videoElement, numSamples = 3) {
    const descriptors = [];
    let attempts = 0;
    const maxAttempts = numSamples * 2; // Allow some failed attempts

    while (descriptors.length < numSamples && attempts < maxAttempts) {
        const detection = await detectFace(videoElement);
        if (detection) {
            descriptors.push(Array.from(detection.descriptor));
        }
        attempts++;
        // Wait a short moment between captures
        await new Promise(resolve => setTimeout(resolve, 200));
    }

    if (descriptors.length === 0) {
        return null;
    }

    // Calculate average descriptor
    const averageDescriptor = new Float32Array(128);
    for (let i = 0; i < 128; i++) {
        let sum = 0;
        for (const descriptor of descriptors) {
            sum += descriptor[i];
        }
        averageDescriptor[i] = sum / descriptors.length;
    }

    return averageDescriptor;
} 