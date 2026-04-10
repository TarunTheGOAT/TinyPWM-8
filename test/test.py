import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge


# -------------------------------------------------
# I2C LINE HANDLING (FIXED: OPEN-DRAIN WIRED-AND)
# -------------------------------------------------
def set_i2c_lines(dut, scl, master_sda):
    slave_sda = (int(dut.uo_out.value) >> 1) & 1
    sda_line = master_sda & slave_sda
    dut.ui_in.value = (sda_line << 1) | scl


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
# ACK PHASE (FIXED)
# -------------------------------------------------
async def i2c_ack_phase(dut):
    # Master releases SDA (sets to 1)
    set_i2c_lines(dut, 0, 1)
    await ClockCycles(dut.clk, 10)

    # SCL HIGH → slave should drive ACK
    set_i2c_lines(dut, 1, 1)
    await ClockCycles(dut.clk, 10)

    # Read ACK from slave
    slave_sda = (int(dut.uo_out.value) >> 1) & 1
    dut._log.info(f"ACK bit = {slave_sda} (0=ACK, 1=NACK)")
    assert slave_sda == 0, "Expected ACK (SDA=0) but got NACK (SDA=1)"

    # Complete cycle
    set_i2c_lines(dut, 0, 1)
    await ClockCycles(dut.clk, 10)


# -------------------------------------------------
# I2C WRITE TRANSACTION
# -------------------------------------------------
async def i2c_write(dut, address, reg_addr, value):

    # Idle
    set_i2c_lines(dut, 1, 1)
    await ClockCycles(dut.clk, 10)

    # START condition
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

    # STOP condition
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
        if (int(dut.uo_out.value) & 0x01):
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
        await RisingEdge(dut.uo_out[0])

        if rise_count == 0:
            start_time = cocotb.utils.get_sim_time(unit="ns")
        elif rise_count == 1:
            end_time = cocotb.utils.get_sim_time(unit="ns")

        rise_count += 1

    period = end_time - start_time
    dut._log.info(f"Measured PWM Period = {period} ns")

    assert 12000 <= period <= 13500, \
        f"Prescaler failed: period={period} ns"
