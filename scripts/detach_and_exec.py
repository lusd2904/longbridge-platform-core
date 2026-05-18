#!/usr/bin/env python3

import os
import sys


def main() -> int:
    if len(sys.argv) < 5:
        print("usage: detach_and_exec.py <workdir> <log_file> <pid_file> <cmd...>", file=sys.stderr)
        return 1

    workdir = sys.argv[1]
    log_file = sys.argv[2]
    pid_file = sys.argv[3]
    cmd = sys.argv[4:]

    first_pid = os.fork()
    if first_pid > 0:
        return 0

    os.setsid()

    second_pid = os.fork()
    if second_pid > 0:
        os._exit(0)

    os.chdir(workdir)

    read_fd = os.open(os.devnull, os.O_RDONLY)
    write_fd = os.open(log_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(read_fd, 0)
    os.dup2(write_fd, 1)
    os.dup2(write_fd, 2)

    with open(pid_file, "w", encoding="utf-8") as handler:
        handler.write(str(os.getpid()))

    os.execvp(cmd[0], cmd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
