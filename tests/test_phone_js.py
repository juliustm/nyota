"""Runs the browser-side checkout assertions as part of the Python suite.

The phone field and the server have to agree on what a number means, and the
donation amounts a supporter can pick have to be ones the server will accept — so
both halves are checked by one command. Skipped where Node isn't installed.
"""

import os
import shutil
import subprocess

import pytest

JS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'js')

needs_node = pytest.mark.skipif(shutil.which('node') is None, reason='Node.js not installed')


def run_node(script):
    result = subprocess.run(
        ['node', os.path.join(JS_DIR, script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@needs_node
def test_nyota_phone_helper():
    run_node('phone.test.js')


@needs_node
def test_checkout_components():
    run_node('checkout.test.js')
