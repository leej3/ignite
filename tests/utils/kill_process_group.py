import os
import signal
import time

import psutil


def kill_process_group(pid_file):
    if not os.path.isfile(pid_file) or os.stat(pid_file).st_size == 0:
        print(f"File {pid_file} does not exist or is empty")
        return 1

    with open(pid_file, "r") as file:
        pgid = int(file.read().strip())

    if os.name != "posix":
        return kill_process_group_win(pid_file)

    try:
        # Check if the process group exists by sending a dummy signal (0)
        os.killpg(pgid, 0)
    except ProcessLookupError:
        print(f"Process group {pgid} does not exist")
        return 1

    # Send INT signal to the process group
    sigtype = "interrupt"
    os.killpg(pgid, signal.SIGINT)
    # Poll process existence and kill forcefully if necessary
    try:
        trying = 5
        while trying > 0:
            time.sleep(0.5)
            os.killpg(pgid, 0)
            trying -= 0.5
            if trying == 0.5 and sigtype == "interrupt":
                sigtype = "kill"
                trying = 2
                os.killpg(pgid, signal.SIGKILL)

    except ProcessLookupError:
        print(f"Process group killed successfully with {sigtype} signal")
        return 0

    print(f"Failed to kill process group {pgid}")
    return 1


def kill_process_group_win(pid_file):
    if not os.path.isfile(pid_file) or os.stat(pid_file).st_size == 0:
        print(f"File {pid_file} does not exist or is empty")
        return 1

    with open(pid_file, "r") as file:
        pid = int(file.read().strip())

    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        print(f"Process {pid} does not exist")
        return 1

    # Try to terminate the process
    try:
        proc.terminate()  # Sends SIGTERM on Unix, TerminateProcess on Windows
        proc.wait(timeout=3)  # Wait up to 3 seconds for the process to terminate
    except psutil.TimeoutExpired:
        # Process did not terminate in time, kill it
        try:
            proc.kill()
            proc.wait(timeout=1)  # Wait for the process to be killed
            print("Process killed successfully with kill signal")
            return 0
        except Exception as e:
            print(f"Failed to kill process {pid}: {e}")
            return 1
    except Exception as e:
        print(f"Error when attempting to terminate process {pid}: {e}")
        return 1

    print("Process terminated successfully with terminate signal")
    return 0
