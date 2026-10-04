"""Directory-level Scenario execution and aggregate reporting."""

import os
import time

from .report import output_paths, write_campaign_html, write_json, write_html
from .runner import run_scenario
from .scenario import load_scenario, validate_scenario


def discover(path, excluded=()):
    if os.path.isfile(path):
        return [os.path.abspath(path)]
    if not os.path.isdir(path):
        raise OSError("scenario path does not exist: %s" % path)
    excluded = {os.path.abspath(item) for item in excluded}
    paths = []
    for root, directories, files in os.walk(path):
        root = os.path.abspath(root)
        directories[:] = [directory for directory in sorted(directories) if os.path.join(root, directory) not in excluded and not directory.startswith(".")]
        directories.sort()
        for filename in sorted(files):
            if filename.startswith("."):
                continue
            if filename.lower().endswith((".yml", ".yaml", ".json")):
                paths.append(os.path.abspath(os.path.join(root, filename)))
    if not paths:
        raise ValueError("no scenario files found under: %s" % path)
    return paths


def _scenario_output_dir(scenario_path, root_path, out_dir):
    relative = os.path.relpath(scenario_path, root_path)
    slug = os.path.splitext(relative)[0].replace(os.sep, "__").replace("/", "__")
    return os.path.join(out_dir, slug)


def execute_one(path, root_path=None, out_dir=None):
    started = time.time()
    record = {"path": os.path.abspath(path), "scenario": os.path.splitext(os.path.basename(path))[0]}
    try:
        scenario = load_scenario(path)
        errors = validate_scenario(scenario)
        if errors:
            record.update({"passed": False, "status": "invalid", "errors": errors, "duration_ms": round((time.time() - started) * 1000, 2)})
            return record
        result = run_scenario(scenario)
        scenario_output = _scenario_output_dir(path, root_path or os.path.dirname(path), out_dir) if out_dir else None
        run_path, html_path, cassette_path = output_paths(path, scenario_output)
        if scenario_output:
            os.makedirs(scenario_output, exist_ok=True)
            write_json(run_path, result)
            write_html(html_path, result)
            write_json(cassette_path, {"version": 2, "transport": result.get("transport", "stdio"), "scenario": result["scenario"], "command": result["command"], "metrics": result.get("metrics", {}), "events": result["events"]})
        checks = result.get("assertions", [])
        record.update({
            "scenario": result.get("scenario"),
            "passed": result.get("passed", False),
            "status": result.get("status"),
            "security_violations": result.get("security_violations", 0),
            "attack_injections": result.get("attack_injections", 0),
            "assertions_passed": sum(1 for item in checks if item.get("passed")),
            "assertions_failed": sum(1 for item in checks if not item.get("passed")),
            "duration_ms": result.get("duration_ms", round((time.time() - started) * 1000, 2)),
            "report": os.path.relpath(html_path, out_dir) if out_dir else html_path,
            "run_json": os.path.relpath(run_path, out_dir) if out_dir else run_path,
        })
        return record
    except (OSError, ValueError, TypeError) as error:
        record.update({"passed": False, "status": "error", "errors": [str(error)], "duration_ms": round((time.time() - started) * 1000, 2)})
        return record


def run_campaign(path, out_dir):
    paths = discover(path, excluded=(out_dir,))
    root_path = os.path.abspath(path) if os.path.isdir(path) else os.path.dirname(paths[0])
    os.makedirs(out_dir, exist_ok=True)
    records = [execute_one(item, root_path, out_dir) for item in paths]
    summary_path = os.path.abspath(os.path.join(out_dir, "campaign.json"))
    html_path = os.path.abspath(os.path.join(out_dir, "campaign.html"))
    summary = {
        "version": 1,
        "root": os.path.abspath(path),
        "out": os.path.abspath(out_dir),
        "scenario_count": len(records),
        "passed_count": sum(1 for item in records if item.get("passed")),
        "failed_count": sum(1 for item in records if not item.get("passed")),
        "security_violations": sum(item.get("security_violations", 0) for item in records),
        "attack_injections": sum(item.get("attack_injections", 0) for item in records),
        "summary_path": summary_path,
        "html_path": html_path,
        "scenarios": records,
    }
    summary["passed"] = summary["failed_count"] == 0
    write_json(summary_path, summary)
    write_campaign_html(html_path, summary)
    return summary
