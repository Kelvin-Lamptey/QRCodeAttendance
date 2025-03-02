import os

# Base directory of the application
basedir = os.path.abspath(os.path.dirname(__file__))

# Secret key for session management
SECRET_KEY = 'your-secret-key-here'

# SQLite database URI
SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'instance', 'attendance.db')

# Disable SQLAlchemy track modifications (improves performance)
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Upload folder for student face images
UPLOAD_FOLDER = os.path.join(basedir, 'uploads')

# TEMPLATES_AUTO_RELOAD = True

# Ensure upload directory exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Ensure instance directory exists
if not os.path.exists(os.path.join(basedir, 'instance')):
    os.makedirs(os.path.join(basedir, 'instance')) 