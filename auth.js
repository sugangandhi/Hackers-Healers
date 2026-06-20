// Simple demo auth — in production replace with real JWT/session
const _DEMO = { username: 'dr.patel', password: 'medoffice2026' };
const _DOCTOR = {
  name: 'Dr. Anika Patel',
  initials: 'AP',
  role: 'Family Physician',
  clinic: 'Ottawa Family Health Team',
  cpso: '92841',
};

function login(username, password) {
  if (username === _DEMO.username && password === _DEMO.password) {
    sessionStorage.setItem('moa_user', JSON.stringify(_DOCTOR));
    return true;
  }
  return false;
}

function getUser() {
  try { return JSON.parse(sessionStorage.getItem('moa_user')); }
  catch { return null; }
}

function requireAuth() {
  const u = getUser();
  if (!u) { window.location.replace('login.html'); return null; }
  return u;
}

function logout() {
  sessionStorage.removeItem('moa_user');
  window.location.replace('login.html');
}
