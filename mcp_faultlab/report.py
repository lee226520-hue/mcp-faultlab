import html
import json
import os


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def write_html(path, run):
    checks = run.get("assertions", [])
    passed = sum(1 for item in checks if item.get("passed"))
    failed = len(checks) - passed
    rows = "".join(
        "<tr class='%s'><td>%s</td><td>%s</td><td>%s<br><small>events: %s</small></td></tr>" % (
            "pass" if item.get("passed") else "fail",
            "PASS" if item.get("passed") else "FAIL",
            html.escape(str(item.get("name"))),
            html.escape(str(item.get("detail"))),
            html.escape(", ".join(str(value) for value in item.get("evidence", [])) or "none"),
        ) for item in checks
    )
    metrics = run.get("metrics", {})
    metric_cards = "".join("<div class='card'><b>%s</b><br>%s</div>" % (html.escape(str(value)), html.escape(str(key).replace("_", " "))) for key, value in metrics.items())
    events = html.escape(json.dumps(run.get("events", []), ensure_ascii=False, indent=2))
    doc = """<!doctype html><meta charset='utf-8'><title>mcp-faultlab: {name}</title>
<style>body{{font:15px system-ui;margin:40px;color:#202124}} .summary{{display:flex;gap:12px}} .card{{padding:12px 18px;border:1px solid #ddd;border-radius:8px}} .ok{{color:#087f23}} .bad{{color:#b42318}} table{{border-collapse:collapse;width:100%;margin-top:24px}} td,th{{border-bottom:1px solid #ddd;padding:10px;text-align:left}} .pass{{background:#f4fbf5}} .fail{{background:#fff4f2}} pre{{background:#f6f8fa;padding:16px;overflow:auto}}</style>
<h1>{name}</h1><p>Command: <code>{command}</code></p>
<div class='summary'><div class='card'><b>{passed}</b> passed</div><div class='card'><b>{failed}</b> failed</div><div class='card'><b class='{security_class}'>{security}</b> security violation</div><div class='card'><b>{attacks}</b> attack injected</div><div class='card'>status: <b>{status}</b></div>{metric_cards}</div>
<table><thead><tr><th>Result</th><th>Assertion</th><th>Evidence</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Trace</h2><pre>{events}</pre>
""".format(name=html.escape(str(run.get("scenario"))), command=html.escape(str(run.get("command"))), passed=passed, failed=failed, security=run.get("security_violations", 0), attacks=run.get("attack_injections", 0), security_class="bad" if run.get("security_violations") else "ok", status=html.escape(str(run.get("status"))), metric_cards=metric_cards, rows=rows, events=events)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(doc)


def output_paths(scenario_path, out_dir=None):
    directory = out_dir or os.path.dirname(os.path.abspath(scenario_path))
    stem = os.path.splitext(os.path.basename(scenario_path))[0]
    return (os.path.join(directory, stem + ".run.json"), os.path.join(directory, stem + ".html"), os.path.join(directory, stem + ".cassette.json"))


def write_campaign_html(path, summary):
    rows = []
    for item in summary.get("scenarios", []):
        result = "PASS" if item.get("passed") else "FAIL"
        report = item.get("report")
        report_link = "<a href='%s'>report</a>" % html.escape(report) if report else "-"
        error = "; ".join(item.get("errors", []))
        rows.append("<tr class='%s'><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            "pass" if item.get("passed") else "fail",
            html.escape(str(item.get("scenario"))),
            result,
            html.escape(str(item.get("assertions_passed", 0))),
            html.escape(str(item.get("assertions_failed", 0))),
            html.escape(str(item.get("security_violations", 0))),
            report_link if not error else html.escape(error),
        ))
    doc = """<!doctype html><meta charset='utf-8'><title>mcp-faultlab campaign</title>
<style>body{{font:15px system-ui;margin:40px;color:#202124}} .summary{{display:flex;gap:12px;flex-wrap:wrap}} .card{{padding:12px 18px;border:1px solid #ddd;border-radius:8px}} table{{border-collapse:collapse;width:100%;margin-top:24px}} td,th{{border-bottom:1px solid #ddd;padding:10px;text-align:left}} .pass{{background:#f4fbf5}} .fail{{background:#fff4f2}}</style>
<h1>mcp-faultlab campaign</h1>
<div class='summary'><div class='card'><b>{total}</b> scenarios</div><div class='card'><b>{passed}</b> passed</div><div class='card'><b>{failed}</b> failed</div><div class='card'><b>{security}</b> security violations</div><div class='card'><b>{attacks}</b> attacks injected</div></div>
<table><thead><tr><th>Scenario</th><th>Result</th><th>Assertions passed</th><th>Assertions failed</th><th>Security violations</th><th>Evidence</th></tr></thead><tbody>{rows}</tbody></table>
""".format(total=summary.get("scenario_count", 0), passed=summary.get("passed_count", 0), failed=summary.get("failed_count", 0), security=summary.get("security_violations", 0), attacks=summary.get("attack_injections", 0), rows="".join(rows))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(doc)
