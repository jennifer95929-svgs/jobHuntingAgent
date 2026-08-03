// injector.js — js-reverse-cloak: injected into BOSS page context
// Handles DOM interaction, anti-detection, and exposes internal APIs

(function() {
    if (window.__bossCloakInjected) return;
    window.__bossCloakInjected = true;

    const NATIVE_CLICK = Element.prototype.click;

    console.log('[cloak] injected into BOSS chat page');
})();
