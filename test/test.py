import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge


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
    # First wait until PWM output is LOW
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
# -------------------------------------------------
async def i2c_clock_pulse(dut, sda):
    set_i2c_lines(dut, 0, sda)
    await ClockCycles(dut.clk, 10)

    set_i2c_lines(dut, 1, sda)
    await ClockCycles(dut.clk, 10)

    set_i2c_lines(dut, 0, sda)
    await ClockCycles(dut.clk, 10)


# -------------------------------------------------
# ACK PHASE
# -------------------------------------------------
async def i2c_ack_phase(dut):

    # Master releases SDA
    set_i2c_lines(dut, 0, 1)
    await ClockCycles(dut.clk, 10)

    # SCL HIGH -> slave should drive ACK
    set_i2c_lines(dut, 1, 1)
    await ClockCycles(dut.clk, 10)

    slave_sda = get_slave_sda(dut)

    dut._log.info(f"ACK bit = {slave_sda} (0=ACK, 1=NACK)")
    assert slave_sda == 0, "Expected ACK (SDA=0) but got NACK (SDA=1)"

    # Finish clock
    set_i2c_lines(dut, 0, 1)
    await ClockCycles(dut.clk, 10)


# -------------------------------------------------
# I2C WRITE
# -------------------------------------------------
async def i2c_write(dut, address, reg_addr, value):

    # Idle
    set_i2c_lines(dut, 1, 1)
    await ClockCycles(dut.clk, 10)

    # START
    set_i2c_lines(dut, 1, 0)
    await ClockCycles(dut.clk, 10)

    # Address + Write bit
    full_addr = (address << 1) | 0

    for i in range(7, -1, -1):
        await i2c_clock_pulse(dut, (full_addr >> i) & 1)

    await i2c_ack_phase(dut)

    # Register address
    for i in range(7, -1, -1):
        await i2c_clock_pulse(dut, (reg_addr >> i) & 1)

    await i2c_ack_phase(dut)

    # Data byte
    for i in range(7, -1, -1):
        await i2c_clock_pulse(dut, (value >> i) & 1)

    await i2c_ack_phase(dut)

    # STOP
    set_i2c_lines(dut, 0, 0)
    await ClockCycles(dut.clk, 10)

    set_i2c_lines(dut, 1, 0)
    await ClockCycles(dut.clk, 10)

    set_i2c_lines(dut, 1, 1)
    await ClockCycles(dut.clk, 10)


# -------------------------------------------------
# MAIN TEST
# -------------------------------------------------
@cocotb.test()
async def test_i2c_pwm_logic(dut):

    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.rst_n.value = 0
    dut.ena.value = 1
    set_i2c_lines(dut, 1, 1)

    await ClockCycles(dut.clk, 5)

    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)

    # ---------------------------------
    # TEST 1: Duty Cycle
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
    # TEST 2: Prescaler
    # ---------------------------------
    dut._log.info("=== Test 2: prescaler = 4 ===")

    await i2c_write(dut, 0x3C, 0x01, 0x04)

    await ClockCycles(dut.clk, 20)

    rise_count = 0
    start_time = 0
    end_time = 0

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
