"""Exercise real HTTP handlers using memory streams, without opening TCP ports."""
import io
import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch


class MemoryConnection:
    def __init__(self, data):
        self.input = io.BytesIO(data)
        self.output = io.BytesIO()

    def makefile(self, mode, *args):
        return self.input

    def sendall(self, data):
        self.output.write(data)


def request(console, path, data=None, headers=None, remote='127.0.0.1', method=None):
    body = b'' if data is None else json.dumps(data).encode()
    values = {'Host': '127.0.0.1:8001', 'Content-Type': 'application/json', 'Content-Length': str(len(body)),
              **(headers or {})}
    verb = method or ('GET' if data is None else 'POST')
    raw = (verb + ' ' + path + ' HTTP/1.0\r\n' +
           ''.join(k + ': ' + str(v) + '\r\n' for k, v in values.items()) + '\r\n').encode() + body
    connection = MemoryConnection(raw)
    console.WebConsoleHandler(connection, (remote, 12345), SimpleNamespace(server_port=8001))
    head, result = connection.output.getvalue().split(b'\r\n\r\n', 1)
    lines = head.decode('iso-8859-1').split('\r\n')
    response_headers = dict(line.split(': ', 1) for line in lines[1:] if ': ' in line)
    return int(lines[0].split()[1]), result, response_headers


class MockDeviceCase(TestCase):
    def setUp(self):
        import web_console
        for item in (patch.object(web_console, 'connection', return_value=('fake-key', 'fake-hosts', 'root@192.0.2.50')),
                     patch.object(web_console, 'ssh_options', return_value=[])):
            item.start()
            self.addCleanup(item.stop)
