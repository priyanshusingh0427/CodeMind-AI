"""Optional end-to-end sandbox test. Skipped unless Docker and the sandbox image are available."""

import pytest

from config import Settings
from core.sandbox import DockerSandbox

SANDBOX = DockerSandbox(Settings().with_overrides(sandbox_enabled=True, sandbox_timeout=10))
pytestmark = pytest.mark.skipif(not SANDBOX.status().available, reason="Docker sandbox image not available")


def test_tests_run_in_container():
    result = SANDBOX.run_tests("def add(a, b):\n    return a + b\n",
                               "from solution import add\n\ndef test_ok():\n    assert add(1, 2) == 3\n\n"
                               "def test_bad():\n    assert add(1, 1) == 3\n")
    assert result.executed and result.passed == 1 and result.failed == 1


def test_network_is_blocked():
    code = ("import socket\n\ndef connect():\n    socket.create_connection(('1.1.1.1', 53), timeout=2)\n")
    result = SANDBOX.run_tests(code, "import pytest\nfrom solution import connect\n\n"
                                     "def test_net():\n    with pytest.raises(OSError):\n        connect()\n")
    assert result.passed == 1


def test_filesystem_is_read_only_and_user_is_not_root():
    code = "import os\n\ndef uid():\n    return os.getuid()\n"
    tests = ("import pytest\nfrom solution import uid\n\ndef test_uid():\n    assert uid() != 0\n\n"
             "def test_ro():\n    with pytest.raises(OSError):\n        open('/work/hack.txt', 'w')\n")
    assert SANDBOX.run_tests(code, tests).passed == 2


def test_infinite_loop_times_out():
    result = SANDBOX.run_tests("def spin():\n    while True:\n        pass\n",
                               "from solution import spin\n\ndef test_spin():\n    spin()\n")
    assert not result.all_passed
