`default_nettype none
`timescale 1ns / 1ps

module tb ();

  // Dump waves
  initial begin
    $dumpfile("tb.fst");
    $dumpvars(0, tb);
  end

  // Signals
  reg clk   = 0;
  reg rst_n = 0;
  reg ena   = 1;
  reg [7:0] ui_in  = 8'b11;  // I2C idle: SCL=1, SDA=1
  reg [7:0] uio_in = 8'b0;

  wire [7:0] uo_out;
  wire [7:0] uio_out;
  wire [7:0] uio_oe;

`ifdef GL_TEST
  wire VPWR = 1'b1;
  wire VGND = 1'b0;
`endif

  // DUT
  tt_um_i2c_pwm
`ifndef GL_TEST
  #(
    .CLOCKS_PER_SECOND(24'd9)
  )
`endif
  user_project (
`ifdef GL_TEST
    .VPWR(VPWR),
    .VGND(VGND),
`endif
    .ui_in  (ui_in),
    .uo_out (uo_out),
    .uio_in (uio_in),
    .uio_out(uio_out),
    .uio_oe (uio_oe),
    .ena    (ena),
    .clk    (clk),
    .rst_n  (rst_n)
  );

  // ✅ Optional fallback clock (safe with Cocotb)
  always #5 clk = ~clk;

  // ✅ Reset sequence (important!)
  initial begin
    rst_n = 0;
    #50;
    rst_n = 1;
  end

endmodule
