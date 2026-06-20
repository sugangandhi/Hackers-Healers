const _API = 'http://localhost:8000/api';

async function login(email, password) {
  try {
    const res = await fetch(`${_API}/auth/login`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ email, password }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    localStorage.setItem('moa_token', data.token);
    localStorage.setItem('moa_user',  JSON.stringify(data.user));
    return data.user;
  } catch {
    return null;
  }
}

async function register(email, password, name, role, clinic) {
  const res = await fetch(`${_API}/auth/register`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ email, password, name, role, clinic }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Registration failed');
  localStorage.setItem('moa_token', data.token);
  localStorage.setItem('moa_user',  JSON.stringify(data.user));
  return data.user;
}

function getUser() {
  try { return JSON.parse(localStorage.getItem('moa_user')); }
  catch { return null; }
}

function requireAuth() {
  const u = getUser();
  if (!u) { window.location.replace('login.html'); return null; }
  return u;
}

function logout() {
  localStorage.removeItem('moa_user');
  localStorage.removeItem('moa_token');
  window.location.replace('login.html');
}
