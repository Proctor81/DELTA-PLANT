import { CookieManager } from "./cookie-manager.js";

export class CookieBanner {
  constructor({ manager = new CookieManager(), onManage = null } = {}) {
    this.manager = manager;
    this.onManage = onManage;
    this.root = null;
  }

  mount(target = document.body) {
    if (this.manager.getCookie(this.manager.consentCookie)) {
      return;
    }
    const banner = document.createElement("aside");
    banner.className = "dp-cookie-banner";
    banner.innerHTML = `
      <div class="dp-cookie-banner__copy">
        <strong>Privacy-first cookies</strong>
        <p>DELTA Plant usa solo cookie strettamente necessari finché non scegli tu di abilitare analytics, voce o LLM.</p>
      </div>
      <div class="dp-cookie-banner__actions">
        <button type="button" data-action="reject">Reject non-essential</button>
        <button type="button" data-action="manage">Manage</button>
        <button type="button" data-action="accept">Accept all</button>
      </div>
    `;
    banner.querySelector('[data-action="accept"]').addEventListener("click", async () => {
      await this.manager.acceptAll();
      banner.remove();
    });
    banner.querySelector('[data-action="reject"]').addEventListener("click", async () => {
      await this.manager.rejectAll();
      banner.remove();
    });
    banner.querySelector('[data-action="manage"]').addEventListener("click", () => {
      this.onManage?.();
    });
    target.appendChild(banner);
    this.root = banner;
  }
}