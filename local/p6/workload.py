"""Fila sintética por pod; métricas observadas no processo, sem dados externos."""
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Workload:
    def __init__(self, capacity=1000, work_seconds=0.1):
        self.queue = queue.Queue(maxsize=capacity)
        self.work_seconds = work_seconds
        self.submitted = self.processed = self.rejected = 0
        self.wait_max = 0.0
        self.lock = threading.Lock()

    def submit(self):
        with self.lock:
            try:
                self.queue.put_nowait(time.monotonic())
                self.submitted += 1
                return True
            except queue.Full:
                self.rejected += 1
                return False

    def process_one(self):
        try:
            arrival = self.queue.get_nowait()
        except queue.Empty:
            return False
        wait = time.monotonic() - arrival
        end = time.process_time() + self.work_seconds
        while time.process_time() < end:
            pass
        with self.lock:
            self.wait_max = max(self.wait_max, wait)
            self.processed += 1
        self.queue.task_done()
        return True

    def metrics(self):
        with self.lock:
            values = {'documents_submitted_total': self.submitted, 'documents_processed_total': self.processed,
                      'documents_rejected_total': self.rejected, 'documents_backlog': self.queue.qsize(),
                      'documents_queue_wait_max_seconds': self.wait_max}
        return ''.join(f'{name} {value}\n' for name, value in values.items())


if __name__ == '__main__':
    work = Workload()
    def worker():
        while True:
            if not work.process_one():
                time.sleep(.01)
    threading.Thread(target=worker, daemon=True).start()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ('/metrics', '/health'):
                self.send_error(404)
                return
            body = work.metrics().encode() if self.path == '/metrics' else b'ok'
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4')
            self.end_headers()
            self.wfile.write(body)
        def do_POST(self):
            if self.path != '/documents':
                self.send_error(404)
                return
            self.send_response(202 if work.submit() else 429)
            self.end_headers()
        def log_message(self, *args):
            pass
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
