import { CookieManager } from "./cookie-manager.js";

export class SiteAnalytics {
  constructor({ manager = new CookieManager(), pageKind = "website", localPreferenceKey = "" } = {}) {
    this.manager = manager;
    this.pageKind = pageKind;
    this.localPreferenceKey = localPreferenceKey;
    this.sessionStorageKey = "deltaplant_analytics_session_id";
    this.sessionBootStorageKey = "deltaplant_analytics_session_booted";
    this.sessionId = this.getOrCreateSessionId();
    this.backendReady = null;
    this.pageViewSent = false;
    this.visibleSince = performance.now();
    this.visibleAccumulatedMs = 0;
    this.hiddenAt = null;
  }

  getOrCreateSessionId() {
    try {
      const existing = window.sessionStorage.getItem(this.sessionStorageKey);
      if (existing) {
        return existing;
      }
      const created = `sess_${(window.crypto?.randomUUID?.() || `${Date.now()}_${Math.random().toString(36).slice(2, 12)}`).replace(/-/g, "")}`;
      window.sessionStorage.setItem(this.sessionStorageKey, created);
      return created;
    } catch {
      return `sess_${Date.now()}`;
    }
  }

  hasAnalyticsConsent() {
    return this.manager.hasConsent("analytics");
  }

  detectDeviceType() {
    const ua = navigator.userAgent || "";
    if (/ipad|tablet/i.test(ua)) {
      return "tablet";
    }
    if (/mobi|android|iphone/i.test(ua) || window.innerWidth < 768) {
      return "mobile";
    }
    if (window.innerWidth < 1180) {
      return "tablet";
    }
    return "desktop";
  }

  readLandingPreferences() {
    if (!this.localPreferenceKey) {
      return null;
    }
    try {
      const rawValue = window.localStorage.getItem(this.localPreferenceKey);
      if (!rawValue) {
        return null;
      }
      const parsed = JSON.parse(rawValue);
      const categories = parsed?.categories || parsed;
      if (!categories || typeof categories !== "object") {
        return null;
      }
      return {
        analytics: Boolean(categories.analytics),
        media: Boolean(categories.media),
      };
    } catch {
      return null;
    }
  }

  async ensureBackend() {
    if (this.backendReady !== null) {
      return this.backendReady;
    }
    if (!this.manager.apiBase) {
      this.backendReady = false;
      return false;
    }
    try {
      const response = await fetch(`${this.manager.apiBase}/api/health`, {
        credentials: "include",
      });
      this.backendReady = response.ok;
      return this.backendReady;
    } catch {
      this.backendReady = false;
      return false;
    }
  }

  buildPayload(eventType, { eventLabel = "", eventData = {}, engagedSeconds = null } = {}) {
    const timezone = Intl.DateTimeFormat?.().resolvedOptions?.().timeZone || "";
    return {
      user_token: this.manager.getOrCreateUserToken(),
      session_id: this.sessionId,
      event_type: eventType,
      event_label: eventLabel || undefined,
      page_path: `${window.location.pathname}${window.location.search}`,
      page_title: document.title,
      referrer: document.referrer || undefined,
      language: navigator.language || document.documentElement.lang || undefined,
      timezone: timezone || undefined,
      device_type: this.detectDeviceType(),
      viewport: `${window.innerWidth}x${window.innerHeight}`,
      screen: `${window.screen?.width || 0}x${window.screen?.height || 0}`,
      engaged_seconds: typeof engagedSeconds === "number" ? engagedSeconds : undefined,
      event_data: {
        page_kind: this.pageKind,
        ...eventData,
      },
    };
  }

  async track(eventType, { eventLabel = "", eventData = {}, engagedSeconds = null, keepalive = false } = {}) {
    if (!this.hasAnalyticsConsent()) {
      return false;
    }
    if (!(await this.ensureBackend())) {
      return false;
    }

    try {
      const response = await fetch(`${this.manager.apiBase}/api/analytics/events`, {
        method: "POST",
        credentials: "include",
        keepalive,
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(this.buildPayload(eventType, { eventLabel, eventData, engagedSeconds })),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  async syncConsentFromPreferences(preferences = {}, source = "landing_preference_center") {
    const current = this.manager.getConsent();
    const nextAnalytics = Boolean(preferences.analytics);
    if (Boolean(current.analytics) === nextAnalytics) {
      return current;
    }

    return this.manager.saveConsent(
      {
        analytics: nextAnalytics,
        maps: current.maps,
        voice: current.voice,
        llm: current.llm,
      },
      source,
    );
  }

  async bootstrapSessionEvents(forcePageView = false) {
    if (!this.hasAnalyticsConsent()) {
      return;
    }
    if (!(await this.ensureBackend())) {
      return;
    }

    const sessionKey = `${this.sessionBootStorageKey}:${this.sessionId}`;
    let isNewSession = false;
    try {
      if (!window.sessionStorage.getItem(sessionKey)) {
        window.sessionStorage.setItem(sessionKey, "1");
        isNewSession = true;
      }
    } catch {
      isNewSession = !this.pageViewSent;
    }

    if (isNewSession) {
      await this.track("session_start", { eventLabel: this.pageKind, eventData: { page_kind: this.pageKind } });
    }

    if (!this.pageViewSent || forcePageView) {
      this.pageViewSent = true;
      await this.track("page_view", { eventLabel: this.pageKind, eventData: { page_kind: this.pageKind } });
    }
  }

  installClickTracking() {
    document.addEventListener("click", (event) => {
      const element = event.target instanceof Element ? event.target.closest("[data-analytics-event], a[href]") : null;
      if (!element) {
        return;
      }

      const trackedEvent = element.getAttribute("data-analytics-event");
      if (trackedEvent) {
        const label = element.getAttribute("data-analytics-label") || element.id || element.textContent?.trim() || this.pageKind;
        void this.track(trackedEvent, {
          eventLabel: label.slice(0, 96),
          eventData: {
            id: element.id || undefined,
            href: element.getAttribute("href") || undefined,
          },
        });
        return;
      }

      if (element.tagName !== "A") {
        return;
      }

      const href = element.getAttribute("href") || "";
      if (!href || href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:")) {
        return;
      }

      const target = new URL(href, window.location.href);
      if (target.hostname === window.location.hostname) {
        return;
      }

      void this.track("outbound_click", {
        eventLabel: target.hostname.slice(0, 96),
        eventData: {
          href: target.href,
          link_text: (element.textContent || "").trim().slice(0, 120),
        },
      });
    }, { passive: true });
  }

  installVisibilityTracking() {
    const finalizeEngagement = () => {
      if (!this.hasAnalyticsConsent()) {
        return;
      }

      let visibleMs = this.visibleAccumulatedMs;
      if (this.hiddenAt === null) {
        visibleMs += Math.max(0, performance.now() - this.visibleSince);
      }
      const engagedSeconds = Math.round((visibleMs / 1000) * 100) / 100;
      if (engagedSeconds <= 0) {
        return;
      }
      void this.track("page_exit", {
        eventLabel: this.pageKind,
        engagedSeconds,
        keepalive: true,
        eventData: { page_kind: this.pageKind },
      });
    };

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") {
        this.visibleAccumulatedMs += Math.max(0, performance.now() - this.visibleSince);
        this.hiddenAt = performance.now();
        return;
      }

      this.hiddenAt = null;
      this.visibleSince = performance.now();
    });

    window.addEventListener("pagehide", finalizeEngagement);
  }

  async boot() {
    this.installClickTracking();
    this.installVisibilityTracking();

    const landingPreferences = this.readLandingPreferences();
    if (landingPreferences) {
      await this.syncConsentFromPreferences(landingPreferences, "landing_bootstrap");
    }

    window.addEventListener("deltaplant:consent-updated", async (event) => {
      const categories = event.detail?.categories || {};
      const source = event.detail?.source || "consent_update";
      if (!categories.analytics) {
        return;
      }
      if (source !== "landing_bootstrap") {
        await this.track("privacy_update", {
          eventLabel: source,
          eventData: { analytics: true, source },
        });
      }
      await this.bootstrapSessionEvents(source !== "landing_bootstrap");
    });

    if (this.hasAnalyticsConsent()) {
      await this.bootstrapSessionEvents(false);
    }
  }
}

export function initDeltaWebsiteAnalytics(options = {}) {
  const analytics = new SiteAnalytics(options);
  window.deltaSiteAnalytics = analytics;
  window.deltaTrackWebsiteEvent = (eventType, eventData = {}, extra = {}) => analytics.track(eventType, { eventData, ...extra });
  window.deltaSyncWebsiteConsent = (preferences = {}, source = "landing_preference_center") => analytics.syncConsentFromPreferences(preferences, source);
  void analytics.boot();
  return analytics;
}