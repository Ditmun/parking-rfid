# ==============================================
# SISTEMA DE ESTACIONAMIENTO RFID
# Un solo archivo: API + Base de datos + Web
# Flask + SQLite (no necesita instalar nada extra)
# ==============================================

from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)
DB = "parking.db"


# --- Base de datos ---
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tarjetas (
            id_tarjeta TEXT PRIMARY KEY,
            saldo INTEGER DEFAULT 0,
            estado TEXT DEFAULT 'afuera',
            hora_entrada TEXT DEFAULT NULL
        )
    """)
    conn.commit()
    conn.close()


def obtener_o_crear(conn, id_tarjeta):
    row = conn.execute("SELECT * FROM tarjetas WHERE id_tarjeta = ?", (id_tarjeta,)).fetchone()
    if row is None:
        conn.execute("INSERT INTO tarjetas (id_tarjeta, saldo, estado) VALUES (?, 0, 'afuera')", (id_tarjeta,))
        conn.commit()
        row = conn.execute("SELECT * FROM tarjetas WHERE id_tarjeta = ?", (id_tarjeta,)).fetchone()
    return row


# --- ENDPOINT 1: Consultar tarjeta ---
@app.route("/tarjeta/<id_tarjeta>")
def consultar(id_tarjeta):
    conn = get_db()
    t = obtener_o_crear(conn, id_tarjeta)
    conn.close()
    return jsonify({
        "id_tarjeta": t["id_tarjeta"],
        "saldo": t["saldo"],
        "estado": t["estado"],
        "hora_entrada": t["hora_entrada"]
    })


# --- ENDPOINT 2: Modificar saldo ---
@app.route("/tarjeta/<id_tarjeta>/saldo", methods=["POST"])
def modificar_saldo(id_tarjeta):
    monto = request.json.get("monto")
    if monto is None or not isinstance(monto, int):
        return jsonify({"error": "monto debe ser un entero"}), 400

    conn = get_db()
    obtener_o_crear(conn, id_tarjeta)
    conn.execute("UPDATE tarjetas SET saldo = saldo + ? WHERE id_tarjeta = ?", (monto, id_tarjeta))
    conn.commit()
    t = conn.execute("SELECT saldo FROM tarjetas WHERE id_tarjeta = ?", (id_tarjeta,)).fetchone()
    conn.close()
    return jsonify({"id_tarjeta": id_tarjeta, "monto_agregado": monto, "saldo_nuevo": t["saldo"]})


# --- ENDPOINT 3: Validar entrada/salida (lo llama el ESP32) ---
@app.route("/tarjeta/<id_tarjeta>/validar", methods=["POST"])
def validar(id_tarjeta):
    conn = get_db()
    t = obtener_o_crear(conn, id_tarjeta)

    if t["estado"] == "afuera":
        # ENTRADA
        ahora = datetime.now().isoformat()
        conn.execute("UPDATE tarjetas SET estado = 'adentro', hora_entrada = ? WHERE id_tarjeta = ?",
                      (ahora, id_tarjeta))
        conn.commit()
        conn.close()
        return jsonify({"accion": "entrada", "resultado": "aprobado", "saldo": t["saldo"]})
    else:
        # SALIDA
        ahora = datetime.now()
        entrada = datetime.fromisoformat(t["hora_entrada"])
        segundos = int((ahora - entrada).total_seconds())
        costo = segundos * 2
        saldo_nuevo = t["saldo"] - costo
        conn.execute("UPDATE tarjetas SET estado = 'afuera', hora_entrada = NULL, saldo = ? WHERE id_tarjeta = ?",
                      (saldo_nuevo, id_tarjeta))
        conn.commit()
        conn.close()
        return jsonify({"accion": "salida", "resultado": "aprobado",
                        "segundos_estacionado": segundos, "costo": costo, "saldo_nuevo": saldo_nuevo})


# --- ENDPOINT 4: Listar todas las tarjetas ---
@app.route("/tarjetas")
def listar():
    conn = get_db()
    rows = conn.execute("SELECT * FROM tarjetas ORDER BY id_tarjeta").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# --- PAGINA WEB ---
@app.route("/")
def index():
    return """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Estacionamiento RFID</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:#0c0e14;color:#eaedf6;min-height:100vh}
.app{max-width:480px;margin:0 auto;padding:24px 16px}
h1{text-align:center;font-size:20px;margin-bottom:4px}
.sub{text-align:center;color:#8b92a8;font-size:13px;margin-bottom:28px}
.card{background:#13161f;border:1px solid #242938;border-radius:10px;padding:20px;margin-bottom:14px}
.card-title{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:#5a6178;margin-bottom:12px}
.row{display:flex;gap:8px}
input{flex:1;background:#1a1e2a;border:1px solid #242938;border-radius:8px;padding:9px 12px;font-size:14px;color:#eaedf6;outline:none}
input:focus{border-color:#4f6ef7}
button{font-size:13px;font-weight:600;padding:9px 16px;border:none;border-radius:8px;cursor:pointer;color:#fff;background:#4f6ef7}
button:hover{background:#6b85ff}
.btn-green{background:#34d399;color:#0c0e14}
.btn-green:hover{background:#4ade80}
#info{display:none;margin-top:14px;padding:14px;background:#1a1e2a;border-radius:8px;font-size:14px;line-height:1.8}
.badge{display:inline-block;font-size:12px;font-weight:600;padding:2px 10px;border-radius:99px}
.badge-adentro{background:rgba(251,191,36,.15);color:#fbbf24}
.badge-afuera{background:rgba(52,211,153,.15);color:#34d399}
.pos{color:#34d399}.neg{color:#f87171}
.saldo-row{margin-top:12px;padding-top:12px;border-top:1px solid #242938}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:10px}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#5a6178;padding:6px 10px;border-bottom:1px solid #242938}
td{padding:8px 10px;border-bottom:1px solid #242938;color:#8b92a8}
tr:hover td{background:#181c27}
.mono{font-family:monospace;color:#eaedf6}
.empty{text-align:center;padding:16px;color:#5a6178}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%) translateY(60px);background:#13161f;border:1px solid #242938;border-radius:8px;padding:10px 18px;font-size:13px;opacity:0;transition:all .3s;z-index:99}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.toast.ok{border-color:#34d399}.toast.err{border-color:#f87171}
</style>
</head>
<body>
<div class="app">
  <h1>🅿️ Estacionamiento RFID</h1>
  <p class="sub">Panel de control — ESP32</p>

  <div class="card">
    <div class="card-title">Consultar Tarjeta</div>
    <div class="row">
      <input type="text" id="tid" placeholder="ID tarjeta (ej: A1B2C3D4)">
      <button onclick="consultar()">Consultar</button>
    </div>
    <div id="info"></div>
    <div class="saldo-row" id="saldo-row" style="display:none">
      <div class="card-title">Modificar Saldo</div>
      <div class="row">
        <input type="number" id="monto" placeholder="Monto (ej: 5000)">
        <button class="btn-green" onclick="agregarSaldo()">Agregar</button>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-title">Tarjetas Registradas</div>
    <button onclick="listar()" style="font-size:12px;padding:6px 14px">Actualizar</button>
    <table><thead><tr><th>ID</th><th>Saldo</th><th>Estado</th></tr></thead>
    <tbody id="tbody"><tr><td colspan="3" class="empty">Sin datos</td></tr></tbody></table>
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
async function consultar(){
  const id=document.getElementById('tid').value.trim();
  if(!id)return msg('Ingresa un ID','err');
  try{
    const r=await fetch('/tarjeta/'+id);
    const d=await r.json();
    const info=document.getElementById('info');
    const cls=d.saldo>=0?'pos':'neg';
    const bcls=d.estado==='adentro'?'badge-adentro':'badge-afuera';
    let h='<b>Saldo:</b> <span class="'+cls+'">$'+d.saldo.toLocaleString()+'</span><br>';
    h+='<b>Estado:</b> <span class="badge '+bcls+'">'+d.estado+'</span><br>';
    if(d.hora_entrada) h+='<b>Entrada:</b> '+new Date(d.hora_entrada).toLocaleString('es-CL');
    info.innerHTML=h;
    info.style.display='block';
    document.getElementById('saldo-row').style.display='block';
    msg('Tarjeta encontrada','ok');
  }catch(e){msg('Error de conexión','err');}
}

async function agregarSaldo(){
  const id=document.getElementById('tid').value.trim();
  const m=parseInt(document.getElementById('monto').value);
  if(!id)return msg('Primero consulta una tarjeta','err');
  if(isNaN(m))return msg('Ingresa un monto válido','err');
  try{
    const r=await fetch('/tarjeta/'+id+'/saldo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({monto:m})});
    const d=await r.json();
    if(r.ok){msg((m>=0?'+':'')+m+' aplicado. Nuevo saldo: $'+d.saldo_nuevo.toLocaleString(),'ok');document.getElementById('monto').value='';consultar();}
    else msg(d.error,'err');
  }catch(e){msg('Error de conexión','err');}
}

async function listar(){
  try{
    const r=await fetch('/tarjetas');
    const d=await r.json();
    const tb=document.getElementById('tbody');
    if(!d.length){tb.innerHTML='<tr><td colspan="3" class="empty">No hay tarjetas</td></tr>';return;}
    tb.innerHTML=d.map(t=>{
      const cls=t.saldo>=0?'pos':'neg';
      const bcls=t.estado==='adentro'?'badge-adentro':'badge-afuera';
      return '<tr style="cursor:pointer" onclick="document.getElementById(\\'tid\\').value=\\''+t.id_tarjeta+'\\';consultar()"><td class="mono">'+t.id_tarjeta+'</td><td class="'+cls+'" style="font-weight:600">$'+t.saldo.toLocaleString()+'</td><td><span class="badge '+bcls+'">'+t.estado+'</span></td></tr>';
    }).join('');
  }catch(e){msg('Error','err');}
}

function msg(t,c){const e=document.getElementById('toast');e.textContent=t;e.className='toast '+c;requestAnimationFrame(()=>e.classList.add('show'));clearTimeout(e._t);e._t=setTimeout(()=>e.classList.remove('show'),2500);}

document.getElementById('tid').addEventListener('keydown',e=>{if(e.key==='Enter')consultar()});
document.getElementById('monto').addEventListener('keydown',e=>{if(e.key==='Enter')agregarSaldo()});
listar();
</script>
</body>
</html>"""


# --- Iniciar ---
init_db()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
