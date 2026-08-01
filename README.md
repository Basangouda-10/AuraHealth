🏥 AuraHealth AI Kiosk

AuraHealth AI Kiosk is an intelligent, edge-computed hospital administrative and biometric check-in terminal. Built with Flask, OpenCV, `face_recognition`, SQLite, and local Llama 3 via Ollama, it provides real-time staff identification, dynamic shift management, interactive clinical tasks, and instant administrative control.

🌟 Key Features

* Biometric Face Check-In & Check-Out: Real-time facial detection and matching using 128-dimensional encodings.
* Shift Attendance Tracking: Automatically categorizes timestamps into Indian Standard Time (IST) and tracks shift types (Morning, Evening, Night) alongside active status (`Checked-In` / `Checked-Out`).
* Interactive Enrolment: Register new staff members with single-face validation and dedicated dropdown choices for roles and departments.
* Clinical Task Engine: Automatically populates staff task lists based on clinical priority, highlighting emergency and ICU tasks.
* Local Medical AI Assistant: Runs on local Llama 3 (`ollama`) to provide private clinical summaries and triage advice without cloud dependency.
* Administrative Controls: Row-by-row attendance record deletion or full system database resets right from the UI.

🛠️ Tech Stack

* Backend: Python 3.9+, Flask
* Computer Vision: OpenCV (`cv2`), `face_recognition`, NumPy
* Database: SQLite3 (`aurahealth.db`)
* Local LLM: Ollama (`llama3:latest`)
* Frontend: HTML5, Modern CSS, Bootstrap 5, FontAwesome 6, Vanilla JavaScript (Fetch API)

📁 Project Structure

--text
aurahealth-kiosk/
├── app.py                  Core Flask server, routing, DB operations, and vision logic
├── aurahealth.db           SQLite database (auto-generated on startup)
└── templates/
    ├── index.html          Main Kiosk interface (Webcam stream, Check-In, Logs, Enrolment)
    └── dashboard.html      Staff Clinical Dashboard (Tasks, AI Assistant, Shift Check-Out)