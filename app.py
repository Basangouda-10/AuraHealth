import os
import cv2
import sqlite3
import requests
import numpy as np
import face_recognition
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response

app = Flask(__name__)
DB_NAME = 'aurahealth.db'

# Global reference to retain the latest camera frame from the video stream
latest_frame = None


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Staff table storing 128-d face encodings as BLOB
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS staff (
            staff_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            department TEXT NOT NULL,
            face_encoding BLOB NOT NULL
        )
    ''')
    
    # Attendance table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (staff_id) REFERENCES staff (staff_id)
        )
    ''')
    
    # Tasks table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER NOT NULL,
            time TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            priority TEXT DEFAULT 'Normal',
            FOREIGN KEY (staff_id) REFERENCES staff (staff_id)
        )
    ''')
    
    conn.commit()
    conn.close()


# Initialize DB on startup
init_db()


def gen_frames():
    """Generates continuous live JPEG camera frames and updates global frame cache."""
    global latest_frame
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    while True:
        success, frame = cap.read()
        if not success:
            break
        else:
            latest_frame = frame.copy()
            ret, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    cap.release()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/dashboard')
def dashboard():
    staff_id = request.args.get('staff_id')
    staff = None
    
    if staff_id:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT name, role, department FROM staff WHERE staff_id = ?", (staff_id,))
        staff = cursor.fetchone()
        conn.close()

    return render_template('dashboard.html', staff_id=staff_id, staff=staff)


@app.route('/video_feed')
def video_feed():
    """Live streaming route for video feed element."""
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/authenticate_checkin', methods=['POST'])
def authenticate_checkin():
    global latest_frame

    if latest_frame is None:
        return jsonify({'success': False, 'message': 'Camera capture failed. Please ensure webcam feed is active.'})

    rgb_frame = cv2.cvtColor(latest_frame, cv2.COLOR_BGR2RGB)
    unknown_encodings = face_recognition.face_encodings(rgb_frame)

    if not unknown_encodings:
        return jsonify({'success': False, 'message': 'No face detected in camera feed. Please position face clearly.'})

    unknown_encoding = unknown_encodings[0]

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT staff_id, name, role, department, face_encoding FROM staff")
    all_staff = cursor.fetchall()

    matched_staff = None
    for staff in all_staff:
        staff_id, name, role, department, db_encoding_bytes = staff
        
        if not db_encoding_bytes:
            continue

        db_encoding = np.frombuffer(db_encoding_bytes, dtype=np.float64)
        
        matches = face_recognition.compare_faces([db_encoding], unknown_encoding, tolerance=0.55)
        if matches[0]:
            matched_staff = {
                'id': staff_id,
                'name': name,
                'role': role,
                'department': department
            }
            break

    if matched_staff:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO attendance (staff_id, timestamp, status) VALUES (?, ?, ?)",
                       (matched_staff['id'], timestamp, 'Checked-In'))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'staff': matched_staff})
    else:
        conn.close()
        return jsonify({'success': False, 'message': 'Biometric identification failed. Staff record not found.'})


@app.route('/register_staff', methods=['POST'])
def register_staff():
    global latest_frame
    name = request.form.get('name')
    role = request.form.get('role')
    department = request.form.get('department')

    if not name or not role or not department:
        return jsonify({'success': False, 'message': 'All fields are required.'})

    if latest_frame is None:
        return jsonify({'success': False, 'message': 'Camera capture failed during registration.'})

    rgb_frame = cv2.cvtColor(latest_frame, cv2.COLOR_BGR2RGB)
    face_locations = face_recognition.face_locations(rgb_frame)

    if len(face_locations) == 0:
        return jsonify({'success': False, 'message': 'No face detected. Please face the camera.'})
    if len(face_locations) > 1:
        return jsonify({'success': False, 'message': 'Multiple people detected! Please stand alone in frame.'})

    new_encoding = face_recognition.face_encodings(rgb_frame, face_locations)[0]

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT staff_id, name, face_encoding FROM staff")
    existing_staff = cursor.fetchall()

    for staff in existing_staff:
        s_id, s_name, s_encoding_bytes = staff
        if not s_encoding_bytes:
            continue
        db_encoding = np.frombuffer(s_encoding_bytes, dtype=np.float64)
        
        matches = face_recognition.compare_faces([db_encoding], new_encoding, tolerance=0.50)
        if matches[0]:
            conn.close()
            return jsonify({
                'success': False, 
                'message': f'This face is already registered to Dr./Staff member "{s_name}"!'
            })

    encoding_bytes = new_encoding.tobytes()
    cursor.execute("INSERT INTO staff (name, role, department, face_encoding) VALUES (?, ?, ?, ?)",
                   (name, role, department, encoding_bytes))
    staff_id = cursor.lastrowid

    # Populate default agenda tasks
    demo_tasks = [
        (staff_id, '08:30 AM', 'Emergency', 'CRITICAL: Patient in ICU Bed 04 showing abnormal ECG trends', 'Pending', 'Critical'),
        (staff_id, '09:00 AM', 'Rounds', 'Morning Patient Rounds - ICU Bed 04', 'Pending', 'Normal'),
        (staff_id, '11:30 AM', 'Emergency', 'Emergency Consult - Cardiac Department', 'Pending', 'Critical'),
        (staff_id, '02:00 PM', 'Meeting', 'Department Shift Sync & Briefing', 'Pending', 'Normal')
    ]
    cursor.executemany("INSERT INTO tasks (staff_id, time, category, title, status, priority) VALUES (?, ?, ?, ?, ?, ?)", demo_tasks)

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': f'Dr./Staff "{name}" registered successfully!'})


@app.route('/logout/<int:staff_id>', methods=['POST', 'GET'])
def logout(staff_id):
    """Logs the staff member out and records a Checked-Out timestamp."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute(
            "INSERT INTO attendance (staff_id, timestamp, status) VALUES (?, ?, ?)",
            (staff_id, timestamp, 'Checked-Out')
        )
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Logged out successfully!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/get_staff_dashboard/<int:staff_id>', methods=['GET'])
def get_staff_dashboard(staff_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT staff_id, name, role, department FROM staff WHERE staff_id = ?", (staff_id,))
    staff = cursor.fetchone()

    if not staff:
        conn.close()
        return jsonify({'success': False, 'message': 'Staff member not found.'})

    cursor.execute("""
        SELECT task_id, time, category, title, status, priority 
        FROM tasks 
        WHERE staff_id = ? 
        ORDER BY 
            CASE 
                WHEN priority = 'Critical' THEN 1
                WHEN category = 'Emergency' THEN 1
                ELSE 2
            END,
            task_id ASC
    """, (staff_id,))
    
    tasks = cursor.fetchall()
    conn.close()

    staff_data = {'id': staff[0], 'name': staff[1], 'role': staff[2], 'department': staff[3]}
    
    all_tasks = []
    critical_alerts = []

    for t in tasks:
        task_dict = {'id': t[0], 'time': t[1], 'category': t[2], 'title': t[3], 'status': t[4], 'priority': t[5]}
        all_tasks.append(task_dict)
        if (t[5] == 'Critical' or t[2] == 'Emergency') and t[4] != 'Completed':
            critical_alerts.append(task_dict)

    return jsonify({
        'success': True, 
        'staff': staff_data, 
        'tasks': all_tasks,
        'critical_alerts': critical_alerts
    })


@app.route('/sync_shift_updates/<int:staff_id>', methods=['GET'])
def sync_shift_updates(staff_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT task_id, time, category, title, priority 
        FROM tasks 
        WHERE staff_id = ? AND status = 'Pending'
        ORDER BY 
            CASE WHEN priority = 'Critical' THEN 1 ELSE 2 END,
            task_id DESC LIMIT 1
    """, (staff_id,))
    
    latest_task = cursor.fetchone()
    conn.close()

    shift_info = {
        'shift_name': 'Active Shift',
        'shift_hours': '08:00 AM - 04:00 PM',
        'active_update': latest_task[3] if latest_task else 'All shift tasks up-to-date.'
    }

    return jsonify({'success': True, 'shift_info': shift_info})


@app.route('/get_attendance_logs', methods=['GET'])
def get_attendance_logs():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            a.log_id, 
            s.name, 
            s.role, 
            s.department, 
            a.timestamp, 
            s.face_encoding,
            a.status
        FROM attendance a 
        JOIN staff s ON a.staff_id = s.staff_id 
        ORDER BY a.log_id DESC
    """)
    logs = cursor.fetchall()
    conn.close()

    formatted_logs = []
    for row in logs:
        raw_ts = row[4]
        try:
            dt = datetime.strptime(raw_ts, "%Y-%m-%d %H:%M:%S")
            hour = dt.hour
            if 6 <= hour < 14:
                shift = "Morning Shift"
            elif 14 <= hour < 22:
                shift = "Evening Shift"
            else:
                shift = "Night Shift"
            
            ist_time = dt.strftime("%Y-%m-%d %I:%M:%S %p") + " IST"
        except Exception:
            shift = "Morning Shift"
            ist_time = raw_ts + " IST"

        has_face = "Enrolled ✓" if row[5] else "Not Enrolled"

        formatted_logs.append({
            'log_id': row[0],
            'name': row[1],
            'role': row[2],
            'department': row[3],
            'ist_time': ist_time,
            'shift': shift,
            'face_enrolled': has_face,
            'status': row[6]
        })

    return jsonify({'success': True, 'logs': formatted_logs})


@app.route('/delete_log/<int:log_id>', methods=['DELETE', 'POST'])
def delete_log(log_id):
    """Deletes a single attendance log entry."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM attendance WHERE log_id = ?", (log_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Log deleted successfully.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/reset_database', methods=['POST', 'DELETE'])
def reset_database():
    """Endpoint to clear all database tables."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM attendance;")
        cursor.execute("DELETE FROM tasks;")
        cursor.execute("DELETE FROM staff;")
        cursor.execute("DELETE FROM sqlite_sequence;")
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Database reset successfully!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/update_task_status', methods=['POST'])
def update_task_status():
    data = request.json
    task_id = data.get('task_id')
    status = data.get('status')

    if not task_id or not status:
        return jsonify({'success': False, 'message': 'Missing task_id or status.'})

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET status = ? WHERE task_id = ?", (status, task_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Task status updated.'})


@app.route('/ai_assistant', methods=['POST'])
def ai_assistant():
    data = request.json
    user_prompt = data.get('prompt', '')
    staff_id = data.get('staff_id')

    if not user_prompt:
        return jsonify({'success': False, 'message': 'Prompt is required.'})

    context_str = ""
    if staff_id:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT name, department FROM staff WHERE staff_id = ?", (staff_id,))
        staff_info = cursor.fetchone()
        if staff_info:
            context_str = f"You are assisting {staff_info[0]} in the {staff_info[1]} department."
        conn.close()

    system_instruction = (
        f"{context_str} You are AuraHealth AI Assistant running locally. "
        "Provide concise, professional medical triage summaries, shift updates, "
        "or clinical advice. Keep answers under 3-4 bullet points."
    )

    try:
        response = requests.post(
            'http://127.0.0.1:11434/api/generate',
            json={
                'model': 'llama3:latest',
                'prompt': f"{system_instruction}\n\nUser Question: {user_prompt}",
                'stream': False,
                'options': {'num_predict': 200}
            },
            timeout=120
        )
        
        if response.status_code == 200:
            ai_response = response.json().get('response', '')
            return jsonify({'success': True, 'response': ai_response})
        else:
            return jsonify({'success': False, 'message': f'Ollama error status code: {response.status_code}'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Ollama connection error: {str(e)}'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)