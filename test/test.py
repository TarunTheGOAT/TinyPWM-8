import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer, RisingEdge, FallingEdge, ClockCycles

async def i2c_write(dut, address, reg_addr, value):
    """Helper to perform an I2C write transaction"""
    # Start Condition: SDA goes low while SCL is high
    dut.ui_in.value = 0b01  # SCL=1, SDA=0
    await ClockCycles(dut.clk, 10)

    # Send 7-bit Address + Write Bit (0)
    full_addr = (address << 1) | 0
    for i in range(7, -1, -1):
        bit = (full_addr >> i) & 1
        dut.ui_in.value = (0 << 1) | bit # SCL low, set SDA
        await ClockCycles(dut.clk, 10)
        dut.ui_in.value = (1 << 1) | bit # SCL high
        await ClockCycles(dut.clk, 10)

    # ACK bit from Slave
    dut.ui_in.value = 0b00 # SCL low
    await ClockCycles(dut.clk, 10)
    dut.ui_in.value = 0b10 # SCL high
    await ClockCycles(dut.clk, 10)

    # Send Register Address
    for i in range(7, -1, -1):
        bit = (reg_addr >> i) & 1
        dut.ui_in.value = (0 << 1) | bit
        await ClockCycles(dut.clk, 10)
        dut.ui_in.value = (1 << 1) | bit
        await ClockCycles(dut.clk, 10)

    # ACK
    dut.ui_in.value = 0b10
    await ClockCycles(dut.clk, 10)

    # Send Data Value
    for i in range(7, -1, -1):
        bit = (value >> i) & 1
        dut.ui_in.value = (0 << 1) | bit
        await ClockCycles(dut.clk, 10)
        dut.ui_in.value = (1 << 1) | bit
        await ClockCycles(dut.clk, 10)

    # ACK and Stop
    dut.ui_in.value = 0b10
    await ClockCycles(dut.clk, 10)
    dut.ui_in.value = 0b11 # Stop: SDA high while SCL high
    await ClockCycles(dut.clk, 10)

@cocotb.test()
async def test_i2c_pwm_logic(dut):
    # Setup Clock (100MHz for fast simulation)
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Initialize
    dut.rst_n.value = 0
    dut.ui_in.value = 0b11 # SCL/SDA high (Idle)
    dut.ena.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    # --- Test 1: Program 25% Duty Cycle ---
    # Register 0x00 is Duty Cycle. 25% of 256 is 64 (0x40).
    dut._log.info("Setting Duty Cycle to 25% (0x40)")
    await i2c_write(dut, 0x3C, 0x00, 0x40)

    # Wait for a full PWM cycle (256 counts)
    high_count = 0
    for _ in range(256):
        await RisingEdge(dut.clk)
        if int(dut.uo_out.value) & 0x01:
            high_count += 1

    dut._log.info(f"Measured High Pulses: {high_count}/256")
    assert 60 <= high_count <= 68, f"Duty cycle mismatch! Expected ~64, got {high_count}"

    # --- Test 2: Program Prescaler ---
    # Register 0x01 is Prescaler. Set to 0x04 (Slow down PWM 4x)
    dut._log.info("Setting Prescaler to 4")
    await i2c_write(dut, 0x3C, 0x01, 0x04)

    # Verify timing (each PWM increment should now take 5 clock cycles)
    await RisingEdge(dut.uo_out)
    start_time = cocotb.utils.get_sim_time(unit="ns")
    await RisingEdge(dut.uo_out)
    end_time = cocotb.utils.get_sim_time(unit="ns")

    period = end_time - start_time
    dut._log.info(f"Measured PWM Period: {period}ns")
    # Expected: (Prescaler + 1) * 256 * clock_period = 5 * 256 * 10 = 12,800ns
    assert 12700 <= period <= 12900, "Prescaler logic failed to slow down the signal!"
