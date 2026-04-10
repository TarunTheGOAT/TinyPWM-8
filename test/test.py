import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

# -------------------------------------------------
# TIMING CONSTANT
# Increase phases so the 2-stage synchronizer in
# the RTL has plenty of time to see each transition
# -------------------------------------------------
PHASE = 20  # clock cycles per I2C half-period


# -------------------------------------------------
# SAFE READ OF SLAVE SDA (handles X/Z, packed bus)
# -------------------------------------------------
def get_slave_sda(dut):
    val = dut.uo_out.value
    if val.is_resolvable:
        return (int(val) >> 1) & 1
    else:
        return 1   # Treat X/Z as released (HIGH)


# -------------------------------------------------
# SAFE READ OF PWM OUTPUT BIT 0
# -------------------------------------------------
def get_pwm_out(dut):
    val = dut.uo_out.value
    if val.is_resolvable:
        return int(val) & 1
    else:
        return 0


# -------------------------------------------------
# I2C WIRED-AND LINE (OPEN-DRAIN)
# -------------------------------------------------
def set_i2c_lines(dut, scl, master_sda):
    slave_sda = get_slave_sda(dut)
    sda_line = master_sda & slave_sda
    dut.ui_in.value = (sda_line << 1) | scl


# -------------------------------------------------
# WAIT FOR PWM RISING EDGE (uo_out[0]: 0 -> 1)
# Cannot use RisingEdge on packed bus bit in GL sim
# -------------------------------------------------
async def wait_pwm_rise(dut):
    # Wait until PWM output is LOW
    while True:
        await RisingEdge(dut.clk)
        if get_pwm_out(dut) == 0:
            break
    # Then wait until PWM output goes HIGH
    while True:
        await RisingEdge(dut.clk)
        if get_pwm_out(dut) == 1:
            break


# -------------------------------------------------
# CLOCK PULSE
# SCL: LOW -> HIGH -> LOW with SDA held stable
# -------------------------------------------------
async def i2c_clock_pulse(dut, sda):
    set_i2c_lines(dut, 0, sda)
    await ClockCycles(dut.clk, PHASE)

    set_i2c_lines(dut, 1, sda)
    await ClockCycles(dut.clk, PHASE)

    set_i2c_lines(dut, 0, sda)
    await ClockCycles(dut.clk, PHASE)


# -------------------------------------------------
# ACK PHASE
# -------------------------------------------------
async def i2c_ack_phase(dut):
    # Master releases SDA (SCL still low)
    set_i2c_lines(dut, 0, 1)
    await ClockCycles(dut.clk, PHASE)

    # SCL HIGH -> slave should pull SDA low (ACK)
    set_i2c_lines(dut, 1, 1)
    await ClockCycles(dut.clk, PHASE)

    slave_sda = get_slave_sda(dut)
    dut._log.info(f"ACK bit = {slave_sda} (0=ACK, 1=NACK)")
    assert slave_sda == 0, "Expected ACK (SDA=0) but got NACK (SDA=1)"

    # SCL LOW to finish ACK clock
    set_i2c_lines(dut, 0, 1)
    await ClockCycles(dut.clk, PHASE)


# -------------------------------------------------
# I2C WRITE
# Correct START: SCL high and stable BEFORE SDA falls
# -------------------------------------------------
async def i2c_write(dut, address, reg_addr, value):

    # --- IDLE: both lines high, let synchronizers settle ---
    set_i2c_lines(dut, 1, 1)
    await ClockCycles(dut.clk, PHASE * 2)

    # --- START CONDITION ---
    # Step 1: SCL high, SDA high (already idle, but be explicit)
    set_i2c_lines(dut, 1, 1)
    await ClockCycles(dut.clk, PHASE)

    # Step 2: SDA falls while SCL is HIGH -> this is the START
    set_i2c_lines(dut, 1, 0)
    await ClockCycles(dut.clk, PHASE)

    # Step 3: SCL falls -> begin clocking data
    set_i2c_lines(dut, 0, 0)
    await ClockCycles(dut.clk, PHASE)

    # --- ADDRESS BYTE (7-bit address + R/W=0) ---
    full_addr = (address << 1) | 0
    for i in range(7, -1, -1):
        await i2c_clock_pulse(dut, (full_addr >> i) & 1)

    await i2c_ack_phase(dut)

    # --- REGISTER ADDRESS BYTE ---
    for i in range(7, -1, -1):
        await i2c_clock_pulse(dut, (reg_addr >> i) & 1)

    await i2c_ack_phase(dut)

    # --- DATA BYTE ---
    for i in range(7, -1, -1):
        await i2c_clock_pulse(dut, (value >> i) & 1)

    await i2c_ack_phase(dut)

    # --- STOP CONDITION ---
    # Step 1: SCL low, SDA low
    set_i2c_lines(dut, 0, 0)
    await ClockCycles(dut.clk, PHASE)

    # Step 2: SCL rises while SDA is still low
    set_i2c_lines(dut, 1, 0)
    await ClockCycles(dut.clk, PHASE)

    # Step 3: SDA rises while SCL is HIGH -> this is the STOP
    set_i2c_lines(dut, 1, 1)
    await ClockCycles(dut.clk, PHASE * 2)


# -------------------------------------------------
# MAIN TEST
# -------------------------------------------------
@cocotb.test()
async def test_i2c_pwm_logic(dut):

    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # --- Reset ---
    dut.rst_n.value  = 0
    dut.ena.value    = 1
    dut.uio_in.value = 0
    set_i2c_lines(dut, 1, 1)

    await ClockCycles(dut.clk, 10)

    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 20)  # let sync regs clear after reset

    # ---------------------------------
    # TEST 1: Duty Cycle = 0x40 (25%)
    # ---------------------------------
    dut._log.info("=== Test 1: duty_cycle = 0x40 (25%) ===")

    await i2c_write(dut, 0x3C, 0x00, 0x40)

    await ClockCycles(dut.clk, 20)

    high_count = 0
    for _ in range(256):
        await RisingEdge(dut.clk)
        if get_pwm_out(dut) == 1:
            high_count += 1

    dut._log.info(f"Measured high_count = {high_count}")

    assert 60 <= high_count <= 68, \
        f"Duty cycle mismatch: expected ~64, got {high_count}"

    # ---------------------------------
    # TEST 2: Prescaler = 4
    # ---------------------------------
    dut._log.info("=== Test 2: prescaler = 4 ===")

    await i2c_write(dut, 0x3C, 0x01, 0x04)

    await ClockCycles(dut.clk, 20)

    rise_count = 0
    start_time = 0
    end_time   = 0

    while rise_count < 2:
        await wait_pwm_rise(dut)

        t = cocotb.utils.get_sim_time(unit="ns")

        if rise_count == 0:
            start_time = t
        elif rise_count == 1:
            end_time = t

        rise_count += 1

    period = end_time - start_time

    dut._log.info(f"Measured PWM Period = {period} ns")

    assert 12000 <= period <= 13500, \
        f"Prescaler failed: period={period} ns"
