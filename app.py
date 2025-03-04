from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import qrcode
import os
from werkzeug.utils import secure_filename
import base64
from io import BytesIO
import numpy as np
import json
from numpy.linalg import norm
from flask_wtf.csrf import CSRFProtect, generate_csrf
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

# Initialize Flask app
app = Flask(__name__)
app.config.from_pyfile('config.py')

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Make csrf_token available in all templates
@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf)

# Initialize database
db = SQLAlchemy(app)

# Models
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    face_encoding = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    qr_code = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('session.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin_dashboard():
    students = Student.query.all()
    sessions = Session.query.all()
    return render_template('admin/dashboard.html', students=students, sessions=sessions)

@app.route('/admin/students/new', methods=['GET', 'POST'])
@csrf.exempt
def new_student():
    if request.method == 'POST':
        try:
            if request.content_type == 'application/json':
                data = request.get_json(force=True)
            else:
                data = request.form.to_dict()
            
            student = Student(
                name=data.get('name', 'Unknown'),
                email=data.get('email', 'unknown@example.com'),
                face_encoding=json.dumps(data.get('face_descriptor', []))
            )
            
            db.session.add(student)
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'Student added successfully!'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 400
            
    return render_template('admin/new_student.html')

@app.route('/admin/sessions/new', methods=['GET', 'POST'])
def new_session():
    if request.method == 'POST':
        name = request.form['name']
        date = datetime.strptime(request.form['date'], '%Y-%m-%d')
        
        session = Session(name=name, date=date)
        db.session.add(session)
        db.session.commit()
        
        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(f"https://cddae5e6-b6e2-4c27-8fad-9bda7226ca07-00-1zl9oyhes4kd3.riker.replit.dev/attendance/{session.id}")
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        qr_code = base64.b64encode(buffered.getvalue()).decode()
        
        session.qr_code = qr_code
        db.session.commit()
        
        flash('Session created successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin/new_session.html')

@app.route('/attendance/<int:session_id>')
def attendance(session_id):
    session = Session.query.get_or_404(session_id)
    return render_template('attendance.html', session=session)

def find_matching_student(face_descriptor, threshold=0.4):
    students = Student.query.filter(Student.face_encoding.isnot(None)).all()
    
    best_match = None
    best_distance = float('inf')
    
    for student in students:
        try:
            stored_descriptor = np.array(json.loads(student.face_encoding))
            distance = norm(face_descriptor - stored_descriptor)
            
            if distance < threshold and distance < best_distance:
                best_distance = distance
                best_match = student
                
        except Exception as e:
            continue
            
    return best_match

@app.route('/api/mark-attendance', methods=['POST'])
@csrf.exempt
def mark_attendance():
    try:
        data = request.json
        face_descriptor = np.array(data['face_descriptor'])
        
        matched_student = find_matching_student(face_descriptor)
        if not matched_student:
            return jsonify({'error': 'No matching student found'}), 400
            
        attendance = Attendance(
            student_id=matched_student.id,
            session_id=data['session_id'],
            timestamp=datetime.now(),
            latitude=data['latitude'],
            longitude=data['longitude']
        )
        
        db.session.add(attendance)
        db.session.commit()
        
        return jsonify({
            'message': 'Attendance marked successfully',
            'student_name': matched_student.name
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/attendance/success/<studentname>')
def attendance_success( studentname):
    return render_template('attendance_success.html', student_name = studentname, datetime=datetime)

@app.route('/static/models/<path:filename>')
def serve_model(filename):
    return send_from_directory('static/models', filename)

@app.route('/debug/students')
def debug_students():
    students = Student.query.all()
    return jsonify([{
        'id': s.id,
        'name': s.name,
        'has_encoding': bool(s.face_encoding)
    } for s in students])

@app.route('/admin/students/delete/<int:student_id>', methods=['POST'])
@csrf.exempt
def delete_student(student_id):
    try:
        student = Student.query.get_or_404(student_id)
        db.session.delete(student)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Student deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# Add this function to get location name from coordinates
def get_location_name(latitude, longitude):
    try:
        geolocator = Nominatim(user_agent="attendance_system")
        location = geolocator.reverse(f"{latitude}, {longitude}", language='en')
        return location.address if location else "Location not found"
    except GeocoderTimedOut:
        return "Location lookup timed out"
    except Exception:
        return "Location lookup failed"

# Add this route to view session attendance
@app.route('/admin/attendance/<int:session_id>')
def session_attendance(session_id):
    session = Session.query.get_or_404(session_id)
    
    # Query all attendance records for this session with student information
    attendance_records = db.session.query(
        Attendance, Student
    ).join(
        Student, Attendance.student_id == Student.id
    ).filter(
        Attendance.session_id == session_id
    ).all()
    
    # Process attendance records to include location names
    attendance_data = []
    for attendance, student in attendance_records:
        location_name = get_location_name(attendance.latitude, attendance.longitude)
        attendance_data.append({
            'student': student,
            'attendance': attendance,
            'location': location_name
        })
    
    return render_template(
        'admin/session_attendance.html',
        session=session,
        attendance_data=attendance_data
    )

@app.route('/admin/sessions/delete/<int:session_id>', methods=['POST'])
@csrf.exempt
def delete_session(session_id):
    try:
        session = Session.query.get_or_404(session_id)
        
        # Delete all attendance records for this session
        Attendance.query.filter_by(session_id=session_id).delete()
        
        # Delete the session
        db.session.delete(session)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Session deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    print("WARNING: For camera access on all devices, this app must be served over HTTPS in production.")
    app.run(host='0.0.0.0', port=5000)