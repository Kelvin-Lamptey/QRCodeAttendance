from app import app, db
from datetime import datetime

def init_db():
    with app.app_context():
        # Drop all existing tables
        db.drop_all()
        
        # Create all tables with new schema
        db.create_all()
        
        print("Database initialized with new schema")

if __name__ == '__main__':
    init_db() 