import os, sys, time, threading

PAN_MIN, PAN_MAX = -90, 90
TILT_MIN, TILT_MAX = -45, 45
BAUD = 115200


def _clamp(v, lo, hi):
    try:
        v = float(v)
    except Exception:
        v = 0.0
    if v < lo:
        v = lo
    if v > hi:
        v = hi
    return int(round(v))


class Gimbal:
    def __init__(self, port=None, baud=BAUD, fmt="P{p}T{t}\n"):
        self.port = port if port is not None else os.environ.get("GIMBAL_PORT", "")
        self.baud = baud
        self.fmt = fmt
        self.p = 0
        self.t = 0
        self._lock = threading.Lock()
        self._ser = None
        self._open()

    def _open(self):
        if not self.port:
            return
        try:
            import serial
            self._ser = serial.Serial(self.port, self.baud, timeout=0.1)
            time.sleep(0.2)
        except Exception as e:
            sys.stderr.write("gimbal open fail: %r\n" % e)
            self._ser = None

    def _write(self, p, t):
        if self._ser is None:
            return False
        try:
            self._ser.write(self.fmt.format(p=p, t=t).encode())
            return True
        except Exception as e:
            sys.stderr.write("gimbal write fail: %r\n" % e)
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
            self._open()
            return False

    def set(self, p, t):
        p = _clamp(p, PAN_MIN, PAN_MAX)
        t = _clamp(t, TILT_MIN, TILT_MAX)
        with self._lock:
            self.p, self.t = p, t
            ok = self._write(p, t)
        return {"p": p, "t": t, "sent": ok}

    def center(self):
        return self.set(0, 0)

    def get(self):
        return {"p": self.p, "t": self.t, "port": self.port,
                "connected": self._ser is not None}

    def close(self):
        with self._lock:
            if self._ser is not None:
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None


class GimbalPCA9685:
    def __init__(self, pan_ch=0, tilt_ch=1, addr=0x40, freq=50,
                 us_min=500, us_max=2500):
        self.enabled = False
        self.pan_ch = pan_ch
        self.tilt_ch = tilt_ch
        self.freq = freq
        self.us_min = us_min
        self.us_max = us_max
        self.p = 0
        self.t = 0
        self._pca = None
        try:
            import smbus  # noqa: F401
            self._init_pca(addr)
            self.enabled = True
        except Exception as e:
            sys.stderr.write("PCA9685 disabled (%r)\n" % e)
            self.enabled = False

    def _init_pca(self, addr):
        import smbus
        self._bus = smbus.SMBus(1)
        self._addr = addr
        self._bus.write_byte_data(addr, 0x00, 0x10)
        prescale = int(round(25000000.0 / (4096 * self.freq)) - 1)
        self._bus.write_byte_data(addr, 0xFE, prescale)
        self._bus.write_byte_data(addr, 0x00, 0x20)
        time.sleep(0.005)

    def _us(self, ch, us):
        ticks = int(us * 4096 * self.freq / 1000000.0)
        base = 0x06 + 4 * ch
        self._bus.write_byte_data(self._addr, base, 0)
        self._bus.write_byte_data(self._addr, base + 1, 0)
        self._bus.write_byte_data(self._addr, base + 2, ticks & 0xFF)
        self._bus.write_byte_data(self._addr, base + 3, ticks >> 8)

    def _deg_us(self, deg, lo, hi):
        span = hi - lo
        frac = (deg - lo) / float(span)
        return self.us_min + frac * (self.us_max - self.us_min)

    def set(self, p, t):
        p = _clamp(p, PAN_MIN, PAN_MAX)
        t = _clamp(t, TILT_MIN, TILT_MAX)
        self.p, self.t = p, t
        if self.enabled:
            try:
                self._us(self.pan_ch, self._deg_us(p, PAN_MIN, PAN_MAX))
                self._us(self.tilt_ch, self._deg_us(t, TILT_MIN, TILT_MAX))
                return {"p": p, "t": t, "sent": True}
            except Exception as e:
                sys.stderr.write("PCA9685 write fail: %r\n" % e)
        return {"p": p, "t": t, "sent": False}

    def center(self):
        return self.set(0, 0)

    def get(self):
        return {"p": self.p, "t": self.t, "connected": self.enabled}

    def close(self):
        pass


if __name__ == "__main__":
    g = Gimbal()
    print("open:", g.get())
    print("set 30,-10:", g.set(30, -10))
    print("clamp 200,200:", g.set(200, 200))
    print("center:", g.center())
    g.close()
