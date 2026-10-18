"""PTY walkthrough: add an append flow via the wizard, force-run, check log+file."""
import json, os, pty, re, select, sys, tempfile, time

home = tempfile.mkdtemp()
target = os.path.join(home, "hits.log")
env = dict(os.environ, FLOWFEATHER_HOME=home, TERM="xterm-256color",
           LINES="30", COLUMNS="100")
pid, fd = pty.fork()
if pid == 0:
    os.chdir(os.path.dirname(os.path.abspath(__file__)) or ".")
    os.execvpe(sys.executable, [sys.executable, "flowfeather.py"], env)

out = b""
def pump(t):
    global out
    end = time.time() + t
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try: out += os.read(fd, 65536)
            except OSError: break

fail = []
pump(2.0)
if not re.search(rb"FLOWFEATHER v1\.0\.0", out): fail.append("title")
os.write(fd, b"a"); pump(0.5)
os.write(fd, b"watcher\n"); pump(0.4)          # name
os.write(fd, b"i\n"); pump(0.4)                # interval trigger
os.write(fd, b"1\n"); pump(0.4)                # every 1 min
os.write(fd, b"a\n"); pump(0.4)                # append action
os.write(fd, target.encode() + b"\n"); pump(0.4)
os.write(fd, b"{name} chirped\n"); pump(0.8)
if not re.search(rb"watcher", out): fail.append("flow listed")
os.write(fd, b"A"); pump(1.0)                  # force-run all
if not os.path.exists(target): fail.append("action file")
elif open(target).read().strip() != "watcher chirped": fail.append("action line")
os.write(fd, b"l"); pump(0.8)                  # log view
if not re.search(rb"forced", out): fail.append("log view")
os.write(fd, b"q"); pump(0.5)
os.write(fd, b"q"); pump(0.8)
wp, _ = os.waitpid(pid, os.WNOHANG)
if wp == 0:
    try: os.kill(pid, 9); os.waitpid(pid, 0)
    except ProcessLookupError: pass
    fail.append("did not quit")
st = json.load(open(os.path.join(home, "flows.json")))
if st["flows"][0]["runs"] != 1: fail.append("runs persisted")
if fail:
    print("PTY FAIL:", ", ".join(fail)); sys.exit(1)
print("PTY PASS")
