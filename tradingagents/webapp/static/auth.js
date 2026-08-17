import { initializeApp } from "https://www.gstatic.com/firebasejs/12.16.0/firebase-app.js";
import {
  GoogleAuthProvider,
  browserLocalPersistence,
  getAuth,
  getIdToken,
  onAuthStateChanged,
  setPersistence,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
} from "https://www.gstatic.com/firebasejs/12.16.0/firebase-auth.js";

let firebaseAuth = null;
let currentUser = null;
let authRequired = true;
let initialized = false;
let callbacks = {};
let dom = {};

export async function initializeAuthentication(handlers) {
  if (initialized) return;
  initialized = true;
  callbacks = handlers || {};
  cacheDom();
  bindLoginEvents();
  setAuthStatus("CONNECTING TO FIREBASE", "pending");

  let response;
  try {
    response = await fetch("/api/auth/config", {
      headers: { "Accept": "application/json" },
      credentials: "same-origin",
    });
  } catch (_error) {
    showAuthError("Cannot reach the TradingAgents authentication service.");
    setAuthStatus("AUTH SERVICE OFFLINE", "error");
    return;
  }

  if (!response.ok) {
    showAuthError("Authentication configuration could not be loaded.");
    setAuthStatus("AUTH CONFIG ERROR", "error");
    return;
  }

  const config = await response.json();
  authRequired = config.required !== false;
  if (!authRequired) {
    currentUser = { uid: "local-development", email: "AUTH DISABLED" };
    showWorkspace(currentUser);
    if (callbacks.onAuthenticated) callbacks.onAuthenticated(currentUser);
    return;
  }

  if (!config.configured || !config.firebase) {
    const missing = Array.isArray(config.missing) ? config.missing.join(", ") : "Firebase web config";
    showAuthError("Server authentication is not configured. Missing: " + missing + ".");
    setAuthStatus("SETUP REQUIRED", "error");
    return;
  }

  try {
    const app = initializeApp(config.firebase);
    firebaseAuth = getAuth(app);
    await setPersistence(firebaseAuth, browserLocalPersistence);
    enableLoginControls(true);
    onAuthStateChanged(firebaseAuth, handleAuthState);
  } catch (_error) {
    showAuthError("Firebase Authentication failed to initialize. Check the web app configuration.");
    setAuthStatus("FIREBASE INIT FAILED", "error");
  }
}

export async function getAuthToken() {
  if (!authRequired) return null;
  if (!currentUser) throw new Error("Login is required.");
  return getIdToken(currentUser);
}

export async function invalidateAuthentication(message) {
  if (!authRequired || !firebaseAuth) return;
  currentUser = null;
  try {
    await signOut(firebaseAuth);
  } finally {
    showLogin();
    showAuthError(message || "Your session ended. Please login again.");
  }
}

function cacheDom() {
  const ids = [
    "auth-shell", "app-shell", "workspace-skip-link", "auth-status-dot", "auth-status-text",
    "google-login-button", "login-form", "login-email", "login-password",
    "email-login-button", "auth-error", "auth-user-email", "logout-button",
  ];
  ids.forEach(function (id) {
    dom[toCamelCase(id)] = document.getElementById(id);
  });
}

function bindLoginEvents() {
  dom.loginForm.addEventListener("submit", loginWithEmail);
  dom.googleLoginButton.addEventListener("click", loginWithGoogle);
  dom.logoutButton.addEventListener("click", async function () {
    setButtonBusy(dom.logoutButton, true, "WAIT");
    try {
      await signOut(firebaseAuth);
    } catch (_error) {
      showAuthError("Logout failed. Please retry.");
    } finally {
      setButtonBusy(dom.logoutButton, false, "LOGOUT");
    }
  });
}

async function loginWithEmail(event) {
  event.preventDefault();
  clearAuthError();
  const email = dom.loginEmail.value.trim();
  const password = dom.loginPassword.value;
  if (!email || !password) {
    showAuthError("Enter both email and password.");
    return;
  }
  setLoginBusy(true, "AUTHENTICATING");
  try {
    await signInWithEmailAndPassword(firebaseAuth, email, password);
  } catch (error) {
    showAuthError(friendlyAuthError(error));
  } finally {
    setLoginBusy(false, "LOGIN TO TERMINAL");
  }
}

async function loginWithGoogle() {
  clearAuthError();
  setLoginBusy(true, "OPENING GOOGLE");
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });
  try {
    await signInWithPopup(firebaseAuth, provider);
  } catch (error) {
    if (error && error.code !== "auth/popup-closed-by-user") {
      showAuthError(friendlyAuthError(error));
    }
  } finally {
    setLoginBusy(false, "LOGIN TO TERMINAL");
  }
}

async function handleAuthState(user) {
  if (!user) {
    currentUser = null;
    showLogin();
    setAuthStatus("LOGIN REQUIRED", "ready");
    if (callbacks.onSignedOut) callbacks.onSignedOut();
    return;
  }

  setAuthStatus("VERIFYING SESSION", "pending");
  try {
    const token = await getIdToken(user, true);
    const response = await fetch("/api/auth/session", {
      headers: { "Accept": "application/json", "Authorization": "Bearer " + token },
      credentials: "same-origin",
    });
    if (!response.ok) {
      let detail = "This Firebase account is not allowed to access TradingAgents.";
      try {
        const payload = await response.json();
        if (payload && payload.detail) detail = String(payload.detail);
      } catch (_error) {
        // Keep the safe generic error.
      }
      await signOut(firebaseAuth);
      showAuthError(detail);
      return;
    }
    const session = await response.json();
    currentUser = user;
    const identity = session.user || { uid: user.uid, email: user.email };
    showWorkspace(identity);
    if (callbacks.onAuthenticated) callbacks.onAuthenticated(identity);
  } catch (_error) {
    currentUser = null;
    showLogin();
    showAuthError("The server could not verify this Firebase session.");
    setAuthStatus("SESSION REJECTED", "error");
  }
}

function showWorkspace(user) {
  clearAuthError();
  dom.authShell.hidden = true;
  dom.appShell.hidden = false;
  dom.workspaceSkipLink.hidden = false;
  dom.authUserEmail.textContent = user.email || user.name || user.uid || "AUTHENTICATED";
  setAuthStatus("AUTHENTICATED", "ready");
}

function showLogin() {
  dom.appShell.hidden = true;
  dom.workspaceSkipLink.hidden = true;
  dom.authShell.hidden = false;
}

function enableLoginControls(enabled) {
  dom.googleLoginButton.disabled = !enabled;
  dom.loginEmail.disabled = !enabled;
  dom.loginPassword.disabled = !enabled;
  dom.emailLoginButton.disabled = !enabled;
}

function setLoginBusy(busy, emailLabel) {
  enableLoginControls(!busy);
  dom.emailLoginButton.querySelector("span").textContent = emailLabel;
  dom.googleLoginButton.classList.toggle("is-loading", busy);
}

function setButtonBusy(button, busy, label) {
  button.disabled = busy;
  button.textContent = label;
}

function setAuthStatus(text, mode) {
  dom.authStatusText.textContent = text;
  dom.authStatusDot.dataset.mode = mode || "pending";
}

function showAuthError(message) {
  dom.authError.textContent = message;
  dom.authError.hidden = false;
}

function clearAuthError() {
  dom.authError.textContent = "";
  dom.authError.hidden = true;
}

function friendlyAuthError(error) {
  const code = error && error.code ? String(error.code) : "";
  const messages = {
    "auth/invalid-credential": "Email or password is incorrect.",
    "auth/invalid-email": "Enter a valid email address.",
    "auth/too-many-requests": "Too many login attempts. Wait a moment and retry.",
    "auth/network-request-failed": "Firebase cannot be reached. Check your connection.",
    "auth/popup-blocked": "The Google login popup was blocked by the browser.",
    "auth/unauthorized-domain": "This domain is not authorized in Firebase Authentication.",
  };
  return messages[code] || "Login failed. Verify the account and try again.";
}

function toCamelCase(value) {
  return value.replace(/-([a-z])/g, function (_match, letter) { return letter.toUpperCase(); });
}
