"""Keep conversions from slowing the laptop down.

- Hard CPU cap: the converter process and every engine it starts (e.g. Microsoft Office)
  are placed in a Windows job object limited to a fixed share of total CPU
  (default 25%). Windows enforces this; it can't be exceeded, however heavy the
  file is. Conversions take longer, but the laptop stays cool and responsive.
- The same job object kills any engine still running if the converter exits
  (e.g. when you cancel), so nothing is left running in the background.
- Idle priority + EcoQoS (Windows "efficiency mode"): within that cap the work
  only uses CPU time nothing else wants, on the efficiency cores.
- Thread caps: encoders use 2 threads instead of every core.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

IDLE_PRIORITY_CLASS = 0x40
ProcessPowerThrottling = 4
PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
JobObjectExtendedLimitInformation = 9
JobObjectCpuRateControlInformation = 15
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_CPU_RATE_CONTROL_ENABLE = 0x1
JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP = 0x4

DEFAULT_CPU_PERCENT = 25

_job = None  # keep the job handle open for the life of the process


class _PowerThrottling(ctypes.Structure):
    _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]


class _IoCounters(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimits), ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class _CpuRate(ctypes.Structure):
    _fields_ = [("ControlFlags", wintypes.DWORD), ("CpuRate", wintypes.DWORD)]


def engine_threads() -> int:
    env = os.environ.get("TAPSHIFT_THREADS")
    if env and env.isdigit():
        return max(1, int(env))
    return 2


def _k32():
    k = ctypes.windll.kernel32
    k.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k.SetProcessInformation.restype = wintypes.BOOL
    k.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k.SetInformationJobObject.restype = wintypes.BOOL
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k.AssignProcessToJobObject.restype = wintypes.BOOL
    k.GetCurrentProcess.restype = wintypes.HANDLE
    return k


def throttle(handle=None, eco: bool = True) -> None:
    """Idle priority (+ EcoQoS) for a process handle; default: this process."""
    if os.name != "nt":
        return
    k = _k32()
    h = wintypes.HANDLE(int(handle)) if handle is not None else k.GetCurrentProcess()
    try:
        k.SetPriorityClass(h, IDLE_PRIORITY_CLASS)
    except Exception:
        pass
    if eco:
        try:
            st = _PowerThrottling(1, PROCESS_POWER_THROTTLING_EXECUTION_SPEED, PROCESS_POWER_THROTTLING_EXECUTION_SPEED)
            k.SetProcessInformation(h, ProcessPowerThrottling, ctypes.byref(st), ctypes.sizeof(st))
        except Exception:
            pass


def cap_this_process(cpu_percent: int = DEFAULT_CPU_PERCENT) -> bool:
    """Put this process (and all future child processes) under a hard CPU cap.
    Returns True if the cap is active."""
    global _job
    if os.name != "nt":
        return False
    k = _k32()
    job = k.CreateJobObjectW(None, None)
    if not job:
        return False
    ext = _ExtendedLimits()
    ext.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    k.SetInformationJobObject(job, JobObjectExtendedLimitInformation, ctypes.byref(ext), ctypes.sizeof(ext))
    pct = max(5, min(100, int(cpu_percent)))
    rate = _CpuRate(JOB_OBJECT_CPU_RATE_CONTROL_ENABLE | JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP, pct * 100)
    capped = bool(k.SetInformationJobObject(job, JobObjectCpuRateControlInformation, ctypes.byref(rate), ctypes.sizeof(rate)))
    if not k.AssignProcessToJobObject(job, k.GetCurrentProcess()):
        return False
    _job = job
    throttle()
    return capped
