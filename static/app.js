// ===============================
// BIOENTRY REALTIME FRONTEND
// ===============================

const state = {
  okCount:    0,
  denyCount:  0,
  recentList: [],
  lastPerson: null,
  adminAuth:  false
};

const THRESHOLD = 60;

// ===============================
// RELOJ
// ===============================

function updateClock() {
  const now    = new Date();
  const days   = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  const months = ['January','February','March','April','May','June',
                  'July','August','September','October','November','December'];

  let h    = now.getHours();
  const ap = h >= 12 ? 'PM' : 'AM';

  h        = h % 12 || 12;

  const mm = String(now.getMinutes()).padStart(2,'0');
  const ss = String(now.getSeconds()).padStart(2,'0');

  document.getElementById('cam-clock').innerHTML =
    `${days[now.getDay()]}, ${months[now.getMonth()]} ${now.getDate()}, ${now.getFullYear()}<br>${h}:${mm}:${ss} ${ap}`;
}

updateClock();
setInterval(updateClock, 1000);

function nowTime() {
  const now = new Date();
  let h     = now.getHours();
  const ap  = h >= 12 ? 'PM' : 'AM';
  h         = h % 12 || 12;
  return `${h}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')} ${ap}`;
}

// ===============================
// ACCURACY BAR
// ===============================

function setAccuracy(pct, approved) {
  const val  = document.getElementById('acc-val');
  const fill = document.getElementById('acc-fill');

  val.textContent = pct + '%';
  val.className   = 'acc-value ' + (approved ? 'ok' : 'deny');

  fill.style.width      = pct + '%';
  fill.style.background = approved
    ? 'linear-gradient(90deg, #1a7a4a, #27ae60)'
    : 'linear-gradient(90deg, #922b21, #c0392b)';
}

// ===============================
// RESET PANEL
// ===============================

function resetPanel() {
  document.getElementById('p-name').textContent    = 'Esperando identificación...';
  document.getElementById('p-role').textContent    = '—';
  document.getElementById('p-code').textContent    = '—';
  document.getElementById('p-program').textContent = '—';
  document.getElementById('avatar').textContent    = '--';
  document.getElementById('a-time').textContent    = '--:--:-- --';

  const st      = document.getElementById('a-status');
  st.textContent = 'En espera';
  st.className   = 'status-tag waiting';

  const accVal  = document.getElementById('acc-val');
  const accFill = document.getElementById('acc-fill');
  accVal.textContent    = '--%';
  accVal.className      = 'acc-value waiting';
  accFill.style.width   = '0%';
  accFill.style.background = '#555';

  document.getElementById('bb-overlay').classList.add('hidden');
  document.getElementById('no-face-msg').classList.remove('hidden');

  state.lastPerson = null;
}

// ===============================
// FLASH
// ===============================

function showFlash(approved) {
  const flash = document.getElementById('flash');
  const label = document.getElementById('flash-label');

  flash.className  = 'status-flash ' + (approved ? 'ok-flash' : 'deny-flash');
  label.textContent = approved ? '✓ APROBADO' : '✕ DENEGADO';

  flash.classList.add('show');
  setTimeout(() => flash.classList.remove('show'), 1400);
}

// ===============================
// RECIENTES
// ===============================

function renderRecent(list) {
  if (!list || list.length === 0) {
    document.getElementById('recent-list').innerHTML =
      '<div style="font-size:11.5px;color:#bbb;padding:6px 0;font-style:italic;">Sin registros aún...</div>';
    return;
  }

  document.getElementById('recent-list').innerHTML = list.map(r => {
    const initials = r.nombre.split(' ').map(n => n[0]).join('').substring(0,2).toUpperCase();
    const approved = r.resultado === 'aprobado';
    const pct      = Math.round(r.confianza);
    const ts       = new Date(r.timestamp);
    let h          = ts.getHours();
    const ap       = h >= 12 ? 'PM' : 'AM';
    h              = h % 12 || 12;
    const hms      = `${h}:${String(ts.getMinutes()).padStart(2,'0')} ${ap}`;

    return `
      <div class="recent-item">
        <div class="ri-left">
          <div class="ri-avatar">${initials}</div>
          <div>
            <div class="ri-name">${r.nombre}</div>
            <div class="ri-role">${pct}% · ${hms}</div>
          </div>
        </div>
        <span class="ri-badge ${approved ? 'ok' : 'deny'}">
          ${approved ? 'Aprobado' : 'Denegado'}
        </span>
      </div>
    `;
  }).join('');
}

// ===============================
// POLL METRICS
// ===============================

let lastHistorySignature = '';

async function pollMetrics() {
  try {
    const res  = await fetch('/metrics');
    const data = await res.json();

    document.getElementById('stat-registered').textContent = data.registered;
    document.getElementById('stat-ok').textContent         = data.total_ok;
    document.getElementById('stat-deny').textContent       = data.total_deny;

    const signature = data.history.map(r => r.timestamp + r.nombre).join('|');
    if (signature !== lastHistorySignature) {
      lastHistorySignature = signature;
      renderRecent(data.history);
    }
  } catch(e) {
    console.error('metrics:', e);
  }
}

// ===============================
// POLL FACE DATA
// ===============================

async function pollRecognition() {
  try {
    const response = await fetch('/face_data');
    const data     = await response.json();

    if (!data.detected) {
      resetPanel();
      return;
    }

    document.getElementById('no-face-msg').classList.add('hidden');

    const person = {
      name:     data.name,
      initials: data.name.split(' ').map(n => n[0]).join('').substring(0,2),
      role:     data.rol,
      code:     data.codigo,
      program:  data.programa
    };

    const pct      = parseInt(data.confidence);
    const approved = data.approved;

    document.getElementById('avatar').textContent    = person.initials;
    document.getElementById('p-name').textContent    = person.name;
    document.getElementById('p-role').textContent    = 'Rol: '    + person.role;
    document.getElementById('p-code').textContent    = 'Código: ' + person.code;
    document.getElementById('p-program').textContent = person.program;
    document.getElementById('a-time').textContent    = nowTime();

    const st      = document.getElementById('a-status');
    st.textContent = approved ? 'Aprobado' : 'Denegado';
    st.className   = 'status-tag ' + (approved ? 'ok' : 'deny');

    setAccuracy(pct, approved);

    document.getElementById('bb-overlay').classList.add('hidden');

    if (state.lastPerson !== person.name) {
      showFlash(approved);
      state.lastPerson = person.name;
    }
  } catch(e) {
    console.error(e);
  }
}

// ===============================
// AGREGAR USUARIO — HELPERS
// (definidos aquí para que estén
//  disponibles en todo el archivo)
// ===============================

const elAgregarConfirm  = document.getElementById('agregar-confirm');
const elFooterNormal    = document.getElementById('footer-agregar-normal');
const elFooterConfirm   = document.getElementById('footer-agregar-confirm');
const elConfirmCancelar = document.getElementById('confirm-cancelar');
const elConfirmAceptar  = document.getElementById('confirm-aceptar');
const elConfirmBtnText  = document.getElementById('confirm-btn-text');
const elConfirmSpinner  = document.getElementById('confirm-spinner');

function volverAEditar() {
  document.getElementById('photo-drop').classList.remove('hidden');
  document.querySelector('.fields-grid').classList.remove('hidden');

  elAgregarConfirm.classList.add('hidden');
  elFooterNormal.classList.remove('hidden');
  elFooterConfirm.classList.add('hidden');
}

// ===============================
// ADMIN PANEL — MODALES
// ===============================

const elBtnAdmin      = document.getElementById('btn-admin');
const elModalLogin    = document.getElementById('modal-login');
const elLoginPassword = document.getElementById('login-password');
const elLoginError    = document.getElementById('login-error');
const elLoginSubmit   = document.getElementById('login-submit');
const elLoginCancel   = document.getElementById('login-cancel');
const elLoginClose    = document.getElementById('login-close');
const elModalAdmin    = document.getElementById('modal-admin');
const elAdminClose    = document.getElementById('admin-close');

function openLoginModal() {
  elLoginPassword.value = '';
  elLoginError.classList.add('hidden');
  elModalLogin.classList.remove('hidden');
  elLoginPassword.focus();
}

function closeLoginModal() {
  elModalLogin.classList.add('hidden');
}

function openAdminModal() {
  elModalAdmin.classList.remove('hidden');
  switchAdminTab('agregar');
  volverAEditar();
}

function closeAdminModal() {
  elModalAdmin.classList.add('hidden');
}

elBtnAdmin.addEventListener('click', () => {
  if (state.adminAuth) {
    openAdminModal();
  } else {
    openLoginModal();
  }
});

elLoginCancel.addEventListener('click', closeLoginModal);
elLoginClose.addEventListener('click', closeLoginModal);

elModalLogin.addEventListener('click', (e) => {
  if (e.target === elModalLogin) closeLoginModal();
});

async function doLogin() {
  const password = elLoginPassword.value;
  try {
    const res  = await fetch('/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password })
    });
    const data = await res.json();

    if (data.ok) {
      state.adminAuth = true;
      closeLoginModal();
      openAdminModal();
    } else {
      elLoginError.textContent = data.error || 'Contraseña incorrecta';
      elLoginError.classList.remove('hidden');
    }
  } catch(e) {
    elLoginError.textContent = 'Error de conexión';
    elLoginError.classList.remove('hidden');
  }
}

elLoginSubmit.addEventListener('click', doLogin);
elLoginPassword.addEventListener('keydown', (e) => { if (e.key === 'Enter') doLogin(); });

elAdminClose.addEventListener('click', closeAdminModal);
elModalAdmin.addEventListener('click', (e) => { if (e.target === elModalAdmin) closeAdminModal(); });

// ===============================
// TABS
// ===============================

const tabButtons = document.querySelectorAll('.admin-tab');

function switchAdminTab(tab) {
  tabButtons.forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tab);
  });

  document.getElementById('tab-agregar').classList.toggle('hidden', tab !== 'agregar');
  document.getElementById('tab-lista').classList.toggle('hidden',   tab !== 'lista');

  if (tab === 'lista')   loadUserList();
  if (tab === 'agregar') volverAEditar();
}

tabButtons.forEach(btn => {
  btn.addEventListener('click', () => switchAdminTab(btn.dataset.tab));
});

// ===============================
// FOTO UPLOAD
// ===============================

const elPhotoDrop        = document.getElementById('photo-drop');
const elFotoInput        = document.getElementById('foto-input');
const elPhotoPreview     = document.getElementById('photo-preview');
const elPreviewImg       = document.getElementById('preview-img');
const elPhotoPlaceholder = document.getElementById('photo-placeholder');

let selectedFoto = null;

elPhotoDrop.addEventListener('click', () => elFotoInput.click());

elFotoInput.addEventListener('change', (e) => {
  if (e.target.files && e.target.files[0]) setFoto(e.target.files[0]);
});

elPhotoDrop.addEventListener('dragover', (e) => {
  e.preventDefault();
  elPhotoDrop.classList.add('drag-over');
});

elPhotoDrop.addEventListener('dragleave', () => {
  elPhotoDrop.classList.remove('drag-over');
});

elPhotoDrop.addEventListener('drop', (e) => {
  e.preventDefault();
  elPhotoDrop.classList.remove('drag-over');
  if (e.dataTransfer.files && e.dataTransfer.files[0]) setFoto(e.dataTransfer.files[0]);
});

function setFoto(file) {
  selectedFoto = file;
  const reader = new FileReader();
  reader.onload = (e) => {
    elPreviewImg.src = e.target.result;
    elPhotoPreview.classList.remove('hidden');
    elPhotoPlaceholder.classList.add('hidden');
  };
  reader.readAsDataURL(file);
}

function resetFoto() {
  selectedFoto     = null;
  elFotoInput.value = '';
  elPreviewImg.src  = '';
  elPhotoPreview.classList.add('hidden');
  elPhotoPlaceholder.classList.remove('hidden');
}

// ===============================
// AGREGAR USUARIO
// ===============================

const elFNombre       = document.getElementById('f-nombre');
const elFCodigo       = document.getElementById('f-codigo');
const elFRol          = document.getElementById('f-rol');
const elFPrograma     = document.getElementById('f-programa');
const elAgregarError  = document.getElementById('agregar-error');
const elAgregarOk     = document.getElementById('agregar-ok');
const elAgregarSubmit = document.getElementById('agregar-submit');
const elAgregarReset  = document.getElementById('agregar-reset');

function resetAgregarForm() {
  elFNombre.value   = '';
  elFCodigo.value   = '';
  elFRol.value      = '';
  elFPrograma.value = '';
  resetFoto();
  elAgregarError.classList.add('hidden');
  elAgregarOk.classList.add('hidden');
  volverAEditar();
}

elAgregarReset.addEventListener('click', resetAgregarForm);

function mostrarConfirmacion() {
  const nombre   = elFNombre.value.trim();
  const codigo   = elFCodigo.value.trim();
  const rol      = elFRol.value.trim();
  const programa = elFPrograma.value.trim();

  elAgregarError.classList.add('hidden');
  elAgregarOk.classList.add('hidden');

  if (!nombre || !codigo || !rol || !programa || !selectedFoto) {
    elAgregarError.textContent = 'Completa todos los campos y selecciona una foto.';
    elAgregarError.classList.remove('hidden');
    return;
  }

  document.getElementById('confirm-nombre').textContent   = nombre;
  document.getElementById('confirm-codigo').textContent   = codigo;
  document.getElementById('confirm-rol').textContent      = rol;
  document.getElementById('confirm-programa').textContent = programa;

  // Ocultar formulario — mostrar solo resumen
  document.getElementById('photo-drop').classList.add('hidden');
  document.querySelector('.fields-grid').classList.add('hidden');

  elAgregarConfirm.classList.remove('hidden');
  elFooterNormal.classList.add('hidden');
  elFooterConfirm.classList.remove('hidden');
}

async function confirmarYGuardar() {
  const nombre   = elFNombre.value.trim();
  const codigo   = elFCodigo.value.trim();
  const rol      = elFRol.value.trim();
  const programa = elFPrograma.value.trim();

  const formData = new FormData();
  formData.append('nombre',   nombre);
  formData.append('codigo',   codigo);
  formData.append('rol',      rol);
  formData.append('programa', programa);
  formData.append('foto',     selectedFoto);

  elConfirmBtnText.classList.add('hidden');
  elConfirmSpinner.classList.remove('hidden');
  elConfirmAceptar.disabled = true;

  try {
    const res  = await fetch('/admin/agregar', { method: 'POST', body: formData });
    const data = await res.json();

    volverAEditar();

    if (data.ok) {
      elAgregarOk.classList.remove('hidden');
      resetAgregarForm();
    } else {
      elAgregarError.textContent = data.error || 'No se pudo agregar el usuario.';
      elAgregarError.classList.remove('hidden');
    }
  } catch(e) {
    volverAEditar();
    elAgregarError.textContent = 'Error de conexión.';
    elAgregarError.classList.remove('hidden');
  } finally {
    elConfirmBtnText.classList.remove('hidden');
    elConfirmSpinner.classList.add('hidden');
    elConfirmAceptar.disabled = false;
  }
}

elAgregarSubmit.addEventListener('click', mostrarConfirmacion);
elConfirmCancelar.addEventListener('click', volverAEditar);
elConfirmAceptar.addEventListener('click', confirmarYGuardar);

// ===============================
// LISTA DE USUARIOS
// ===============================

const elUserList = document.getElementById('user-list');

async function loadUserList() {
  elUserList.innerHTML = '<div class="list-loading">Cargando...</div>';

  try {
    const res   = await fetch('/admin/usuarios');
    const users = await res.json();

    if (!users.length) {
      elUserList.innerHTML = '<div class="list-loading">No hay usuarios registrados.</div>';
      return;
    }

    elUserList.innerHTML = users.map(u => {
      const initials = u.nombre.split(' ').map(n => n[0]).join('').substring(0,2).toUpperCase();
      return `
        <div class="user-item">
          <div class="user-item-info">
            <div class="user-item-avatar">${initials}</div>
            <div>
              <div class="user-item-name">${u.nombre}</div>
              <div class="user-item-meta">${u.rol} · ${u.programa} · Código: ${u.codigo}</div>
            </div>
          </div>
          <button class="btn-delete" data-id="${u.id}">Eliminar</button>
        </div>
      `;
    }).join('');

    elUserList.querySelectorAll('.btn-delete').forEach(btn => {
      btn.addEventListener('click', () => deleteUser(btn.dataset.id));
    });
  } catch(e) {
    elUserList.innerHTML = '<div class="list-loading">Error al cargar usuarios.</div>';
  }
}

async function deleteUser(id) {
  if (!confirm('¿Eliminar este usuario? Esta acción no se puede deshacer.')) return;

  try {
    const res  = await fetch(`/admin/eliminar/${id}`, { method: 'DELETE' });
    const data = await res.json();

    if (data.ok) {
      loadUserList();
    } else {
      alert(data.error || 'No se pudo eliminar el usuario.');
    }
  } catch(e) {
    alert('Error de conexión.');
  }
}

// ===============================
// LOOP PRINCIPAL
// ===============================

resetPanel();

setInterval(pollRecognition, 1000);
setInterval(pollMetrics,     3000);