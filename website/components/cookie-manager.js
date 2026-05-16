export class CookieManager {
  constructor(apiBase = "") {
    this.apiBase = apiBase;
    this.userTokenCookie = "deltaplant_public_id";
    this.consentCookie = "deltaplant_consent";
  }

  getCookie(name) {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : null;
  }

  setCookie(name, value, maxAgeSeconds = 31536000) {
    const secure = window.location.protocol === "https:" ? "; Secure" : "";
    document.cookie = `${name}=${encodeURIComponent(value)}; Max-Age=${maxAgeSeconds}; Path=/; SameSite=Strict${secure}`;
  }

  getOrCreateUserToken() {
    const existing = this.getCookie(this.userTokenCookie) || window.localStorage.getItem(this.userTokenCookie);
    if (existing) {
      this.setCookie(this.userTokenCookie, existing);
      return existing;
    }
    const token = `dp_${(window.crypto?.randomUUID?.() || `${Date.now()}_${Math.random().toString(36).slice(2, 12)}`).replace(/-/g, "")}`;
    this.setCookie(this.userTokenCookie, token);
    window.localStorage.setItem(this.userTokenCookie, token);
    return token;
  }

  getConsent() {
    const value = this.getCookie(this.consentCookie);
    if (!value) {
      return { necessary: true, analytics: false, maps: false, voice: false, llm: false };
    }
    try {
      return JSON.parse(value);
    } catch {
      return { necessary: true, analytics: false, maps: false, voice: false, llm: false };
    }
  }

  hasConsent(category) {
    return Boolean(this.getConsent()[category]);
  }

  getCsrfToken() {
    return this.getCookie("deltaplant_csrf");
  }

  async request(path, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers || {});
    if (method !== "GET") {
      const csrf = this.getCsrfToken();
      if (csrf) {
        headers.set("X-CSRF-Token", csrf);
      }
      if (!headers.has("Content-Type") && options.body) {
        headers.set("Content-Type", "application/json");
      }
    }

    const response = await fetch(`${this.apiBase}${path}`, {
      credentials: "include",
      ...options,
      headers,
    });

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `HTTP ${response.status}`);
    }
    return response;
  }

  async saveConsent(categories) {
    const user_token = this.getOrCreateUserToken();
    const response = await this.request("/api/privacy/consent", {
      method: "POST",
      body: JSON.stringify({ user_token, ...categories }),
    });
    const payload = await response.json();
    this.setCookie(this.consentCookie, JSON.stringify(payload.categories), 36 * 30 * 24 * 3600);
    return payload;
  }

  async acceptAll() {
    const user_token = this.getOrCreateUserToken();
    const response = await this.request("/api/cookies/accept-all", {
      method: "POST",
      body: JSON.stringify({ user_token }),
    });
    const payload = await response.json();
    this.setCookie(this.consentCookie, JSON.stringify(payload.categories), 36 * 30 * 24 * 3600);
    return payload;
  }

  async rejectAll() {
    const user_token = this.getOrCreateUserToken();
    const response = await this.request("/api/cookies/reject-all", {
      method: "POST",
      body: JSON.stringify({ user_token }),
    });
    const payload = await response.json();
    this.setCookie(this.consentCookie, JSON.stringify(payload.categories), 36 * 30 * 24 * 3600);
    return payload;
  }

  async fetchPreferences() {
    const user_token = this.getOrCreateUserToken();
    const response = await this.request(`/api/cookies/preferences?user_token=${encodeURIComponent(user_token)}`);
    return response.json();
  }
}