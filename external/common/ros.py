"""A private ROS master and the processes belonging to one reconstruction."""
import os
import signal
import socket
import subprocess
import time
import xmlrpc.client

from .process import execute


def stop(process, timeout=120):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGINT)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        raise RuntimeError("ROS process did not finish after SIGINT; output is incomplete")


class Session:
    def __init__(self, case, environment):
        self.case = case
        self.environment = dict(environment)
        self.processes = []
        self.streams = []
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.environment.update(ROS_MASTER_URI=f"http://127.0.0.1:{port}", ROS_IP="127.0.0.1",
                                ROS_HOME=str(case.output / "ros_home"), ROS_LOG_DIR=str(case.output / "ros_logs"))
        self.environment.pop("ROS_HOSTNAME", None)
        self.port = port

    def start(self, command, name):
        stream = (self.case.output / (name + ".log")).open("w")
        self.streams.append(stream)
        process = subprocess.Popen(command, env=self.environment, cwd=self.case.output,
                                   stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        self.processes.append(process)
        with (self.case.output / "commands.txt").open("a") as log:
            import shlex
            log.write(shlex.join(command) + "\n")
        return process

    def __enter__(self):
        master = self.start(["roscore", "-p", str(self.port)], "roscore")
        deadline = time.monotonic() + 30
        try:
            while time.monotonic() < deadline:
                if master.poll() is not None:
                    raise RuntimeError("roscore failed; see roscore.log")
                try:
                    probe = subprocess.run(["rosparam", "list"], env=self.environment, capture_output=True, timeout=3)
                    if probe.returncode == 0:
                        return self
                except subprocess.TimeoutExpired:
                    pass
                time.sleep(0.2)
            raise RuntimeError("ROS master did not start")
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def parameters(self, config, values):
        execute(["rosparam", "load", str(config)], self.case.output / "parameters.log", env=self.environment)
        for name, value in values.items():
            execute(["rosparam", "set", name, str(value).lower() if isinstance(value, bool) else str(value)],
                    self.case.output / "parameters.log", env=self.environment)

    def wait_node(self, name, process):
        deadline = time.monotonic() + 60
        master = xmlrpc.client.ServerProxy(self.environment["ROS_MASTER_URI"])
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"{name} stopped before replay; see node.log")
            try:
                if master.lookupNode("/rimba_reproduction", name)[0] == 1:
                    return
            except OSError:
                pass
            time.sleep(0.2)
        raise RuntimeError(f"ROS node did not register: {name}")

    def __exit__(self, exc_type, exc, traceback):
        errors = []
        for process in reversed(self.processes):
            try:
                stop(process)
            except RuntimeError as error:
                errors.append(str(error))
        for stream in self.streams:
            stream.close()
        if errors and exc_type is None:
            raise RuntimeError("; ".join(errors))
