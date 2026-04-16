#!/usr/bin/env python3
"""
Standalone HTTP mock servers for E2E testing.

Wraps the existing mock servers from backend/src/tests/e2e/mocks/
as real HTTP listeners on separate ports.

Usage:
    python tests/e2e/scripts/mock-server-runner.py

Ports:
    9001 - Mock Shopify API
    9002 - Mock Airbyte API
    9003 - Mock OpenRouter API

Environment:
    MOCK_SHOPIFY_PORT=9001
    MOCK_AIRBYTE_PORT=9002
    MOCK_OPENROUTER_PORT=9003
"""

import os
import sys
import json
import signal
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add backend to path so we can import mock servers
BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'backend')
sys.path.insert(0, BACKEND_DIR)


class HealthCheckMixin:
    """Adds /health endpoint to mock servers."""

    def check_health(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode())
            return True
        return False


class MockShopifyHandler(BaseHTTPRequestHandler, HealthCheckMixin):
    """Mock Shopify API server."""

    def do_GET(self):
        if self.check_health():
            return

        # Default: return mock Shopify response
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({
            'shop': {
                'id': 1,
                'name': 'E2E Test Store',
                'domain': 'e2e-test.myshopify.com',
                'plan_name': 'partner_test',
            }
        }).encode())

    def do_POST(self):
        if self.check_health():
            return

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else b''

        # Mock billing endpoints
        if '/recurring_application_charges' in self.path:
            self.send_response(201)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'recurring_application_charge': {
                    'id': 12345,
                    'status': 'pending',
                    'confirmation_url': 'https://e2e-test.myshopify.com/admin/charges/confirm',
                }
            }).encode())
            return

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'ok': True}).encode())

    def log_message(self, format, *args):
        pass  # Suppress request logging


class MockAirbyteHandler(BaseHTTPRequestHandler, HealthCheckMixin):
    """Mock Airbyte API server."""

    def do_GET(self):
        if self.check_health():
            return

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({
            'connections': [],
            'status': 'active',
        }).encode())

    def do_POST(self):
        if self.check_health():
            return

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else b''

        # Mock connection creation
        if '/connections' in self.path:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'connectionId': 'mock-connection-id',
                'status': 'active',
                'sourceId': 'mock-source-id',
                'destinationId': 'mock-destination-id',
            }).encode())
            return

        # Mock sync trigger
        if '/jobs' in self.path:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'job': {
                    'id': 99999,
                    'status': 'running',
                    'configType': 'sync',
                }
            }).encode())
            return

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'ok': True}).encode())

    def log_message(self, format, *args):
        pass


class MockOpenRouterHandler(BaseHTTPRequestHandler, HealthCheckMixin):
    """Mock OpenRouter (LLM) API server."""

    def do_GET(self):
        if self.check_health():
            return

        # Model list
        if '/models' in self.path:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'data': [
                    {'id': 'mock-model', 'name': 'Mock Model', 'context_length': 4096},
                ]
            }).encode())
            return

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({}).encode())

    def do_POST(self):
        if self.check_health():
            return

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else b''

        # Chat completions
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({
            'id': 'mock-completion-1',
            'choices': [{
                'index': 0,
                'message': {
                    'role': 'assistant',
                    'content': 'This is a mock AI response for E2E testing. Based on your data, revenue is trending up 12% MoM.',
                },
                'finish_reason': 'stop',
            }],
            'model': 'mock-model',
            'usage': {'prompt_tokens': 50, 'completion_tokens': 30, 'total_tokens': 80},
        }).encode())

    def log_message(self, format, *args):
        pass


def start_server(handler_class, port, name):
    """Start an HTTP server in a background thread."""
    server = HTTPServer(('0.0.0.0', port), handler_class)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f'  {name} listening on port {port}')
    return server


def main():
    shopify_port = int(os.getenv('MOCK_SHOPIFY_PORT', '9001'))
    airbyte_port = int(os.getenv('MOCK_AIRBYTE_PORT', '9002'))
    openrouter_port = int(os.getenv('MOCK_OPENROUTER_PORT', '9003'))

    print('Starting E2E mock servers...')
    servers = [
        start_server(MockShopifyHandler, shopify_port, 'Mock Shopify'),
        start_server(MockAirbyteHandler, airbyte_port, 'Mock Airbyte'),
        start_server(MockOpenRouterHandler, openrouter_port, 'Mock OpenRouter'),
    ]
    print('All mock servers running. Press Ctrl+C to stop.\n')

    # Wait for shutdown signal
    shutdown_event = threading.Event()

    def signal_handler(sig, frame):
        print('\nShutting down mock servers...')
        for server in servers:
            server.shutdown()
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    shutdown_event.wait()


if __name__ == '__main__':
    main()
