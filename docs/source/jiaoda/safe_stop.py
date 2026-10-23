#!/usr/bin/env python3
"""关机/停服务前，把中位帧连发一段时间，确保电调收到的是 1500 中位而不是信号突然消失。"""
import serial, time, sys
PORT = "/dev/ttyACM0"
try:
    p = serial.Serial()
    p.port = PORT; p.baudrate = 115200; p.timeout = 0.05; p.write_timeout = 0.2
    p.dtr = False; p.rts = False
    p.open()
    p.dtr = False; p.rts = False
    for _ in range(50):          # 2 秒，20 Hz
        p.write(b"0,0,0,0,0\n")
        p.flush()
        time.sleep(0.05)
    p.close()
    print("safe_stop: neutral sent")
except Exception as e:
    print("safe_stop: %r" % (e,), file=sys.stderr)
    sys.exit(0)
