"""Process-local deny guard, not a sandbox or a system network configuration."""
import sys

class OfflineViolation(BaseException):
    pass

class WriteBoundaryViolation(BaseException):
    pass

def install(write_root=None):
    from pathlib import Path
    events = []
    root = Path(write_root).resolve() if write_root else None
    def hook(event, args):
        if event.startswith('socket.') or event in (
            'subprocess.Popen','os.system','os.exec','os.posix_spawn','os.fork','os.forkpty',
        ):
            events.append({'event':event, 'category':'network_or_child_process'})
            raise OfflineViolation(f'Blocked offline operation: {event}')
        if root and event == 'open':
            name, mode, flags = args
            writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags, int) and bool(flags & 3 or flags & 0x240))
            if writing and isinstance(name, (str, bytes)):
                path = Path(name.decode() if isinstance(name, bytes) else name).resolve()
                if path != root and root not in path.parents:
                    events.append({'event':event,'category':'write_outside_run'})
                    raise WriteBoundaryViolation(f'Write outside run directory denied: {path}')
    sys.addaudithook(hook)
    return events
