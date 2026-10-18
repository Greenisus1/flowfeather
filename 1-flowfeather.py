#!/usr/bin/env python3
"""Flowfeather - tiny self-hosted automations for your Pi.

Fullscreen curses UI. A flow is one trigger + one action: every N
minutes, when a file changes, or when an RSS feed posts something new -
run a shell command, append to a log file, or fetch a URL. Pure stdlib,
one JSON state file, no daemon: press r to run what is due, or put
`flowfeather.py --tick` in cron.

MIT license, copyright Greenisus1. Built with AI assistance from my design.
"""
import curses, json, os, subprocess, sys, time, urllib.request
import xml.etree.ElementTree as ET

VERSION = "1.0.0"
APP_DIR = os.environ.get("FLOWFEATHER_HOME", "/root/flowfeather")
STORE = os.path.join(APP_DIR, "flows.json")
CMD_TIMEOUT = 60
LOG_KEEP = 20


def load_store():
    try:
        return json.load(open(STORE))
    except Exception:
        return {"flows": []}


def save_store(st):
    os.makedirs(APP_DIR, exist_ok=True)
    json.dump(st, open(STORE, "w"), indent=1)


def new_flow(name, trig, act):
    return {"name": name, "trigger": trig, "action": act, "enabled": True,
            "last_run": 0, "runs": 0, "state": {}, "log": []}


# ---------- triggers: due(flow, now) -> (bool, reason) ----------

def due(flow, now):
    if not flow.get("enabled"):
        return False, "disabled"
    t = flow["trigger"]
    kind = t.get("type")
    if kind == "interval":
        mins = max(1, int(t.get("minutes", 60)))
        if now - flow.get("last_run", 0) >= mins * 60:
            return True, f"every {mins}m"
        return False, f"not due (every {mins}m)"
    if kind == "file":
        path = t.get("path", "")
        try:
            st_ = os.stat(path)
            if st_.st_size <= 1024 * 1024:
                import hashlib
                with open(path, "rb") as fh:
                    sig = hashlib.sha1(fh.read()).hexdigest()
            else:
                sig = f"{st_.st_mtime_ns}:{st_.st_size}"
        except OSError:
            sig = ""
        old = flow["state"].get("sig")
        flow["state"]["sig"] = sig
        if old is None:
            return False, "baseline recorded"
        if sig != old:
            return True, f"{path} changed"
        return False, "unchanged"
    if kind == "rss":
        url = t.get("url", "")
        try:
            data = urllib.request.urlopen(url, timeout=15).read()
            root = ET.fromstring(data)
            first = root.find("channel/item")
            guid = ""
            if first is not None:
                guid = (first.findtext("guid") or first.findtext("link")
                        or first.findtext("title") or "")
        except Exception as e:
            return False, f"fetch error: {str(e)[:60]}"
        old = flow["state"].get("guid")
        flow["state"]["guid"] = guid
        if old is None:
            return False, "baseline recorded"
        if guid and guid != old:
            return True, "new feed item"
        return False, "no new item"
    return False, f"unknown trigger {kind!r}"


# ---------- actions: act(flow) -> outcome string ----------

def act(flow):
    a = flow["action"]
    kind = a.get("type")
    if kind == "shell":
        p = subprocess.run(a.get("command", "true"), shell=True,
                           capture_output=True, text=True, timeout=CMD_TIMEOUT)
        out = (p.stdout or "").strip() or (p.stderr or "").strip()
        return f"rc={p.returncode} {out[:120]}"
    if kind == "append":
        path = a.get("path", os.path.join(APP_DIR, "flowfeather.log"))
        line = a.get("line", "flow {name} fired")
        line = line.replace("{name}", flow["name"])
        line = line.replace("{time}", time.strftime("%Y-%m-%d %H:%M:%S"))
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a") as fh:
            fh.write(line + "\n")
        return f"appended to {os.path.basename(path)}"
    if kind == "url":
        url = a.get("url", "")
        data = a.get("body")
        req = urllib.request.Request(
            url, data=data.encode() if data else None,
            headers={"User-Agent": "flowfeather/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return f"HTTP {r.status}"
    return f"unknown action {kind!r}"


def run_due(st, now=None, force=False):
    """Run every due (or forced) flow once. Returns [(name, reason, outcome)]."""
    now = now or int(time.time())
    results = []
    for flow in st["flows"]:
        is_due, reason = (flow.get("enabled", False), "forced") if force \
            else due(flow, now)
        if not is_due:
            continue
        try:
            outcome = act(flow)
        except Exception as e:
            outcome = f"ERROR: {str(e)[:120]}"
        flow["last_run"] = now
        flow["runs"] = flow.get("runs", 0) + 1
        flow["log"].append(f"{time.strftime('%m-%d %H:%M')} {reason}: {outcome}")
        flow["log"] = flow["log"][-LOG_KEEP:]
        results.append((flow["name"], reason, outcome))
    return results


def trig_summary(t):
    if t.get("type") == "interval":
        return f"every {t.get('minutes', 60)}m"
    if t.get("type") == "file":
        return f"file {t.get('path', '?')}"
    if t.get("type") == "rss":
        return f"rss {t.get('url', '?')[:40]}"
    return "?"


def act_summary(a):
    if a.get("type") == "shell":
        return f"run `{a.get('command', '')[:40]}`"
    if a.get("type") == "append":
        return f"append to {os.path.basename(a.get('path', 'log'))}"
    if a.get("type") == "url":
        return f"fetch {a.get('url', '')[:40]}"
    return "?"


# ---------- UI ----------

def header(scr, w, sub):
    scr.addnstr(0, 0, f" FLOWFEATHER v{VERSION} - {sub}".ljust(w - 1), w - 1,
                curses.A_REVERSE)


def keys(scr, h, w, s):
    scr.addnstr(h - 1, 0, s[:w - 1], w - 1, curses.A_REVERSE)


def prompt(scr, label):
    curses.echo()
    curses.curs_set(1)
    h, w = scr.getmaxyx()
    scr.addnstr(h - 3, 2, label + " ", w - 4, curses.A_BOLD)
    scr.refresh()
    try:
        v = scr.getstr(h - 3, 2 + len(label) + 1, 300).decode().strip()
    except Exception:
        v = ""
    curses.noecho()
    curses.curs_set(0)
    return v


def add_flow_wizard(scr):
    name = prompt(scr, "Flow name:")
    if not name:
        return None
    tt = prompt(scr, "Trigger: [i]nterval, [f]ile change, [r]ss:")
    tt = (tt or "i").lower()[:1]
    if tt == "f":
        path = prompt(scr, "File path to watch:")
        if not path:
            return None
        trig = {"type": "file", "path": path}
    elif tt == "r":
        url = prompt(scr, "Feed URL:")
        if not url:
            return None
        trig = {"type": "rss", "url": url}
    else:
        mins = prompt(scr, "Every how many minutes? [60]:")
        trig = {"type": "interval", "minutes": int(mins) if mins.isdigit() else 60}
    at = prompt(scr, "Action: [s]hell command, [a]ppend to file, [u]rl fetch:")
    at = (at or "a").lower()[:1]
    if at == "s":
        cmd = prompt(scr, "Shell command:")
        if not cmd:
            return None
        act_ = {"type": "shell", "command": cmd}
    elif at == "u":
        url = prompt(scr, "URL to fetch:")
        if not url:
            return None
        act_ = {"type": "url", "url": url}
    else:
        path = prompt(scr, "File to append to (~/flow.log style):")
        if not path:
            return None
        line = prompt(scr, "Line to append [{name} {time} ok]:")
        act_ = {"type": "append", "path": path,
                "line": line or "{name} fired at {time}"}
    return new_flow(name, trig, act_)


def view_log(scr, flow):
    top = 0
    while True:
        scr.erase()
        h, w = scr.getmaxyx()
        header(scr, w, f"log: {flow['name'][:w - 22]}")
        lines = flow.get("log") or ["(no runs yet)"]
        body = h - 3
        top = max(0, min(top, len(lines) - body))
        for row, line in enumerate(lines[top:top + body]):
            scr.addnstr(2 + row, 2, line, w - 4)
        keys(scr, h, w, "[j/k] scroll  [q] back")
        scr.refresh()
        ch = scr.getch()
        if ch in (curses.KEY_UP, ord("k")):
            top = max(0, top - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            top = min(max(0, len(lines) - body), top + 1)
        elif ch in (ord("q"), 27):
            return


def main(scr):
    curses.curs_set(0)
    st = load_store()
    sel, msg = 0, ""
    while True:
        scr.erase()
        h, w = scr.getmaxyx()
        header(scr, w, "your flows")
        flows = st["flows"]
        if not flows:
            scr.addnstr(3, 4, "No flows yet - press a to add one.", w - 8)
        for row, fl in enumerate(flows[:h - 4]):
            on = "on " if fl.get("enabled") else "off"
            line = (f"[{on}] {fl['name']}  |  {trig_summary(fl['trigger'])}"
                    f" -> {act_summary(fl['action'])}  |  {fl.get('runs', 0)} runs")
            attr = curses.A_REVERSE if row == sel else 0
            if not fl.get("enabled"):
                attr |= curses.A_DIM
            scr.addnstr(2 + row, 2, line.ljust(w - 4)[:w - 4], w - 4, attr)
        if msg:
            scr.addnstr(h - 2, 2, msg, w - 4, curses.A_BOLD)
        keys(scr, h, w, "[a]dd  [e]nable/disable  [d]elete  [l]og  "
                        "[r]un due  run [A]ll now  [q]uit")
        scr.refresh()
        ch = scr.getch()
        msg = ""
        if ch in (curses.KEY_UP, ord("k")):
            sel = max(0, sel - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            sel = min(max(0, len(flows) - 1), sel + 1)
        elif ch == ord("a"):
            fl = add_flow_wizard(scr)
            if fl:
                flows.append(fl)
                save_store(st)
                msg = f"Added {fl['name']}."
        elif ch == ord("e") and flows:
            flows[sel]["enabled"] = not flows[sel].get("enabled")
            save_store(st)
        elif ch == ord("d") and flows:
            gone = flows.pop(sel)
            sel = max(0, sel - 1)
            save_store(st)
            msg = f"Deleted {gone['name']}."
        elif ch == ord("l") and flows:
            view_log(scr, flows[sel])
        elif ch == ord("r"):
            res = run_due(st)
            save_store(st)
            msg = f"Ran {len(res)} due flow(s)." if res else "Nothing due."
        elif ch == ord("A"):
            res = run_due(st, force=True)
            save_store(st)
            msg = f"Force-ran {len(res)} enabled flow(s)."
        elif ch in (ord("q"), 27):
            return


if __name__ == "__main__":
    if "--tick" in sys.argv:
        st = load_store()
        res = run_due(st)
        save_store(st)
        for name, reason, outcome in res:
            print(f"{name}: {reason}: {outcome}")
        sys.exit(0)
    curses.wrapper(main)
