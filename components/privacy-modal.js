import { CookieManager } from "./cookie-manager.js";

export class PrivacyModal {
  constructor({ manager = new CookieManager() } = {}) {
    this.manager = manager;
    this.root = null;
  }

  mount(target = document.body) {
    const consent = this.manager.getConsent();
    const wrapper = document.createElement("div");
    wrapper.className = "dp-privacy-modal";
    wrapper.hidden = true;
    wrapper.innerHTML = `
      <div class="dp-privacy-modal__backdrop" data-close="true"></div>
      <div class="dp-privacy-modal__panel" role="dialog" aria-modal="true" aria-label="Privacy controls">
        <header>
          <p>Privacy controls</p>
          <button type="button" data-close="true" aria-label="Close">×</button>
        </header>
        <section>
          <label><input type="checkbox" checked disabled /> Necessary cookies</label>
          <label><input type="checkbox" name="analytics" ${consent.analytics ? "checked" : ""} /> Analytics</label>
          <label><input type="checkbox" name="maps" ${consent.maps ? "checked" : ""} /> Interactive maps</label>
          <label><input type="checkbox" name="voice" ${consent.voice ? "checked" : ""} /> Voice synthesis</label>
          <label><input type="checkbox" name="llm" ${consent.llm ? "checked" : ""} /> LLM narratives</label>
        </section>
        <footer>
          <button type="button" data-action="save">Save preferences</button>
        </footer>
      </div>
    `;
    wrapper.addEventListener("click", (event) => {
      const targetElement = event.target;
      if (!(targetElement instanceof HTMLElement)) {
        return;
      }
      if (targetElement.dataset.close === "true") {
        this.hide();
      }
    });
    wrapper.querySelector('[data-action="save"]').addEventListener("click", async () => {
      const categories = {
        analytics: wrapper.querySelector('input[name="analytics"]').checked,
        maps: wrapper.querySelector('input[name="maps"]').checked,
        voice: wrapper.querySelector('input[name="voice"]').checked,
        llm: wrapper.querySelector('input[name="llm"]').checked,
      };
      await this.manager.saveConsent(categories);
      this.hide();
    });
    target.appendChild(wrapper);
    this.root = wrapper;
  }

  show() {
    if (this.root) {
      this.root.hidden = false;
    }
  }

  hide() {
    if (this.root) {
      this.root.hidden = true;
    }
  }
}