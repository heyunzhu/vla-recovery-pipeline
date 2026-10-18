"""Process-local vision models behind a synchronous JSON-lines protocol."""
import atexit
import json
import subprocess
import time
import queue
import threading


PREFIX = 'RGBD_REPLY '


class JSONLineProcess:
    def __init__(self, argv, *, env, log_path, timeout=180, cwd=None):
        self.timeout = timeout
        self.log = open(log_path, 'w')
        self.process = subprocess.Popen(argv, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=self.log, text=True, bufsize=1, cwd=cwd)
        self.lines=queue.Queue()
        def collect():
            for line in self.process.stdout:self.lines.put(line)
            self.lines.put(None)
        threading.Thread(target=collect,daemon=True).start()
        atexit.register(self.close)
        self.ready = self._read()
        if not self.ready.get('ready'):
            self.close()
            raise RuntimeError(f'vision worker failed: {self.ready}')

    def _read(self):
        deadline = time.monotonic()+self.timeout
        while time.monotonic()<deadline:
            try:line=self.lines.get(timeout=max(0,deadline-time.monotonic()))
            except queue.Empty:break
            if line is None:raise RuntimeError('vision worker exited; inspect worker log')
            if line.startswith(PREFIX):return json.loads(line[len(PREFIX):])
        raise TimeoutError('vision worker response timed out')

    def request(self, payload):
        self.process.stdin.write(json.dumps(payload)+'\n')
        self.process.stdin.flush()
        reply = self._read()
        if 'error' in reply:
            raise RuntimeError(reply['error'])
        return reply

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.write(json.dumps(dict(shutdown=True))+'\n')
                self.process.stdin.flush()
            except (OSError,ValueError):self.process.terminate()
            try:self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill();self.process.wait()
        self.log.close()


def reply(payload):
    print(PREFIX+json.dumps(payload), flush=True)
