// ============================================================
// SISTEMA DE ESTACIONAMIENTO RFID - Servidor Express
// Proyecto universitario: ESP32 + Lector RFID + API REST
// ============================================================

const express = require('express');
const { Pool } = require('pg');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// --- Middleware ---
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// --- Conexión a PostgreSQL ---
// En Render, la variable DATABASE_URL se configura automáticamente
// al vincular un servicio de PostgreSQL.
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.DATABASE_URL
    ? { rejectUnauthorized: false } // Necesario para Render
    : false,                        // Sin SSL en desarrollo local
});

// --- Crear la tabla si no existe ---
async function inicializarDB() {
  const query = `
    CREATE TABLE IF NOT EXISTS tarjetas (
      id_tarjeta TEXT PRIMARY KEY,
      saldo INTEGER DEFAULT 0,
      estado TEXT DEFAULT 'afuera' CHECK (estado IN ('adentro', 'afuera')),
      hora_entrada TIMESTAMPTZ DEFAULT NULL
    );
  `;
  try {
    await pool.query(query);
    console.log('✅ Tabla "tarjetas" lista');
  } catch (err) {
    console.error('❌ Error al crear tabla:', err.message);
  }
}

// --- Función auxiliar: obtener o crear tarjeta ---
async function obtenerOCrearTarjeta(idTarjeta) {
  // Intentar obtener la tarjeta
  let result = await pool.query(
    'SELECT * FROM tarjetas WHERE id_tarjeta = $1',
    [idTarjeta]
  );

  // Si no existe, crearla con saldo 0 y estado "afuera"
  if (result.rows.length === 0) {
    result = await pool.query(
      `INSERT INTO tarjetas (id_tarjeta, saldo, estado, hora_entrada)
       VALUES ($1, 0, 'afuera', NULL)
       RETURNING *`,
      [idTarjeta]
    );
  }

  return result.rows[0];
}

// ============================================================
// ENDPOINT 1: GET /tarjeta/:id
// Devuelve info de la tarjeta. Si no existe, la crea.
// ============================================================
app.get('/tarjeta/:id', async (req, res) => {
  try {
    const tarjeta = await obtenerOCrearTarjeta(req.params.id);

    res.json({
      id_tarjeta: tarjeta.id_tarjeta,
      saldo: tarjeta.saldo,
      estado: tarjeta.estado,
      hora_entrada: tarjeta.hora_entrada,
    });
  } catch (err) {
    console.error('Error en GET /tarjeta/:id:', err.message);
    res.status(500).json({ error: 'Error interno del servidor' });
  }
});

// ============================================================
// ENDPOINT 2: POST /tarjeta/:id/saldo
// Agrega o quita saldo. Body: { "monto": 1000 }
// ============================================================
app.post('/tarjeta/:id/saldo', async (req, res) => {
  try {
    const { monto } = req.body;

    // Validar que el monto sea un número entero
    if (monto === undefined || !Number.isInteger(monto)) {
      return res.status(400).json({
        error: 'El campo "monto" es obligatorio y debe ser un número entero',
      });
    }

    // Asegurar que la tarjeta existe
    await obtenerOCrearTarjeta(req.params.id);

    // Actualizar el saldo
    const result = await pool.query(
      `UPDATE tarjetas
       SET saldo = saldo + $1
       WHERE id_tarjeta = $2
       RETURNING saldo`,
      [monto, req.params.id]
    );

    res.json({
      id_tarjeta: req.params.id,
      monto_agregado: monto,
      saldo_nuevo: result.rows[0].saldo,
    });
  } catch (err) {
    console.error('Error en POST /tarjeta/:id/saldo:', err.message);
    res.status(500).json({ error: 'Error interno del servidor' });
  }
});

// ============================================================
// ENDPOINT 3: POST /tarjeta/:id/validar
// Lógica de entrada/salida del estacionamiento.
// El ESP32 llama este endpoint cada vez que se pasa una tarjeta.
// ============================================================
app.post('/tarjeta/:id/validar', async (req, res) => {
  try {
    const tarjeta = await obtenerOCrearTarjeta(req.params.id);

    if (tarjeta.estado === 'afuera') {
      // ---- ENTRADA ----
      const ahora = new Date();

      await pool.query(
        `UPDATE tarjetas
         SET estado = 'adentro', hora_entrada = $1
         WHERE id_tarjeta = $2`,
        [ahora.toISOString(), req.params.id]
      );

      res.json({
        accion: 'entrada',
        resultado: 'aprobado',
        saldo: tarjeta.saldo,
      });

    } else {
      // ---- SALIDA ----
      const ahora = new Date();
      const horaEntrada = new Date(tarjeta.hora_entrada);

      // Calcular segundos transcurridos
      const segundos = Math.floor((ahora - horaEntrada) / 1000);

      // Costo = 2 pesos por segundo
      const costo = segundos * 2;

      // Nuevo saldo (puede quedar negativo)
      const saldoNuevo = tarjeta.saldo - costo;

      await pool.query(
        `UPDATE tarjetas
         SET estado = 'afuera', hora_entrada = NULL, saldo = $1
         WHERE id_tarjeta = $2`,
        [saldoNuevo, req.params.id]
      );

      res.json({
        accion: 'salida',
        resultado: 'aprobado',
        segundos_estacionado: segundos,
        costo: costo,
        saldo_nuevo: saldoNuevo,
      });
    }
  } catch (err) {
    console.error('Error en POST /tarjeta/:id/validar:', err.message);
    res.status(500).json({ error: 'Error interno del servidor' });
  }
});

// ============================================================
// ENDPOINT 4: POST /tarjeta/:id/estado (DEBUG)
// Cambia el estado manualmente. Body: { "estado": "afuera" }
// ============================================================
app.post('/tarjeta/:id/estado', async (req, res) => {
  try {
    const { estado } = req.body;

    if (estado !== 'adentro' && estado !== 'afuera') {
      return res.status(400).json({
        error: 'El campo "estado" debe ser "adentro" o "afuera"',
      });
    }

    await obtenerOCrearTarjeta(req.params.id);

    const horaEntrada = estado === 'adentro' ? new Date().toISOString() : null;

    await pool.query(
      `UPDATE tarjetas
       SET estado = $1, hora_entrada = $2
       WHERE id_tarjeta = $3`,
      [estado, horaEntrada, req.params.id]
    );

    res.json({
      id_tarjeta: req.params.id,
      estado: estado,
      hora_entrada: horaEntrada,
    });
  } catch (err) {
    console.error('Error en POST /tarjeta/:id/estado:', err.message);
    res.status(500).json({ error: 'Error interno del servidor' });
  }
});

// ============================================================
// ENDPOINT 5: GET /tarjetas (extra, útil para la demo)
// Lista todas las tarjetas registradas
// ============================================================
app.get('/tarjetas', async (req, res) => {
  try {
    const result = await pool.query(
      'SELECT * FROM tarjetas ORDER BY id_tarjeta'
    );
    res.json(result.rows);
  } catch (err) {
    console.error('Error en GET /tarjetas:', err.message);
    res.status(500).json({ error: 'Error interno del servidor' });
  }
});

// --- Iniciar servidor ---
inicializarDB().then(() => {
  app.listen(PORT, () => {
    console.log(`🚗 Servidor de estacionamiento corriendo en puerto ${PORT}`);
    console.log(`🌐 Interfaz web: http://localhost:${PORT}`);
  });
});
