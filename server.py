from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import urllib.request
import urllib.error
import traceback
import re

app = Flask(__name__)
CORS(app)

# ==============================================================================
# CONEXIÓN A BASE DE DATOS (MONGODB) CON TIMEOUT BLINDADO
# ==============================================================================
MONGO_URI = os.environ.get("MONGO_URI", "").strip()
perfil_col = None

if MONGO_URI:
    try:
        import pymongo
        import certifi
        # Agregamos serverSelectionTimeoutMS=2500 para que máximo espere 2.5s y no congele el servidor
        client = pymongo.MongoClient(
            MONGO_URI, 
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=2500
        )
        db = client["logan_db"]
        perfil_col = db["perfil"]
        print("✅ Conectado exitosamente a MongoDB Atlas")
    except Exception as e:
        print("⚠️ Error conectando a MongoDB Atlas:", e)
estado_rele = "OFF"
cola_ordenes_pc = []  # COLA DE MENSAJES (Sustituye la variable única para no perder órdenes)
HISTORIAL = []       
MAX_HISTORIAL = 10   

def cargar_perfil():
    if perfil_col is not None:
        try:
            doc = perfil_col.find_one({"_id": "usuario_principal"})
            if doc:
                doc.pop("_id", None)
                return doc
        except Exception as e:
            print("⚠️ Error leyendo perfil de DB:", e)
            
    return {
        "nombre_usuario": "Amigo",
        "trato": "informal, cercano y natural",
        "gustos_y_datos": {}
    }

def guardar_perfil(perfil):
    if perfil_col is not None:
        try:
            perfil_col.update_one(
                {"_id": "usuario_principal"},
                {"$set": perfil},
                upsert=True
            )
            print("🧠 Memoria actualizada en MongoDB.")
        except Exception as e:
            print("❌ Error guardando perfil en DB:", e)

def construir_prompt_sistema():
    perfil_actual = cargar_perfil()
    perfil_str = json.dumps(perfil_actual, ensure_ascii=False, indent=2)
    
    return f"""
Eres Logan, un asistente de hogar con inteligencia artificial avanzado, empático, brillante y muy eficiente.
Hablas de forma fluida, cercana, natural y concisa (máximo 2 oraciones breves).

INSTRUCCIÓN DE IDENTIDAD (STRICT):
- Tu nombre es Logan. Jamás menciones que eres Llama, Groq, Meta, OpenAI, Gemini ni ningún otro motor. Tu única identidad es Logan.

PERFIL Y MEMORIA DEL USUARIO:
{perfil_str}

REGLAS DE CONTROL DOMÓTICO (ESP32):
- Encender luz: [[LUZ:ON]]
- Apagar luz: [[LUZ:OFF]]

REGLAS DE CONTROL DE LAPTOP (OBLIGATORIAS):
- PAUSAR O REANUDAR MÚSICA/MULTIMEDIA (Súper importante):
  Si el usuario dice 'pausa', 'pon pausa', 'despausa', 'continúa', 'reproduce', 'sigue la música':
  Debes responder e incluir OBLIGATORIAMENTE [[VOLUMEN: PAUSA]].
- REPRODUCIR EN SPOTIFY: [[REPRODUCIR: nombre_cancion_o_artista]]
- TEMPORIZADORES/ALARMAS: [[ALARMA: segundos | mensaje]]
- ABRIR APLICACIONES: [[EJECUTAR: nombre_app]]
- CONTROL DE VOLUMEN: [[VOLUMEN: SUBIR]], [[VOLUMEN: BAJAR]], [[VOLUMEN: MUTE]]
- SISTEMA: [[SISTEMA: BLOQUEAR]], [[SISTEMA: CAPTURA]], [[SISTEMA: APAGAR]]

REGLA DE APRENDIZAJE AUTOMÁTICO:
- Si el usuario te da datos personales o preferencias: [[RECORDAR: clave = valor]].
"""

MODELOS_GROQ = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-70b-8192"
]

def consultar_groq(api_key, user_message):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
        'User-Agent': 'Mozilla/5.0'
    }

    messages_payload = [{"role": "system", "content": construir_prompt_sistema()}]
    for msg in HISTORIAL:
        messages_payload.append(msg)
    messages_payload.append({"role": "user", "content": user_message})

    ultimo_error = ""
    for modelo in MODELOS_GROQ:
        payload = {
            "model": modelo,
            "messages": messages_payload,
            "temperature": 0.6
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers=headers
            )
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode('utf-8'))
            return res_data['choices'][0]['message']['content']

        except Exception as e:
            ultimo_error = str(e)
            continue

    raise Exception(ultimo_error)

# ==============================================================================
# RUTAS DEL SERVIDOR
# ==============================================================================

@app.route('/chat', methods=['POST'])
def chat():
    global estado_rele, HISTORIAL, cola_ordenes_pc
    
    api_key = os.environ.get("GROQ_API_KEY", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key:
        return jsonify({'reply': 'Falta configurar GROQ_API_KEY en Render.', 'estado_rele': estado_rele}), 500

    data = request.get_json() or {}
    user_message = data.get('message', '')

    if not user_message:
        return jsonify({'reply': 'No logré escucharte bien.', 'estado_rele': estado_rele}), 400

    try:
        reply_text = consultar_groq(api_key, user_message)

        # 1. CONTROL DOMÓTICO (ESP32)
        if "[[LUZ:ON]]" in reply_text.upper():
            estado_rele = "ON"
            reply_text = re.sub(r"\[\[LUZ:ON\]\]", "", reply_text, flags=re.IGNORECASE).strip()
        elif "[[LUZ:OFF]]" in reply_text.upper():
            estado_rele = "OFF"
            reply_text = re.sub(r"\[\[LUZ:OFF\]\]", "", reply_text, flags=re.IGNORECASE).strip()

        comando_tipo = None
        comando_valor = None

        # 2. EXTRACCIÓN FLEXIBLE DE COMANDOS (Insensible a mayúsculas/minúsculas)
        patron_etiquetas = r"\[\[(ALARMA|REPRODUCIR|VOLUMEN|SISTEMA|EJECUTAR):\s*(.*?)\s*\]\]"
        coincidencia = re.search(patron_etiquetas, reply_text, re.IGNORECASE)

        if coincidencia:
            comando_tipo = coincidencia.group(1).upper()
            comando_valor = coincidencia.group(2).strip()
            # Limpia la etiqueta de la respuesta hablada
            reply_text = re.sub(patron_etiquetas, "", reply_text, flags=re.IGNORECASE).strip()

        # 3. APRENDIZAJE AUTOMÁTICO
        patron_recordar = r"\[\[RECORDAR:\s*(.*?)\s*=\s*(.*?)\s*\]\]"
        coincidencias_memoria = re.findall(patron_recordar, reply_text, re.IGNORECASE)
        if coincidencias_memoria:
            perfil_actual = cargar_perfil()
            for clave, valor in coincidencias_memoria:
                clave_clean = clave.strip().lower()
                valor_clean = valor.strip()
                if clave_clean in ["nombre_usuario", "trato"]:
                    perfil_actual[clave_clean] = valor_clean
                else:
                    perfil_actual["gustos_y_datos"][clave_clean] = valor_clean
            guardar_perfil(perfil_actual)
            reply_text = re.sub(r"\[\[RECORDAR:.*?\]\]", "", reply_text, flags=re.IGNORECASE).strip()

        # 4. AÑADIR A LA COLA DE LA LAPTOP
        if comando_tipo or reply_text:
            cola_ordenes_pc.append({
                "tipo": comando_tipo,
                "valor": comando_valor,
                "hablar": reply_text
            })

        # 5. MEMORIA CONVERSACIONAL
        HISTORIAL.append({"role": "user", "content": user_message})
        HISTORIAL.append({"role": "assistant", "content": reply_text})
        if len(HISTORIAL) > MAX_HISTORIAL * 2:
            HISTORIAL = HISTORIAL[-MAX_HISTORIAL * 2:]

        return jsonify({'reply': reply_text, 'estado_rele': estado_rele})

    except Exception as e:
        print("❌ ERROR GENERAL:", str(e))
        traceback.print_exc()
        return jsonify({'reply': f"Detalle técnico: {str(e)[:150]}", 'estado_rele': estado_rele}), 500

@app.route('/esp32/status', methods=['GET'])
def esp32_status():
    return jsonify({"relay": estado_rele})

@app.route('/pc/comando', methods=['GET'])
def pc_comando():
    """Entrega los comandos en orden estricto de llegada"""
    global cola_ordenes_pc
    if cola_ordenes_pc:
        data = cola_ordenes_pc.pop(0) # Extrae la orden más antigua de la cola
    else:
        data = {}
    return jsonify(data)

@app.route('/status', methods=['GET'])
def status():
    return f"<h1>Logan Server Activo</h1><p>Relé: <b>{estado_rele}</b></p>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
