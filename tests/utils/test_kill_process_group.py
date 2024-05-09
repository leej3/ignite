import os
import sys
import time
from unittest.mock import patch

from .kill_process_group import kill_process_group


# Attempt at creating interuptible command failed
# command = """setsid sh -c 'trap "" SIGINT SIGTERM; sleep 1000' >/dev/null 2>&1 & echo $! > .kpg_testing.pid"""
def test_kill_process_group_existing_persistent():
    pid_file = ".kpg_testing.pid"
    os.system("setsid sh -c 'sleep 1000' >/dev/null 2>&1 & echo $! > .kpg_testing.pid")
    time.sleep(1)
    message = "Process group killed successfully with kill signal"
    with patch("builtins.print") as mock_print:
        assert kill_process_group(pid_file) == 0
        mock_print.assert_called_with(message)


def test_kill_process_group_nonexistent_process():
    pid_file = ".kpg_testing.pid"
    with open(pid_file, "w") as file:
        file.write("12345")
    message = "Process group 12345 does not exist"
    with patch("builtins.print") as mock_print:
        assert kill_process_group(pid_file) == 1
        mock_print.assert_called_with(message)


def test_kill_process_group_no_file():
    pid_file = ".kpg_testing_nonexistent.pid"
    message = "File .kpg_testing_nonexistent.pid does not exist or is empty"
    with patch("builtins.print") as mock_print:
        assert kill_process_group(pid_file) == 1
        mock_print.assert_called_with(message)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        pid_file = sys.argv[1]
        result = kill_process_group(pid_file)
        sys.exit(result)
    else:
        print("Please provide the path to the PID file as a command line argument.")
        print("Example: python kill_process_group.py /path/to/pid_file")
