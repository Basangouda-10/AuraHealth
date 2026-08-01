import os
import sqlite3

DB_NAME = "aurahealth.db"
CAPTURE_DIR = "captured_faces"

# 1. Clear database tables
if os.path.exists(DB_NAME):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM attendance")
    cursor.execute("DELETE FROM schedules")
    cursor.execute("DELETE FROM staff")
    conn.commit()
    conn.close()
    print("[SUCCESS] Database tables wiped clean.")

# 2. Clear stored snapshot images
if os.path.exists(CAPTURE_DIR):
    for filename in os.listdir(CAPTURE_DIR):
        file_path = os.path.join(CAPTURE_DIR, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)
    print("[SUCCESS] Captured face images removed.")

print("\nSystem completely reset! You can now start registering fresh profiles.")