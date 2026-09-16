import time


DEFAULT_ADDRESSES = (0x19, 0x18)
EXPECTED_CHIP_ID = 0xE26A

REG_CHIP_ID_L = 0xFA
REG_P0 = 0x40
REG_P1 = 0x50
REG_P0M1 = 0x71
REG_P0M2 = 0x72
REG_P1M1 = 0x73
REG_P1M2 = 0x74
REG_ADCRL = 0x82
REG_ADCRH = 0x83
REG_ADCCON1 = 0xA1
REG_ADCCON0 = 0xA8
REG_AINDIDS0 = 0xB6

ADC_CHANNELS = {
    "reference_v": (REG_P1M1, REG_P1M2, REG_P1, 7, 0),
    "reducing_ohms": (REG_P0M1, REG_P0M2, REG_P0, 7, 2),
    "nh3_ohms": (REG_P0M1, REG_P0M2, REG_P0, 6, 3),
    "oxidising_ohms": (REG_P0M1, REG_P0M2, REG_P0, 5, 4)
}


class MICS6814:
    def __init__(self, i2c, address=None, adc_reference_v=3.3):
        self.i2c = i2c
        self.address = address or self._find_address()
        self.adc_reference_v = adc_reference_v

        chip_id = int.from_bytes(
            self.i2c.readfrom_mem(self.address, REG_CHIP_ID_L, 2),
            "little"
        )
        if chip_id != EXPECTED_CHIP_ID:
            raise RuntimeError("Unexpected MICS6814 chip ID: 0x{:04x}".format(
                chip_id
            ))

        self._configure()

    def _find_address(self):
        addresses = self.i2c.scan()
        for address in DEFAULT_ADDRESSES:
            if address in addresses:
                return address
        raise OSError("MICS6814 not found")

    def _read_register(self, register):
        return self.i2c.readfrom_mem(self.address, register, 1)[0]

    def _write_register(self, register, value):
        self.i2c.writeto_mem(self.address, register, bytes((value & 0xFF,)))

    def _change_register_bit(self, register, bit, enabled):
        value = self._read_register(register)
        if enabled:
            value |= 1 << bit
        else:
            value &= ~(1 << bit)
        self._write_register(register, value)

    def _write_port_bit(self, register, bit, enabled):
        self._write_register(register, (0x08 if enabled else 0x00) | bit)

    def _configure(self):
        self._change_register_bit(REG_ADCCON1, 0, True)

        for mode1, mode2, port, pin, _ in ADC_CHANNELS.values():
            self._change_register_bit(mode1, pin, True)
            self._change_register_bit(mode2, pin, False)
            self._write_port_bit(port, pin, False)

        self._change_register_bit(REG_P1M1, 5, False)
        self._change_register_bit(REG_P1M2, 5, True)
        self._write_port_bit(REG_P1, 5, False)

    def _read_adc(self, channel, timeout_ms=1000):
        self._write_register(REG_AINDIDS0, 1 << channel)
        control = self._read_register(REG_ADCCON0)
        control = (control & 0x30) | channel | 0x40
        self._write_register(REG_ADCCON0, control)

        started = time.ticks_ms()
        while not self._read_register(REG_ADCCON0) & 0x80:
            if time.ticks_diff(time.ticks_ms(), started) >= timeout_ms:
                raise RuntimeError("MICS6814 ADC conversion timed out")
            time.sleep_ms(1)

        raw = self.i2c.readfrom_mem(self.address, REG_ADCRL, 2)
        value = raw[0] | (raw[1] << 4)
        return (value / 4095.0) * self.adc_reference_v

    def _resistance(self, voltage):
        remaining = self.adc_reference_v - voltage
        if remaining <= 0:
            return 0
        return (voltage * 56000.0) / remaining

    def read(self):
        readings = {}
        for key, (_, _, _, _, channel) in ADC_CHANNELS.items():
            voltage = self._read_adc(channel)
            readings[key] = voltage if key == "reference_v" else self._resistance(
                voltage
            )
        return readings