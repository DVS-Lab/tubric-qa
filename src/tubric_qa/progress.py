"""Flushed CLI progress, including a heartbeat during blocking library calls."""

import sys
import threading
import time


class Progress:
    def __init__(self, enabled=True, interval=30):
        self.enabled = enabled
        self.interval = interval
        self.started = time.monotonic()
        self.stage = "Starting report"
        self.stop = threading.Event()
        self.lock = threading.Lock()

    def __call__(self, message):
        if self.enabled:
            with self.lock:
                self.stage = message
                self._write(message)

    def _write(self, message):
        elapsed = time.monotonic() - self.started
        print(f"[{elapsed:7.1f}s] {message}", file=sys.stderr, flush=True)

    def _heartbeat(self):
        while not self.stop.wait(self.interval):
            with self.lock:
                self._write(f"Still working: {self.stage}")

    def __enter__(self):
        if self.enabled:
            self.thread = threading.Thread(target=self._heartbeat, daemon=True)
            self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        if self.enabled:
            self.thread.join()
