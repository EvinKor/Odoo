/** @odoo-module **/

function updatePortalPointsBadge(badge) {
    if (!badge) {
        return;
    }
    const valueNode = badge.querySelector(".js-event-portal-points-value");
    const debugNode = badge.parentElement
        ? badge.parentElement.querySelector(".js-event-portal-points-debug")
        : null;
    const endpoint = badge.dataset.pointsEndpoint;
    if (!valueNode || !endpoint) {
        return;
    }

    const setDebugText = (text) => {
        if (debugNode) {
            debugNode.textContent = text || "";
        }
    };

    const setBadgeTitle = (text) => {
        badge.title = text || "";
    };

    fetch(endpoint, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify({
            jsonrpc: "2.0",
            method: "call",
            params: {},
        }),
    })
        .then(async (response) => {
            const rawText = await response.text();
            let payload;
            try {
                payload = rawText ? JSON.parse(rawText) : {};
            } catch {
                throw new Error(`Non-JSON response: ${rawText || response.statusText}`);
            }
            if (!response.ok) {
                const errorText = payload && payload.error
                    ? JSON.stringify(payload.error)
                    : rawText || response.statusText;
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }
            return payload;
        })
        .then((payload) => {
            const result = payload && Object.prototype.hasOwnProperty.call(payload, "result")
                ? payload.result
                : payload;
            const email = result && result.email ? String(result.email) : "no-email";
            const url = result && result.url ? String(result.url) : "";
            const attemptedUrls = result && Array.isArray(result.attempted_urls)
                ? result.attempted_urls.map((item) => String(item))
                : [];
            const sessionEmail = result && result.session_payload_email
                ? String(result.session_payload_email)
                : "";
            const debugParts = [sessionEmail && sessionEmail !== email
                ? `email: ${email} | session email: ${sessionEmail}`
                : `email: ${email}`];
            if (url) {
                debugParts.push(`url: ${url}`);
            }
            const debugText = debugParts.join(" | ");
            console.info("[event_application] portal points badge", result);
            setDebugText(debugText);
            setBadgeTitle([debugText].concat(attemptedUrls.map((item) => `tried: ${item}`)).join("\n"));
            if (result && result.ok === false) {
                valueNode.textContent = "0";
                const errorText = result.message || result.error || "fetch failed";
                setDebugText(`${debugText} | error: ${errorText}`);
                setBadgeTitle([`${debugText} | error: ${errorText}`].concat(attemptedUrls.map((item) => `tried: ${item}`)).join("\n"));
                console.error("[event_application] portal points badge error", result);
                return;
            }
            const balance = Number(result && result.balance);
            valueNode.textContent = Number.isFinite(balance) ? String(Math.trunc(balance)) : "0";
        })
        .catch((error) => {
            valueNode.textContent = "0";
            setDebugText(`fetch error: ${error.message}`);
            setBadgeTitle(`fetch error: ${error.message}`);
            console.error("[event_application] portal points badge fetch failed", error);
        });
}

function initPortalPointsBadge() {
    document
        .querySelectorAll(".js-event-portal-points-badge")
        .forEach((badge) => updatePortalPointsBadge(badge));
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPortalPointsBadge);
} else {
    initPortalPointsBadge();
}
