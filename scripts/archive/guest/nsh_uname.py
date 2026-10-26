import serial, time
ser = serial.Serial("/dev/ttyACM0", 1000000, timeout=0.4)
ser.dtr = True
ser.rts = False
time.sleep(0.15)
ser.reset_input_buffer()
ser.write(b"\r\nuname -a\r\nls /dev\r\n")
time.sleep(1.0)
data = ser.read(4096)
ser.close()
print(data.decode("latin1", "replace"))
