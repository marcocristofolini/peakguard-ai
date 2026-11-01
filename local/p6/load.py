"""Carga sintética controlada: 20s a 1 doc/s, 90s a 12 doc/s, 20s a 1 doc/s."""
import json
import time
import urllib.request

start = time.monotonic()
for index in range(13):
    rate = 12 if 2 <= index < 11 else 1
    accepted = rejected = errors = 0
    for n in range(rate * 10):
        deadline = start + index * 10 + n / rate
        time.sleep(max(0, deadline - time.monotonic()))
        try:
            with urllib.request.urlopen(urllib.request.Request('http://documents:8080/documents', data=b'', method='POST'), timeout=2) as response:
                accepted += response.status == 202
        except urllib.error.HTTPError:
            rejected += 1
        except OSError:
            errors += 1
    print(json.dumps({'interval': index, 'target_docs_per_second': rate, 'accepted': accepted,
                      'rejected': rejected, 'errors': errors, 'elapsed_seconds': time.monotonic()-start}), flush=True)
