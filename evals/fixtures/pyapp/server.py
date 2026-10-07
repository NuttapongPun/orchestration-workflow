"""HTTP front end. Serves greetings and items, and counts requests."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import greetings
import store

request_count = 0


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global request_count
        request_count += 1
        if self.path.startswith("/greet/"):
            body = greetings.greet(self.path.rsplit("/", 1)[-1])
        elif self.path == "/items":
            body = json.dumps(store.all_items())
        elif self.path == "/stats":
            body = json.dumps({"requests": request_count})
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body.encode())


if __name__ == "__main__":
    store.load()
    ThreadingHTTPServer(("127.0.0.1", 8080), Handler).serve_forever()
