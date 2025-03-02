import os
import urllib.request

def download_models():
    # Create models directory if it doesn't exist
    models_dir = os.path.join('static', 'models')
    os.makedirs(models_dir, exist_ok=True)

    # Base URL for the model files
    base_url = "https://raw.githubusercontent.com/justadudewhohacks/face-api.js/master/weights"

    # List of model files to download
    model_files = [
        'tiny_face_detector_model-weights_manifest.json',
        'tiny_face_detector_model-shard1',
        'face_landmark_68_model-weights_manifest.json',
        'face_landmark_68_model-shard1',
        'face_recognition_model-weights_manifest.json',
        'face_recognition_model-shard1'
    ]

    # Download each file
    for file in model_files:
        file_path = os.path.join(models_dir, file)
        if not os.path.exists(file_path):
            print(f"Downloading {file}...")
            url = f"{base_url}/{file}"
            try:
                urllib.request.urlretrieve(url, file_path)
                print(f"Successfully downloaded {file}")
            except Exception as e:
                print(f"Error downloading {file}: {e}")
        else:
            print(f"File {file} already exists")

if __name__ == "__main__":
    download_models() 