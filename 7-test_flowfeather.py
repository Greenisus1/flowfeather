import importlib.util, json, os, tempfile, time, unittest

HOME = tempfile.mkdtemp()
os.environ["FLOWFEATHER_HOME"] = HOME
spec = importlib.util.spec_from_file_location(
    "flowfeather", os.path.join(os.path.dirname(__file__), "flowfeather.py"))
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
NOW = 1_700_000_000


def mkflow(trig, act, **kw):
    fl = f.new_flow("t", trig, act)
    fl.update(kw)
    return fl


class TestInterval(unittest.TestCase):
    def test_due_after_minutes(self):
        fl = mkflow({"type": "interval", "minutes": 5}, {}, last_run=NOW - 400)
        self.assertTrue(f.due(fl, NOW)[0])
        fl["last_run"] = NOW - 100
        self.assertFalse(f.due(fl, NOW)[0])

    def test_disabled_never_due(self):
        fl = mkflow({"type": "interval", "minutes": 1}, {},
                    last_run=0, enabled=False)
        self.assertFalse(f.due(fl, NOW)[0])


class TestFileTrigger(unittest.TestCase):
    def test_change_detection(self):
        path = os.path.join(HOME, "watched.txt")
        open(path, "w").write("one")
        fl = mkflow({"type": "file", "path": path}, {})
        self.assertFalse(f.due(fl, NOW)[0])       # baseline
        self.assertFalse(f.due(fl, NOW + 1)[0])   # unchanged
        open(path, "w").write("two")
        self.assertTrue(f.due(fl, NOW + 2)[0])    # changed
        os.remove(path)
        self.assertTrue(f.due(fl, NOW + 3)[0])    # disappeared = change


class TestRssTrigger(unittest.TestCase):
    def test_new_item(self):
        feed = os.path.join(os.path.dirname(__file__), "sample.xml")
        fl = mkflow({"type": "rss", "url": "file://" + feed}, {})
        self.assertFalse(f.due(fl, NOW)[0])       # baseline
        self.assertFalse(f.due(fl, NOW + 1)[0])   # same item
        fl["state"]["guid"] = "stale"
        self.assertTrue(f.due(fl, NOW + 2)[0])    # new guid
    def test_bad_url(self):
        fl = mkflow({"type": "rss", "url": "file:///nope.xml"}, {})
        ok, reason = f.due(fl, NOW)
        self.assertFalse(ok)
        self.assertIn("fetch error", reason)


class TestActions(unittest.TestCase):
    def test_shell(self):
        out = os.path.join(HOME, "shell-out.txt")
        fl = mkflow({}, {"type": "shell",
                         "command": f"echo hi > {out}"})
        f.act(fl)
        self.assertEqual(open(out).read().strip(), "hi")

    def test_append(self):
        path = os.path.join(HOME, "a.log")
        fl = mkflow({}, {"type": "append", "path": path,
                         "line": "{name} at {time}"})
        fl["name"] = "chirp"
        f.act(fl)
        f.act(fl)
        lines = open(path).read().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(l.startswith("chirp at ") for l in lines))

    def test_url(self):
        import http.server, threading
        srv = http.server.HTTPServer(("127.0.0.1", 0),
                                     http.server.SimpleHTTPRequestHandler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        fl = mkflow({}, {"type": "url",
                         "url": f"http://127.0.0.1:{srv.server_port}/"})
        self.assertEqual(f.act(fl), "HTTP 200")
        srv.shutdown()


class TestRunDue(unittest.TestCase):
    def test_runs_and_logs(self):
        path = os.path.join(HOME, "r.log")
        st = {"flows": [mkflow({"type": "interval", "minutes": 1},
                               {"type": "append", "path": path,
                                "line": "fired {name}"}, last_run=0)]}
        st["flows"][0]["name"] = "pinger"
        res = f.run_due(st, now=NOW)
        self.assertEqual(len(res), 1)
        self.assertEqual(st["flows"][0]["runs"], 1)
        self.assertEqual(open(path).read().strip(), "fired pinger")
        # not due again right away
        self.assertEqual(f.run_due(st, now=NOW + 10), [])
        # force runs it
        self.assertEqual(len(f.run_due(st, now=NOW + 10, force=True)), 1)
        self.assertEqual(st["flows"][0]["runs"], 2)
        self.assertTrue(st["flows"][0]["log"])

    def test_log_capped(self):
        fl = mkflow({}, {"type": "append", "path": os.path.join(HOME, "x"),
                         "line": "x"})
        fl["log"] = ["old"] * 50
        st = {"flows": [fl]}
        f.run_due(st, now=NOW, force=True)
        self.assertEqual(len(fl["log"]), f.LOG_KEEP)


if __name__ == "__main__":
    unittest.main()
