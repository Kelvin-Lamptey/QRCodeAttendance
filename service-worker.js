const CACHE_NAME = 'face-recognition-cache-v1';
const urlsToCache = [
    '/static/models/tiny_face_detector_model-weights_manifest.json',
    '/static/models/face_landmark_68_model-weights_manifest.json',
    '/static/models/face_recognition_model-weights_manifest.json',
    // Add other assets you want to cache
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('Opened cache');
                return cache.addAll(urlsToCache);
            })
    );
});

self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                // Cache hit - return response
                if (response) {
                    return response;
                }
                return fetch(event.request);
            })
    );
}); 