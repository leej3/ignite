import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from .kill_process_group import kill_process_group


# Attempt at creating interuptible command failed
# command = """setsid sh -c 'trap "" SIGINT SIGTERM; sleep 1000' >/dev/null 2>&1 & echo $! > .kpg_testing.pid"""
@pytest.mark.skipif(os.name != "posix", reason="Test only available on Unix-like systems")
def test_kill_process_group_existing_persistent():

    pid_file = ".kpg_testing.pid"
    os.system("setsid sh -c 'sleep 1000' >/dev/null 2>&1 & echo $! > .kpg_testing.pid")
    time.sleep(1)
    message = "Process group killed successfully with kill signal"
    with patch("builtins.print") as mock_print:
        assert kill_process_group(pid_file) == 0
        mock_print.assert_called_with(message)
    with pytest.raises(ProcessLookupError):
        os.killpg(int(Path(pid_file).read_text()), 0)


def test_kill_process_group_nonexistent_process():
    pid_file = ".kpg_testing.pid"
    with open(pid_file, "w") as file:
        file.write("12345")
    if os.name == "posix":
        message = "Process group 12345 does not exist"
    else:
        message = "Process 12345 does not exist"
    with patch("builtins.print") as mock_print:
        assert kill_process_group(pid_file) == 1
        mock_print.assert_called_with(message)


def test_kill_process_group_no_file():
    pid_file = ".kpg_testing_nonexistent.pid"
    message = "File .kpg_testing_nonexistent.pid does not exist or is empty"
    with patch("builtins.print") as mock_print:
        assert kill_process_group(pid_file) == 1
        mock_print.assert_called_with(message)


@pytest.mark.skipif(os.name != "posix", reason="Test only available on Unix-like systems")
def test_is_script():
    epath = Path(__file__).resolve().with_name("kill_process_group.py")
    pid_file = ".kpg_testing.pid"
    os.system("setsid sh -c 'sleep 1000' >/dev/null 2>&1 & echo $! > .kpg_testing.pid")
    time.sleep(1)
    os.system(f"python {epath} {pid_file}")
    with pytest.raises(ProcessLookupError):
        os.killpg(int(Path(pid_file).read_text()), 0)
