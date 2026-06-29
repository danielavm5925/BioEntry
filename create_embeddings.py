from flask import Flask, render_template, Response, jsonify
import cv2
import os
import numpy as np
import faiss
from deepface import DeepFace
import sqlite3
from datetime import datetime

app = Flask(__name__)

# ============================================
# SQLITE — usuarios + accesos
# ============================================

conn = sqlite3.connect("usuarios.db", check_same_thread=False)
cursor = conn.cursor()

# Crear tabla de accesos si no existe
cursor.execute("""
CREATE TABLE IF NOT EXISTS accesos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre    TEXT,
    codigo    TEXT,
    resultado TEXT,
    confianza REAL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# ============================================
# CONFIG
# ============================================

DB_PATH   = "database"
THRESHOLD = 0.6          # menor = más estricto

# ============================================
# CARGAR EMBEDDINGS
# ============================================

embeddings = []
labels     = []

print("Cargando base de rostros...")

for file in os.listdir(DB_PATH):

    if not file.lower().endswith((".jpg", ".jpeg", ".png")):
        continue

    path = os.path.join(DB_PATH, file)

    try:

        objs = DeepFace.represent(
            img_path          = path,
            model_name        = "ArcFace",
            detector_backend  = "retinaface",   # ← igual que al construir la BD
            enforce_detection = False
        )

        if objs:
            embeddings.append(objs[0]["embedding"])
            labels.append(os.path.splitext(file)[0])
            print(f"  ✓ {os.path.splitext(file)[0]}")

    except Exception as e:
        print("  Error:", e)

embeddings = np.array(embeddings).astype("float32")
faiss.normalize_L2(embeddings)
dimension  = embeddings.shape[1]

# ============================================
# FAISS
# ============================================

index = faiss.IndexFlatIP(dimension)
index.add(embeddings)

print(f"FAISS listo — {len(labels)} persona(s) registrada(s)")

# ============================================
# MÉTRICAS EN MEMORIA (para el endpoint)
# ============================================

metrics = {
    "total_ok":   0,
    "total_deny": 0,
    "registered": len(labels)
}

# ============================================
# WEBCAM
# ============================================

camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

face_data = {"detected": False}

# último acceso registrado para no duplicar en BD
_last_logged = {"name": None, "ts": 0}

# ============================================
# VIDEO STREAM
# ============================================

def generate_frames():

    global face_data

    frame_count = 0

    while True:

        success, frame = camera.read()

        if not success:
            break

        frame_count += 1
        frame = cv2.flip(frame, 1)

        # ── Preprocesamiento: ecualización de histograma ──────────────────
        ycrcb              = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
        ycrcb[:, :, 0]     = cv2.equalizeHist(ycrcb[:, :, 0])
        frame_proc         = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)
        # ─────────────────────────────────────────────────────────────────

        # Analizar cada 20 frames para reducir lag con retinaface
        if frame_count % 20 == 0:

            try:

                objs = DeepFace.represent(
                    img_path          = frame_proc,
                    model_name        = "ArcFace",
                    detector_backend  = "retinaface",   # ← consistente con build
                    enforce_detection = False
                )

                if not objs:

                    face_data = {"detected": False}

                else:

                    obj          = objs[0]
                    embedding    = obj["embedding"]
                    facial_area  = obj["facial_area"]

                    x = facial_area["x"];  y = facial_area["y"]
                    w = facial_area["w"];  h = facial_area["h"]

                    vec = np.array([embedding]).astype("float32")
                    faiss.normalize_L2(vec)

                    D, I = index.search(vec, 1)
                    similarity = float(D[0][0])
                    confidence = round(similarity * 100, 2)

                    print(f"Similitud: {similarity:.4f}  |  Persona: {labels[I[0][0]]}")

                    # ── RECONOCIDO ────────────────────────────────────────
                    if similarity > THRESHOLD:

                        name = labels[I[0][0]]

                        cursor.execute(
                            "SELECT nombre, codigo, rol, programa "
                            "FROM usuarios WHERE archivo LIKE ?",
                            (f"{name}%",)
                        )
                        user = cursor.fetchone()

                        if user:
                            nombre_real, codigo, rol, programa = user
                        else:
                            nombre_real = name
                            codigo = rol = programa = "N/A"

                        face_data = {
                            "detected":  True,
                            "approved":  True,
                            "name":      nombre_real,
                            "codigo":    codigo,
                            "rol":       rol,
                            "programa":  programa,
                            "confidence": confidence,
                            "x": int(x), "y": int(y),
                            "w": int(w), "h": int(h)
                        }

                        _log_access(nombre_real, codigo, "aprobado", confidence)

                    # ── DESCONOCIDO ───────────────────────────────────────
                    else:

                        if similarity > 0.15:

                            face_data = {
                                "detected":  True,
                                "approved":  False,
                                "name":      "Desconocido",
                                "codigo":    "N/A",
                                "rol":       "No registrado",
                                "programa":  "Acceso denegado",
                                "confidence": confidence,
                                "x": int(x), "y": int(y),
                                "w": int(w), "h": int(h)
                            }

                            _log_access("Desconocido", "N/A", "denegado", confidence)

                        else:

                            face_data = {"detected": False}

            except Exception as e:
                print("Error:", e)

        # ── Dibujar resultado ─────────────────────────────────────────────
        if face_data.get("detected"):

            x = face_data["x"];  y = face_data["y"]
            w = face_data["w"];  h = face_data["h"]
            color = (0, 255, 0) if face_data["approved"] else (0, 0, 255)

            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.putText(
                frame, face_data["name"],
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2
            )

        ret, buffer = cv2.imencode(".jpg", frame)
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" +
            buffer.tobytes() +
            b"\r\n"
        )

# ============================================
# HELPER: registrar acceso sin duplicar
# ============================================

def _log_access(nombre, codigo, resultado, confianza):
    """Guarda el acceso en la BD y actualiza métricas.
    Evita duplicados: no registra el mismo nombre si pasaron < 5 s."""

    now = datetime.now().timestamp()

    if _last_logged["name"] == nombre and (now - _last_logged["ts"]) < 5:
        return

    _last_logged["name"] = nombre
    _last_logged["ts"]   = now

    cursor.execute(
        "INSERT INTO accesos (nombre, codigo, resultado, confianza) "
        "VALUES (?, ?, ?, ?)",
        (nombre, codigo, resultado, confianza)
    )
    conn.commit()

    if resultado == "aprobado":
        metrics["total_ok"]   += 1
    else:
        metrics["total_deny"] += 1

# ============================================
# ROUTES
# ============================================

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/video")
def video():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

@app.route("/face_data")
def get_face_data():
    return jsonify(face_data)

@app.route("/metrics")
def get_metrics():
    """Devuelve contadores globales + historial de hoy."""

    today = datetime.now().strftime("%Y-%m-%d")

    cursor.execute(
        "SELECT nombre, codigo, resultado, confianza, timestamp "
        "FROM accesos "
        "WHERE DATE(timestamp) = ? "
        "ORDER BY timestamp DESC LIMIT 50",
        (today,)
    )

    rows = cursor.fetchall()
    history = [
        {
            "nombre":    r[0],
            "codigo":    r[1],
            "resultado": r[2],
            "confianza": r[3],
            "timestamp": r[4]
        }
        for r in rows
    ]

    return jsonify({
        "registered": metrics["registered"],
        "total_ok":   metrics["total_ok"],
        "total_deny": metrics["total_deny"],
        "history":    history
    })

# ============================================
# RUN
# ============================================

if __name__ == "__main__":
    app.run(debug=True)