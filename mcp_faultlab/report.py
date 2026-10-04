"""Generate a self-contained HTML report from a cassette."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .cassette import load


def _pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _message_label(message: dict[str, Any]) -> str:
    method = message.get("method")
    if method == "tools/call" and isinstance(message.get("params"), dict):
        return f"tools/call · {message['params'].get('name', 'unknown')}"
    if method:
        return str(method)
    if "result" in message:
        return "response · result"
    if "error" in message:
        return "response · error"
    return "notification"


def render(cassette: dict[str, Any], title: str = "mcp-faultlab report") -> str:
    events = cassette.get("events", [])
    faults = [event for event in events if event.get("fault")]
    requests = [event for event in events if event.get("direction") == "client->server"]
    responses = [event for event in events if event.get("direction") == "server->client"]
    cards = []
    for event in events:
        message = event.get("message", {})
        direction = event.get("direction", "unknown")
        fault = event.get("fault")
        classes = ["event", "request" if direction == "client->server" else "response"]
        if fault:
            classes.append("fault")
        body = f"<pre>{html.escape(_pretty(message))}</pre>"
        before = event.get("message_before_fault")
        if before is not None:
            body = (
                '<details class="before-after" open>'
                "<summary>Before / delivered</summary>"
                f"<div><span>Before fault</span><pre>{html.escape(_pretty(before))}</pre></div>"
                f"<div><span>Delivered to client</span>{body}</div>"
                "</details>"
            )
        fault_badge = (
            f'<span class="fault-badge">{html.escape(str(fault))}</span>' if fault else ""
        )
        cards.append(
            f'<article class="{" ".join(classes)}" data-search="{html.escape(_pretty(message).lower())}">'
            f'<div class="event-head"><span class="seq">#{event.get("sequence", "?")}</span>'
            f'<span class="direction">{html.escape(direction)}</span>'
            f'<span class="label">{html.escape(_message_label(message))}</span>'
            f'{fault_badge}'
            f'</div>{body}</article>'
        )
    escaped_title = html.escape(title)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escaped_title}</title>
<style>
:root {{ color-scheme: dark; --bg:#0b1020; --panel:#121a2c; --muted:#8ea0bd; --text:#edf3ff; --line:#253453; --green:#56d39a; --red:#ff7d91; --blue:#79a8ff; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--bg); color:var(--text); font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; }}
main {{ max-width:1200px; margin:0 auto; padding:34px 20px 80px; }} h1 {{ font:700 28px/1.2 Inter,system-ui,sans-serif; margin:0 0 8px; }}
.sub {{ color:var(--muted); word-break:break-all; margin-bottom:24px; }} .stats {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:20px 0 28px; }}
.stat,.event {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; }} .stat {{ padding:16px; }} .stat b {{ display:block; font:700 26px system-ui,sans-serif; }} .stat span {{ color:var(--muted); }}
.toolbar {{ position:sticky; top:0; z-index:2; background:color-mix(in srgb,var(--bg) 88%,transparent); backdrop-filter:blur(10px); padding:8px 0 14px; }} input {{ width:100%; padding:12px 14px; border:1px solid var(--line); border-radius:9px; background:#0e1628; color:var(--text); font:inherit; }}
.event {{ margin:12px 0; overflow:hidden; }} .event.fault {{ border-color:var(--red); box-shadow:0 0 0 1px #ff7d9133; }} .event-head {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:11px 14px; border-bottom:1px solid var(--line); }}
.seq,.direction {{ color:var(--muted); }} .label {{ color:var(--blue); }} .fault-badge {{ color:#160b10; background:var(--red); border-radius:999px; padding:2px 8px; font-size:12px; }}
pre {{ margin:0; padding:16px; overflow:auto; color:#d9e5ff; }} details summary {{ cursor:pointer; color:var(--green); padding:12px 16px; border-bottom:1px solid var(--line); }} .before-after > div {{ border-bottom:1px solid var(--line); }} .before-after span {{ display:block; padding:10px 16px 0; color:var(--muted); }}
@media(max-width:700px) {{ .stats {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} main {{ padding:22px 12px 60px; }} }}
</style></head><body><main>
<h1>{escaped_title}</h1><div class="sub">{html.escape(str(cassette.get("target", "")))}</div>
<section class="stats"><div class="stat"><b>{len(events)}</b><span>events</span></div><div class="stat"><b>{len(requests)}</b><span>requests</span></div><div class="stat"><b>{len(responses)}</b><span>responses</span></div><div class="stat"><b>{len(faults)}</b><span>faults</span></div></section>
<div class="toolbar"><input id="filter" placeholder="Filter method, tool, or payload…" autocomplete="off"></div>
<section id="timeline">{"".join(cards)}</section>
</main><script>
const input=document.querySelector('#filter'); const events=[...document.querySelectorAll('.event')];
input.addEventListener('input',()=>{{const q=input.value.toLowerCase();events.forEach(e=>e.hidden=q&&!e.dataset.search.includes(q));}});
</script></body></html>"""


def write_report(cassette_path: str, output_path: str, title: str | None = None) -> Path:
    cassette = load(cassette_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(cassette, title or f"mcp-faultlab · {Path(cassette_path).name}"), encoding="utf-8")
    return output
