// ══════════════════════════════════════════════════════
// PARCHE — pegar este bloque al final de index.html
// antes del </body>, reemplazando el bloque existente
// de selCruceTurno y el DOMContentLoaded del cruce.
//
// Corrección 3: turno del día pre-seleccionado en Cruce
// Corrección 2b: mostrar columna "Despachado" en tabla
// ══════════════════════════════════════════════════════

// Días de la semana → turno que le corresponde
// Lunes=1 → LxM (lo que salió el lunes fue faenado DxL)
const TURNO_POR_DIA = {
  0: 'SxD',  // Domingo
  1: 'DxL',  // Lunes
  2: 'LxM',  // Martes
  3: 'MxM',  // Miércoles
  4: 'MxJ',  // Jueves
  5: 'JxV',  // Viernes
  6: 'VxS',  // Sábado
};

// Sobreescribir selCruceTurno para que también actualice
// el estado visual de los botones correctamente
function selCruceTurno(t, btn) {
  cruceTurnoActivo = t;
  document.querySelectorAll('#cruceTurnosBtns .turno-btn').forEach(b => {
    b.classList.remove('selected');
  });
  btn.classList.add('selected');
}

// Ejecutar después de que el DOM del cruce esté listo
document.addEventListener('DOMContentLoaded', function () {

  // Esperar a que el módulo Cruce inyecte su HTML (usa prepend)
  setTimeout(function () {
    const turnoHoy = TURNO_POR_DIA[new Date().getDay()];

    // Marcar sugerido en los botones del módulo Despachos
    document.querySelectorAll('.turno-btn').forEach(b => {
      if (b.dataset.turno === turnoHoy) b.classList.add('sugerido');
    });

    // Pre-seleccionar el turno del día en Cruce Diario
    const btnCruceHoy = document.querySelector(
      `#cruceTurnosBtns .turno-btn[data-t="${turnoHoy}"]`
    );
    if (btnCruceHoy) {
      // Desmarcar "Todos"
      document.querySelectorAll('#cruceTurnosBtns .turno-btn').forEach(b => {
        b.classList.remove('selected');
        b.style.borderColor = '';
        b.style.background  = '';
        b.style.color       = '';
      });
      btnCruceHoy.classList.add('selected');
      cruceTurnoActivo = turnoHoy;
    }
  }, 300); // 300ms es suficiente para que el prepend termine

});

// ── Sobreescribir renderCruceTabla para agregar columna
//    "Despachado hoy" usando el campo ya_despachado ──────
function renderCruceTabla(datos) {
  const tbody = document.getElementById('cruceTbody');
  if (!datos.length) {
    tbody.innerHTML = '<tr><td colspan="11" class="empty-state">Sin datos para este cruce.</td></tr>';
    return;
  }

  // Actualizar encabezado para incluir la columna Despachado
  const thead = tbody.closest('table').querySelector('thead tr');
  if (thead && thead.cells.length < 11) {
    const th = document.createElement('th');
    th.className = 'num';
    th.textContent = 'Despachado';
    thead.insertBefore(th, thead.cells[thead.cells.length - 1]);
  }

  const ESTADO_BADGE = {
    'OK':         '<span style="background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:20px;font-size:0.75rem;font-weight:700;">✅ OK</span>',
    'DECOMISO':   '<span style="background:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:20px;font-size:0.75rem;font-weight:700;">🏷️ DECOMISO</span>',
    'CRUDA':      '<span style="background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:20px;font-size:0.75rem;font-weight:700;">🟡 CRUDA</span>',
    'INCOMPLETO': '<span style="background:#f3f4f6;color:#374151;padding:2px 8px;border-radius:20px;font-size:0.75rem;font-weight:700;">⚠️ INCOMPLETO</span>',
  };
  const FILA_BG = {
    'DECOMISO':   'background:#fff5f5;border-left:3px solid #dc2626;',
    'CRUDA':      'background:#fffbeb;border-left:3px solid #f59e0b;',
    'INCOMPLETO': 'background:#fafafa;border-left:3px solid #9ca3af;',
    'OK':         '',
  };

  tbody.innerHTML = datos.map(j => {
    const bg    = FILA_BG[j.estado] || '';
    const badge = ESTADO_BADGE[j.estado] || j.estado;
    const decom = j.decomisos && j.decomisos.length
      ? j.decomisos.map(d => `<span style="font-size:0.75rem;color:#991b1b;">${d.producto||''}: ${d.causa||'—'}</span>`).join('<br>')
      : '—';
    const obs = (j.observaciones || '').split('\n').filter(Boolean).join(' · ').substring(0, 60);

    // Columna Despachado — verde si ya salió hoy
    const desp = j.ya_despachado
      ? `<span style="background:#d1fae5;color:#065f46;padding:2px 7px;border-radius:20px;font-size:0.72rem;font-weight:700;" title="${j.destino_salida||''}">✓ Hoy</span>`
      : '—';

    return `<tr style="${bg}"
              data-estado="${j.estado.toLowerCase()}"
              data-txt="${(j.codigo_base + (j.destino||'')).toLowerCase()}">
      <td style="font-family:monospace;font-weight:700;font-size:0.85rem;">${j.codigo_base}</td>
      <td class="num">${badge}</td>
      <td style="font-size:0.78rem;max-width:190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
          title="${j.destino||''}">${j.destino || '—'}</td>
      <td class="num" style="color:#dc2626;font-weight:700;">${j.tiene_vr  ? '✓' : '—'}</td>
      <td class="num" style="color:#2563eb;font-weight:700;">${j.tiene_vb  ? '✓' : '—'}</td>
      <td class="num">${j.tiene_cabeza ? '✓' : '—'}</td>
      <td class="num">${j.tiene_pm    ? '✓' : '—'}</td>
      <td class="num" style="font-size:0.8rem;">${j.horas_en_cava}h</td>
      <td class="num">${desp}</td>
      <td style="font-size:0.78rem;">${decom}</td>
      <td style="font-size:0.75rem;color:var(--gris);">${obs}</td>
    </tr>`;
  }).join('');
}
