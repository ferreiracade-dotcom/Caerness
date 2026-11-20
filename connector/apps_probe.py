"""Opt-in MCP Apps probe: one tool, `ui_probe`, that carries a small inline UI card.

Off by default. Set CAERNESS_APPS_PROBE=1 to add it; the live tools are untouched. It answers one question:
does the Claude app (web, desktop, phone) draw an interactive UI for this connector? The text result is
meaningful on its own, so a client without Apps support still gets something.
"""
from __future__ import annotations

import os

from mcp.server.apps import Apps, client_supports_apps
from mcp.server.mcpserver.context import Context

PROBE_URI = "ui://caerness/probe.html"

PROBE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body { margin: 0; padding: 12px; font: 14px/1.5 system-ui, sans-serif; color: #1f1e1d; background: transparent; }
  @media (prefers-color-scheme: dark) { body { color: #f0eee6; } .box { border-color: #4a4944 !important; } }
  .box { border: 1px solid #d8d5cc; border-radius: 12px; padding: 12px 14px; }
  h1 { font-size: 15px; font-weight: 500; margin: 0 0 6px; }
  .row { display: flex; justify-content: space-between; gap: 12px; padding: 3px 0; }
  .k { opacity: .65; }
  button { margin-top: 10px; font: inherit; padding: 6px 12px; border-radius: 8px; border: 1px solid #b8b5aa; background: transparent; color: inherit; }
</style></head>
<body><div class="box">
  <h1>Caerness connector UI probe</h1>
  <div class="row"><span class="k">Rendered</span><span>yes</span></div>
  <div class="row"><span class="k">Host</span><span id="host">waiting</span></div>
  <div class="row"><span class="k">Tool result</span><span id="result">not received</span></div>
  <button id="ask">Ask Claude to continue</button>
</div>
<script>
  var nextId = 1, pending = {};
  function send(method, params) {
    var id = nextId++;
    window.parent.postMessage({ jsonrpc: "2.0", id: id, method: method, params: params || {} }, "*");
    return new Promise(function (ok) { pending[id] = ok; });
  }
  window.addEventListener("message", function (ev) {
    var m = ev.data || {};
    if (m.id && pending[m.id]) { pending[m.id](m); delete pending[m.id]; return; }
    if (m.method === "ui/notifications/tool-result") {
      var t = ((m.params || {}).content || [{}])[0].text || "received";
      document.getElementById("result").textContent = String(t).slice(0, 40);
    }
  });
  send("ui/initialize", {
    protocolVersion: "2026-01-26",
    appInfo: { name: "caerness-probe", version: "0.1.0" },
    appCapabilities: {}
  }).then(function (r) {
    var info = (r.result || {}).hostInfo || {};
    document.getElementById("host").textContent = info.name ? info.name + " " + (info.version || "") : "no reply";
    window.parent.postMessage({ jsonrpc: "2.0", method: "ui/notifications/initialized", params: {} }, "*");
  });
  document.getElementById("ask").addEventListener("click", function () {
    send("ui/message", { role: "user", content: [{ type: "text", text: "The probe button worked. Say so in one line." }] });
  });
</script></body></html>
"""


def enabled() -> bool:
    return os.environ.get("CAERNESS_APPS_PROBE") == "1"


def make_apps() -> Apps:
    apps = Apps()

    @apps.tool(resource_uri=PROBE_URI, name="ui_probe",
               description="Test only: shows a small inline UI card. Call when the user asks to test connector UI.")
    def ui_probe(ctx: Context) -> str:
        if client_supports_apps(ctx):
            return "Probe: this client negotiated MCP Apps, so a UI card should be showing."
        return "Probe: this client did not negotiate MCP Apps, so no UI card will show."

    apps.add_html_resource(PROBE_URI, PROBE_HTML, name="caerness-probe", title="Connector UI probe")
    return apps
