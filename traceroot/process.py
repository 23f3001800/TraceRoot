from dataclasses import dataclass
import os
import signal
import subprocess
from threading import Thread
from time import monotonic

@dataclass
class ProcessResult:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    duration_ms: float
    timed_out: bool
    stdout_truncated: bool
    stderr_truncated: bool

def run_process(argv: list[str], timeout: int, input_bytes: bytes | None = None,
                limit: int = 65536) -> ProcessResult:
    """Trusted runtime primitive; never exposed as an agent tool."""
    start = monotonic()
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, shell=False, start_new_session=True)
    buffers = [bytearray(), bytearray()]
    truncated = [False, False]
    def drain(stream, index):
        while block := stream.read(8192):
            remaining = limit - len(buffers[index])
            buffers[index].extend(block[:max(0, remaining)])
            truncated[index] |= len(block) > remaining
        stream.close()
    def write_input():
        try:
            if input_bytes:
                proc.stdin.write(input_bytes)
        except (BrokenPipeError, OSError):
            pass
        finally:
            proc.stdin.close()
    workers = [Thread(target=drain, args=(proc.stdout, 0), daemon=True),
               Thread(target=drain, args=(proc.stderr, 1), daemon=True),
               Thread(target=write_input, daemon=True)]
    for worker in workers:
        worker.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    except BaseException:
        # A global investigation deadline must also terminate the Docker CLI process.
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
        for worker in workers:
            worker.join(timeout=1)
        raise
    for worker in workers:
        worker.join(timeout=2)
    return ProcessResult(proc.returncode, bytes(buffers[0]), bytes(buffers[1]),
                         round((monotonic() - start) * 1000, 2), timed_out, *truncated)
