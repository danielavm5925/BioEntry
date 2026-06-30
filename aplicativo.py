from flask import Flask, render_template, Response, jsonify, request
import cv2
import os
import numpy as np
import faiss
from deepface import DeepFace
import sqlite3
from datetime import datetime
import shutil
import logging
import unicodedata


app = Flask(__name__)

#OCULTAR SPAM DE REQUESTS FLASK
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

#SQLITE
conn = sqlite3.connect("usuarios.db", check_same_thread=False)
cursor = conn.cursor()

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

#Config
DB_PATH   = "database"
THRESHOLD = 0.6

#Estado global de los embeddings
embeddings_store = {
    "embeddings": None,
    "labels":     [],
    "index":      None
}

def load_embeddings():
    """Carga (o recarga) embeddings desde la carpeta database/."""
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
                detector_backend  = "retinaface",
                enforce_detection = False
            )

            if objs:
                embeddings.append(objs[0]["embedding"])
                labels.append(os.path.splitext(file)[0])
                print(f"  ✓ {os.path.splitext(file)[0]}")

        except Exception as e:
            print("  Error:", e)

    if not embeddings:
        print("⚠️  No se cargaron embeddings.")
        return

    emb_arr = np.array(embeddings).astype("float32")
    faiss.normalize_L2(emb_arr)

    idx = faiss.IndexFlatIP(emb_arr.shape[1])
    idx.add(emb_arr)

    embeddings_store["embeddings"] = emb_arr
    embeddings_store["labels"]     = labels
    embeddings_store["index"]      = idx

    print(f"FAISS listo — {len(labels)} persona(s)")

load_embeddings()

#Métricas
metrics = {
    "total_ok":   0,
    "total_deny": 0
}

#Cámara
camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

face_data     = {"detected": False}
_last_logged  = {"name": None, "ts": 0}
current_person = None

#Video stream
def generate_frames():
    global face_data
    global current_person
    frame_count = 0

    while True:
        success, frame = camera.read()
        if not success:
            break

        frame_count += 1
        frame = cv2.flip(frame, 1)

        if frame_count % 15 == 0:
            try:
                objs = DeepFace.represent(
                    img_path          = frame,
                    model_name        = "ArcFace",
                    detector_backend  = "opencv",
                    enforce_detection = False
                )

                index  = embeddings_store["index"]
                labels = embeddings_store["labels"]

                if not objs or index is None:
                    face_data = {"detected": False}
                    current_person = None
                else:
                    obj         = objs[0]
                    embedding   = obj["embedding"]
                    facial_area = obj["facial_area"]

                    x = facial_area["x"]; y = facial_area["y"]
                    w = facial_area["w"]; h = facial_area["h"]

                    vec = np.array([embedding]).astype("float32")
                    faiss.normalize_L2(vec)

                    D, I   = index.search(vec, 1)
                    sim    = float(D[0][0])
                    conf   = round(sim * 100, 2)

                    if sim > 0.15:
                        print(f"Similitud: {sim:.4f}  |  {labels[I[0][0]]}")
                    else:
                        print(f"falsa alarma del detector, no hay nadie")

                    if sim > THRESHOLD:
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
                            "detected": True, "approved": True,
                            "name": nombre_real, "codigo": codigo,
                            "rol": rol, "programa": programa,
                            "confidence": conf,
                            "x": int(x), "y": int(y),
                            "w": int(w), "h": int(h)
                        }

                        if current_person != nombre_real:
                            _log_access(nombre_real, codigo, "aprobado", conf)
                            current_person = nombre_real

                    else:
                        if sim > 0.15:
                            face_data = {
                                "detected": True, "approved": False,
                                "name": "Desconocido", "codigo": "N/A",
                                "rol": "No registrado", "programa": "Acceso denegado",
                                "confidence": conf,
                                "x": int(x), "y": int(y),
                                "w": int(w), "h": int(h)
                            }

                            if current_person != "Desconocido":
                                _log_access("Desconocido", "N/A", "denegado", conf)
                                current_person = "Desconocido"
                        else:
                            face_data = {"detected": False}
                            current_person = None

            except Exception as e:
                print("Error:", e)

        if face_data.get("detected"):
            x = face_data["x"]; y = face_data["y"]
            w = face_data["w"]; h = face_data["h"]
            color = (0, 255, 0) if face_data["approved"] else (0, 0, 255)
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.putText(frame, face_data["name"],
                        (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        ret, buffer = cv2.imencode(".jpg", frame)
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" +
               buffer.tobytes() + b"\r\n")

#Helper log de acceso
def _log_access(nombre, codigo, resultado, confianza):
    now = datetime.now().timestamp()
    if _last_logged["name"] == nombre and (now - _last_logged["ts"]) < 5:
        return
    _last_logged["name"] = nombre
    _last_logged["ts"]   = now
    cursor.execute(
        "INSERT INTO accesos (nombre, codigo, resultado, confianza) VALUES (?, ?, ?, ?)",
        (nombre, codigo, resultado, confianza)
    )
    conn.commit()
    if resultado == "aprobado":
        metrics["total_ok"]   += 1
    else:
        metrics["total_deny"] += 1

#Rutas - vistas
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/video")
def video():
    return Response(generate_frames(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/face_data")
def get_face_data():
    return jsonify(face_data)

@app.route("/metrics")
def get_metrics():

    today = datetime.now().strftime("%Y-%m-%d")

    cursor.execute(
        "SELECT COUNT(*) FROM accesos "
        "WHERE resultado='aprobado' AND DATE(timestamp) = ?",
        (today,)
    )
    total_ok = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM accesos "
        "WHERE resultado='denegado' AND DATE(timestamp) = ?",
        (today,)
    )
    total_deny = cursor.fetchone()[0]

    cursor.execute(
        "SELECT nombre, codigo, resultado, confianza, timestamp "
        "FROM accesos "
        "WHERE DATE(timestamp) = ? "
        "ORDER BY id DESC LIMIT 6",
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
        "registered": len(embeddings_store["labels"]),
        "total_ok":   total_ok,
        "total_deny": total_deny,
        "history":    history
    })

#Rutas - Admin
ADMIN_PASSWORD = "uao2026"

@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json()
    if data.get("password") == ADMIN_PASSWORD:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Contraseña incorrecta"}), 401


@app.route("/admin/usuarios")
def admin_usuarios():
    cursor.execute(
        "SELECT id, nombre, codigo, rol, programa, archivo FROM usuarios ORDER BY id DESC"
    )
    rows = cursor.fetchall()
    return jsonify([
        {"id": r[0], "nombre": r[1], "codigo": r[2],
         "rol": r[3], "programa": r[4], "archivo": r[5]}
        for r in rows
    ])

def normalizar_texto(texto):
    """Quita tildes/diacríticos y caracteres no-ASCII, deja solo letras/números."""
    # Descompone caracteres acentuados (á -> a + tilde) y descarta la tilde
    nfkd = unicodedata.normalize('NFKD', texto)
    sin_tildes = ''.join(c for c in nfkd if not unicodedata.combining(c))
    # Deja solo letras y números (sin espacios ni símbolos)
    return ''.join(c for c in sin_tildes if c.isalnum())

@app.route("/admin/agregar", methods=["POST"])
def admin_agregar():
    nombre   = request.form.get("nombre", "").strip()
    codigo   = request.form.get("codigo", "").strip()
    rol      = request.form.get("rol", "").strip()
    programa = request.form.get("programa", "").strip()
    foto     = request.files.get("foto")

    if not all([nombre, codigo, rol, programa, foto]):
        return jsonify({"ok": False, "error": "Faltan campos"}), 400
    
    # Validar código duplicado 
    cursor.execute("SELECT nombre FROM usuarios WHERE codigo = ?", (codigo,))
    existente = cursor.fetchone()
    if existente:
        return jsonify({
            "ok": False,
            "error": f"El código {codigo} ya está registrado para {existente[0]}."
        }), 409

    # Nombre de archivo basado en el código (sin tildes, espacios ni caracteres especiales)
    codigo_limpio = normalizar_texto(codigo)
    nombre_limpio = normalizar_texto(nombre)
    nombre_archivo = f"{codigo_limpio}_{nombre_limpio}" + os.path.splitext(foto.filename)[1].lower()
    ruta_foto      = os.path.join(DB_PATH, nombre_archivo)

    foto.save(ruta_foto)

    try:
        cursor.execute(
            "INSERT INTO usuarios (nombre, codigo, rol, programa, archivo) "
            "VALUES (?, ?, ?, ?, ?)",
            (nombre, codigo, rol, programa, nombre_archivo)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        os.remove(ruta_foto)
        return jsonify({"ok": False, "error": "El usuario ya existe"}), 409

    # Validar que la foto SÍ tenga un rostro detectable antes de aceptarla
    try:
        test_objs = DeepFace.represent(
            img_path=ruta_foto,
            model_name="ArcFace",
            detector_backend="retinaface",
            enforce_detection=True
        )
    except Exception as e:
        print(f"Error validando rostro: {e}")
        test_objs = None

    if not test_objs:
        # Revertir: la foto no sirve, no dejamos al usuario registrado a medias
        cursor.execute("DELETE FROM usuarios WHERE archivo = ?", (nombre_archivo,))
        conn.commit()
        os.remove(ruta_foto)
        return jsonify({
            "ok": False,
            "error": "No se detectó ningún rostro en la foto. Intenta con otra imagen, de frente y con buena iluminación."
        }), 422

    load_embeddings()
    return jsonify({"ok": True, "archivo": nombre_archivo})


@app.route("/admin/eliminar/<int:uid>", methods=["DELETE"])
def admin_eliminar(uid):
    cursor.execute("SELECT archivo FROM usuarios WHERE id = ?", (uid,))
    row = cursor.fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Usuario no encontrado"}), 404

    archivo = row[0]
    ruta    = os.path.join(DB_PATH, archivo)

    if os.path.exists(ruta):
        os.remove(ruta)

    cursor.execute("DELETE FROM usuarios WHERE id = ?", (uid,))
    conn.commit()

    load_embeddings()
    return jsonify({"ok": True})


#run
if __name__ == "__main__":
    app.run(debug=True)