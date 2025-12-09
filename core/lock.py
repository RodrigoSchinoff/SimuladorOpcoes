# core/lock.py
import threading
import time

# locks em memória por chave
_locks = {}
_lock_global = threading.Lock()

def acquire_lock(key, timeout=30):
    """
    Obtém um lock por chave, evitando stampede.
    Retorna True se lock foi obtido, False caso timeout.
    """
    end = time.time() + timeout

    while time.time() < end:
        with _lock_global:
            if key not in _locks:
                _locks[key] = threading.Lock()

        if _locks[key].acquire(blocking=False):
            return True

        time.sleep(0.05)

    return False


def release_lock(key):
    """Libera o lock da chave, caso exista."""
    with _lock_global:
        lk = _locks.get(key)
    if lk:
        try:
            lk.release()
        except:
            pass
