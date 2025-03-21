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
    student_id = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    face_encoding = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)
    qr_code = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('session.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

class Classroom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    coordinates = db.Column(db.Text, nullable=False)  # Store coordinates as a JSON string

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
            
            # Check if the student ID already exists
            existing_student = Student.query.filter_by(student_id=data.get('student_id')).first()
            if existing_student:
                return jsonify({'success': False, 'error': 'Student ID already exists'}), 400
            
            # Validate student ID format
            student_id = data.get('student_id', '')
            if not student_id.isdigit() or len(student_id) != 10:
                return jsonify({'success': False, 'error': 'Invalid student ID format. Must be 10 digits'}), 400
            
            # Get face descriptor and ensure it's properly formatted
            face_descriptor = data.get('face_descriptor', [])
            if isinstance(face_descriptor, str):
                face_descriptor = face_descriptor.strip("'")
                face_descriptor = json.loads(face_descriptor)
            
            # Ensure it's a valid list of floats
            face_descriptor = [float(x) for x in face_descriptor]
            
            # Store as a clean JSON string
            face_encoding = json.dumps(face_descriptor)
            
            student = Student(
                student_id=student_id,
                name=data.get('name', 'Unknown'),
                face_encoding=face_encoding
            )
            
            db.session.add(student)
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'Student added successfully!'})
        except Exception as e:
            print(f"Error saving student: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 400
        
    return render_template('admin/new_student.html')

@app.route('/admin/sessions/new', methods=['GET', 'POST'])
def new_session():
    import logging

    # Configure logging
    logging.basicConfig(level=logging.INFO)

    if request.method == 'POST':
        try:
            name = request.form['name']
            classroom_id = request.form['classroom_id']
            date = datetime.strptime(request.form['date'], '%Y-%m-%d')
            
            session = Session(name=name, date=date, classroom_id=classroom_id)
            logging.info("Session created successfully.")

            db.session.add(session)
            db.session.commit()
            
            # Generate QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(f"{request.host_url}attendance/{session.id}")
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            qr_code = base64.b64encode(buffered.getvalue()).decode()
            
            session.qr_code = qr_code
            db.session.commit()
            
            flash('Session created successfully!', 'success')
            logging.info("Redirecting to admin dashboard.")
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            logging.error(f"Error creating session: {str(e)}")  # Log the error
            flash('Error creating session. Please try again.', 'error')
            return redirect(url_for('admin_dashboard'))

    classrooms = Classroom.query.all()  # Or however you fetch your classrooms
    return render_template('admin/new_session.html', classrooms=classrooms)

@app.route('/attendance/<int:session_id>')
def attendance(session_id):
    session = Session.query.get_or_404(session_id)
    return render_template('attendance.html', session=session)

def find_matching_student(face_descriptor, threshold=0.35):
    students = Student.query.filter(Student.face_encoding.isnot(None)).all()
    
    print(f"Total students with face encodings: {len(students)}")
    
    best_match = None
    best_distance = float('inf')
    
    # Convert input face_descriptor to numpy array if it isn't already
    face_descriptor = np.array(face_descriptor, dtype=np.float64)
    
    for student in students:
        try:
            # Parse the stored face encoding from JSON string to numpy array
            stored_descriptor = np.array(json.loads(student.face_encoding.strip("'")), dtype=np.float64)
            
            # Calculate distance
            distance = norm(face_descriptor - stored_descriptor)
            print(f"Distance for {student.name}: {distance}")
            
            if distance < threshold and distance < best_distance:
                best_distance = distance
                best_match = student
                
        except Exception as e:
            print(f"Error processing student {student.name}: {str(e)}")
            # Try to clean up the stored encoding and retry
            try:
                # Remove any extra quotes and spaces
                cleaned_encoding = student.face_encoding.strip("'").replace("'", '"')
                stored_descriptor = np.array(json.loads(cleaned_encoding), dtype=np.float64)
                
                distance = norm(face_descriptor - stored_descriptor)
                print(f"Distance for {student.name} (after cleanup): {distance}")
                
                if distance < threshold and distance < best_distance:
                    best_distance = distance
                    best_match = student
            except Exception as e2:
                print(f"Failed second attempt for {student.name}: {str(e2)}")
                continue
    
    if best_match:
        print(f"\nBest match found: {best_match.name} with distance: {best_distance}")
    else:
        print("\nNo match found above threshold")
    
    return best_match

def point_inside_polygon(point, polygon_coords):
    """
    Check if a point is inside a polygon using ray casting algorithm
    point: tuple of (latitude, longitude)
    polygon_coords: list of tuples [(lat1, lon1), (lat2, lon2), ...]
    """
    x, y = point
    n = len(polygon_coords)
    inside = False
    
    p1x, p1y = polygon_coords[0]
    for i in range(n + 1):
        p2x, p2y = polygon_coords[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    
    return inside

@app.route('/api/mark-attendance', methods=['POST'])
@csrf.exempt
def mark_attendance():
    try:
        data = request.json
        face_descriptor = np.array(data['face_descriptor'])
        session_id = data['session_id']
        latitude = data['latitude']
        longitude = data['longitude']
        
        # Get the session and its classroom
        session = Session.query.get_or_404(session_id)
        classroom = Classroom.query.get_or_404(session.classroom_id)
        
        # Parse classroom coordinates
        classroom_coords = json.loads(classroom.coordinates)
        polygon_coords = []
        for coord in classroom_coords:
            lat, lon = map(float, coord.split(','))
            polygon_coords.append((lat, lon))
        
        # Check if student is in classroom
        is_in_classroom = point_inside_polygon((float(latitude), float(longitude)), polygon_coords)
        
        matched_student = find_matching_student(face_descriptor)
        if not matched_student:
            return jsonify({
                'message': 'User not recognized',
                'student_name': 'Unknown',
                'in_classroom': is_in_classroom
            }), 200
        
        attendance = Attendance(
            student_id=matched_student.id,
            session_id=session_id,
            timestamp=datetime.now(),
            latitude=latitude,
            longitude=longitude
        )
        
        db.session.add(attendance)
        db.session.commit()
        
        return jsonify({
            'message': 'Attendance marked successfully',
            'student_name': matched_student.name,
            'in_classroom': is_in_classroom
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/attendance/success/<studentname>')
def attendance_success(studentname):
    in_classroom = request.args.get('in_classroom', 'true').lower() == 'true'
    return render_template('attendance_success.html', 
                         student_name=studentname, 
                         datetime=datetime,
                         in_classroom=in_classroom)

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

@app.route('/admin/classrooms/new', methods=['GET', 'POST'])
@csrf.exempt
def new_classroom():
    if request.method == 'POST':
        name = request.form['name']
        try:
            corner1 = request.form['corner1']
            corner2 = request.form['corner2']
            corner3 = request.form['corner3']
            corner4 = request.form['corner4']
            
            # Log the received coordinates for debugging
            print(f"Received coordinates: corner1={corner1}, corner2={corner2}, corner3={corner3}, corner4={corner4}")
            
            # Validate that all corners are provided
            if not all([corner1, corner2, corner3, corner4]):
                return jsonify({'success': False, 'error': 'All corners must be provided.'}), 400
            
            # Create a new classroom
            classroom = Classroom(
                name=name,
                coordinates=json.dumps([corner1, corner2, corner3, corner4])  # Store corners as JSON
            )
            
            db.session.add(classroom)
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'Classroom added successfully!'})
        except Exception as e:
            print(f"Error saving classroom: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 400
    
    # Render the form for adding a new classroom
    return render_template('admin/new_classroom.html')

@app.route('/admin/classrooms')
def list_classrooms():
    classrooms = Classroom.query.all()
    return render_template('admin/classrooms.html', classrooms=classrooms)

@app.route('/admin/classrooms/edit/<int:classroom_id>', methods=['GET', 'POST'])
@csrf.exempt
def edit_classroom(classroom_id):
    classroom = Classroom.query.get_or_404(classroom_id)
    
    if request.method == 'POST':
        try:
            name = request.form['name']
            corner1 = request.form['corner1']
            corner2 = request.form['corner2']
            corner3 = request.form['corner3']
            corner4 = request.form['corner4']
            
            # Validate that all corners are provided
            if not all([corner1, corner2, corner3, corner4]):
                return jsonify({'success': False, 'error': 'All corners must be provided.'}), 400
            
            # Update classroom
            classroom.name = name
            classroom.coordinates = json.dumps([corner1, corner2, corner3, corner4])
            
            db.session.commit()
            return jsonify({'success': True, 'message': 'Classroom updated successfully!'})
        except Exception as e:
            print(f"Error updating classroom: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 400
    
    coordinates = json.loads(classroom.coordinates)
    return render_template('admin/edit_classroom.html', classroom=classroom, coordinates=coordinates)

@app.route('/admin/classrooms/delete/<int:classroom_id>', methods=['POST'])
@csrf.exempt
def delete_classroom(classroom_id):
    try:
        classroom = Classroom.query.get_or_404(classroom_id)
        
        # Check if classroom is being used in any sessions
        sessions = Session.query.filter_by(classroom_id=classroom_id).first()
        if sessions:
            return jsonify({
                'success': False, 
                'error': 'Cannot delete classroom as it is being used in one or more sessions.'
            }), 400
        
        db.session.delete(classroom)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Classroom deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    print("WARNING: For camera access on all devices, this app must be served over HTTPS in production.")
    app.run(host='0.0.0.0', port=5000)
