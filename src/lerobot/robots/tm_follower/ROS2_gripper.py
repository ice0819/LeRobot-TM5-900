#!/usr/bin/env python3
import time
import math
import minimalmodbus as mm


class RobotiqGripper(mm.Instrument):
    """
    Robotiq gripper helper based on MinimalModbus.

    Notes
    -----
    - Uses Modbus RTU
    - Typical Robotiq register block starts at 1000(write) and 2000(read)
    - This version avoids reading registers inside __init__ to prevent
      startup no-response issues before activation is complete.
    """

    def __init__(self, portname: str, slaveaddress: int = 9):
        super().__init__(portname, slaveaddress)

        self.debug = False
        self.mode = mm.MODE_RTU
        self.processing = False
        self.timeOut = 10

        # Explicit serial settings
        self.serial.baudrate = 115200
        self.serial.bytesize = 8
        self.serial.parity = "N"
        self.serial.stopbits = 1
        self.serial.timeout = 0.05

        # Stability options
        self.clear_buffers_before_each_transaction = True
        self.close_port_after_each_call = False

        self.registerDic = {}
        self._buildRegisterDic()

        self.paramDic = {}

        # calibration-related values
        self.closemm = None
        self.closebit = None
        self.openmm = None
        self.openbit = None
        self._aCoef = None
        self._bCoef = None

    def _buildRegisterDic(self):
        self.registerDic["ACTION_REQUEST"] = 1000
        self.registerDic["POSITION_REQUEST"] = 1001
        self.registerDic["SPEED"] = 1002
        self.registerDic["FORCE"] = 1003

        self.registerDic["GRIPPER_STATUS"] = 2000
        self.registerDic["FAULT_STATUS"] = 2002
        self.registerDic["POS_REQUEST_ECHO"] = 2003
        self.registerDic["POSITION"] = 2004
        self.registerDic["CURRENT"] = 2005

    def _int_to_bin8(self, x: int) -> str:
        return format(int(x) & 0xFF, "08b")

    def _int_to_bin16(self, x: int) -> str:
        return format(int(x) & 0xFFFF, "016b")

    def readAll(self):
        self.paramDic.clear()

        try:
            # Robotiq 這裡實際只需要 3 個 register = 6 bytes
            regs = self.read_registers(self.registerDic["GRIPPER_STATUS"], 3)
        except Exception as e:
            # print(f"[RobotiqGripper] readAll failed: {e}")
            return self.paramDic

        # print(f"[RobotiqGripper] raw regs = {regs}")

        reg0, reg1, reg2 = regs

        # 每個 register 拆成高/低 byte
        reg0_hi = (reg0 >> 8) & 0xFF
        reg0_lo = reg0 & 0xFF
        reg1_hi = (reg1 >> 8) & 0xFF
        reg1_lo = reg1 & 0xFF
        reg2_hi = (reg2 >> 8) & 0xFF
        reg2_lo = reg2 & 0xFF

        # print(f"[RobotiqGripper] reg2000 hi=0x{reg0_hi:02X} lo=0x{reg0_lo:02X}")
        # print(f"[RobotiqGripper] reg2001 hi=0x{reg1_hi:02X} lo=0x{reg1_lo:02X}")
        # print(f"[RobotiqGripper] reg2002 hi=0x{reg2_hi:02X} lo=0x{reg2_lo:02X}")

        # status byte = reg2000 高位
        status = reg0_hi

        self.paramDic["gOBJ"] = (status >> 6) & 0x03
        self.paramDic["gSTA"] = (status >> 4) & 0x03
        self.paramDic["gGTO"] = (status >> 3) & 0x01
        self.paramDic["gACT"] = (status >> 0) & 0x01

        # fault byte = reg2000 低位
        self.paramDic["gFLT"] = reg0_lo

        # request echo = reg2001 低位
        self.paramDic["gPR"] = reg1_lo

        # actual position = reg2002 高位
        self.paramDic["gPO"] = reg2_hi

        # current = reg2002 低位
        self.paramDic["gCU"] = reg2_lo

        return self.paramDic

    def reset(self):
        """
        Reset gripper activation bit.
        """
        # ACTION_REQUEST upper byte: rARD/rATR/rGTO/rMOD/rACT
        # Here we clear activation.
        self.write_register(self.registerDic["ACTION_REQUEST"], 0, functioncode=16)

    def activate(self):
        """
        Activate gripper.
        """
        # Common activation request byte: 0x01 or 0x09 depending on mode bits.
        # 0x01 usually sufficient for basic activation.
        self.write_register(self.registerDic["ACTION_REQUEST"], 0x0100, functioncode=16)

    def resetActivate(self):
        """
        Recommended startup sequence.
        """
        self.reset()
        time.sleep(0.2)
        self.activate()
        time.sleep(0.5)
        self.readAll()

    def autoRelease(self):
        """
        Optional emergency auto-release.
        """
        # Typical auto-release request, may vary by gripper FW.
        self.write_register(self.registerDic["ACTION_REQUEST"], 0x0D00, functioncode=16)

    def goto(self, position: int, speed: int = 128, force: int = 128):
        """
        Robotiq register packing:
        reg1000 = ACTION << 8 | OPTIONS
        reg1001 = SPEED  << 8 | POSITION
        reg1002 = FORCE  << 8 | 0x00
        """
        position = int(max(0, min(255, position)))
        speed = int(max(0, min(255, speed)))
        force = int(max(0, min(255, force)))

        action = 0x09  # activate + go to
        options = 0x00

        reg1000 = (action << 8) | options
        reg1001 = (speed << 8) | position
        reg1002 = (force << 8) | 0x00

        # print(
        #     f"[RobotiqGripper] goto pos={position} speed={speed} force={force} "
        #     f"regs={[hex(reg1000), hex(reg1001), hex(reg1002)]}"
        # )

        self.write_registers(
            self.registerDic["ACTION_REQUEST"],
            [reg1000, reg1001, reg1002]
        )

        time.sleep(0.01)
        self.readAll()

    def goTo(self, position: int, speed: int = 128, force: int = 128):
        self.goto(position, speed, force)

    def goTomm(self, position: int, speed: int = 128, force: int = 128):
        """
        Kept for compatibility with your current calling code.
        Here it behaves the same as goto() and accepts 0~255.
        """
        self.goto(position, speed, force)

    def getPosition(self):
        """
        Return actual position 0~255.
        """
        self.readAll()
        return self.paramDic.get("gPO", 0)

    def getRequestedPosition(self):
        self.readAll()
        return self.paramDic.get("gPR", 0)

    def getCurrent(self):
        self.readAll()
        return self.paramDic.get("gCU", 0)

    def isActivated(self):
        self.readAll()
        return self.paramDic.get("gACT", 0) == 1

    def isMoving(self):
        self.readAll()
        # gOBJ meanings vary by FW, but non-terminal states often indicate motion.
        gobj = self.paramDic.get("gOBJ", 0)
        return gobj in (0, 1)

    def isOpen(self):
        return self.getPosition() <= 5

    def isClosed(self):
        return self.getPosition() >= 250

    def wait_until_stopped(self, timeout: float = 5.0, poll_dt: float = 0.05):
        t0 = time.time()
        while time.time() - t0 < timeout:
            self.readAll()
            if not self.isMoving():
                return True
            time.sleep(poll_dt)
        return False

    def calibrate(self, openmm: float, closemm: float, openbit: int = 0, closebit: int = 255):
        """
        Optional linear calibration helper.
        """
        self.openmm = float(openmm)
        self.closemm = float(closemm)
        self.openbit = int(openbit)
        self.closebit = int(closebit)

        if self.closebit == self.openbit:
            raise ValueError("openbit and closebit cannot be equal.")

        self._aCoef = (self.closemm - self.openmm) / (self.closebit - self.openbit)
        self._bCoef = self.openmm - self._aCoef * self.openbit

    def bitTomm(self, bitval: int) -> float:
        if self._aCoef is None or self._bCoef is None:
            raise RuntimeError("Call calibrate() before bitTomm().")
        return self._aCoef * bitval + self._bCoef

    def mmTobit(self, mmval: float) -> int:
        if self._aCoef is None or self._bCoef is None:
            raise RuntimeError("Call calibrate() before mmTobit().")
        if abs(self._aCoef) < 1e-12:
            raise RuntimeError("Calibration slope is zero.")
        bit = int(round((mmval - self._bCoef) / self._aCoef))
        return max(0, min(255, bit))