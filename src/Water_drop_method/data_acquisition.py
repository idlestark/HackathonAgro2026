class NIUSB6009:
    """
    Class designed for data acquisition of a photodiode connected to a NI-USB6009.
    """

    def __init__(self, device_name="Dev1", channel="ai0", sample_rate=1000, samples_per_channel=10000):
        try:
            import nidaqmx
        except ImportError as exc:
            raise ImportError(
                "nidaqmx is required to use NIUSB6009. Install it in the runtime environment."
            ) from exc

        self._nidaqmx = nidaqmx
        self.device_name = device_name
        self.channel = channel
        self.sample_rate = sample_rate
        self.samples_per_channel = samples_per_channel

        self.task = self._nidaqmx.Task()
        self.task.ai_channels.add_ai_voltage_chan(f"{self.device_name}/{self.channel}")
        self.task.timing.cfg_samp_clk_timing(self.sample_rate, samps_per_chan=self.samples_per_channel)

    def start(self):
        """Start the task for data acquisition."""
        self.task.start()

    def measure(self):
        """Read a single sample from the task."""
        return self.task.read()

    def stop(self):
        """Stop the task."""
        self.task.stop()

    def close(self):
        """Close the task."""
        self.task.close()

import time


class ArduinoUno:
    """
    Class designed for data acquisition using an Arduino Uno connected via serial port.
    """

    def __init__(self, port="COM3", baudrate=9600, channel="A0", timeout=1):
        try:
            import serial
        except ImportError as exc:
            raise ImportError(
                "pyserial is required to use ArduinoUno. Install it in the runtime environment."
            ) from exc

        self._serial = serial
        self.port = port
        self.baudrate = baudrate
        self.channel = channel
        self.timeout = timeout
        self.connection = None

    def start(self):
        """Open the serial connection and wait for the microcontroller initialization."""
        if self.connection is None or not self.connection.is_open:
            self.connection = self._serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            time.sleep(2)  # Required pause: opening the port resets the Arduino

    def measure(self, convert_to_volts=True):
        """
        Read a single sample from the serial port.
        Converts the 10-bit ADC reading (0-1023) to Volts (0-5V) if convert_to_volts is True.
        """
        if self.connection and self.connection.is_open:
            line = self.connection.readline().decode('utf-8', errors='ignore').strip()

            try:
                raw_val = float(line)
                if convert_to_volts:
                    return (raw_val / 1023.0) * 5.0
                return raw_val
            except ValueError:
                return None
        return None

    def stop(self):
        """Stop transmission or clear the buffer."""
        if self.connection and self.connection.is_open:
            self.connection.reset_input_buffer()

    def close(self):
        """Close the serial port connection."""
        if self.connection and self.connection.is_open:
            self.connection.close()
            self.connection = None