`default_nettype none

module tt_um_i2c_pwm #(
    parameter CLOCKS_PER_SECOND = 24'd9_999_999
)(
    // DO NOT CHANGE THESE NAMES!!
    // The factory tools require these exact port definitions
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

   // I2C Signal Definitions
   wire scl = ui_in[0]; // input clock, ie clock from master
   wire sda_in = ui_in[1]; // input data
   reg  sda_out;

   // Assign outputs
   assign uo_out[1]   = sda_out;
   assign uo_out[7:2] = 6'b0;
   assign uio_oe      = 8'b0;
   assign uio_out     = 8'b0;

   // Synchronizers to prevent metastability
   reg [1:0] scl_sync, sda_sync;
   always @(posedge clk) begin
      scl_sync <= {scl_sync[0], scl}; // scl_sync = [previous scl value, current scl value]
      sda_sync <= {sda_sync[0], sda_in}; // sda_sync = [previous sda_in, current sda_in]
   end

   wire scl_rise = (scl_sync == 2'b10);
   wire scl_fall = (scl_sync == 2'b01);
   wire scl_high = scl_sync[0];

   // Start/Stop detection
   // start_bit = when sda_i falls high to low (1 to 0) while scl_sync(scl) is high
   wire start_bit = (scl_high && !sda_sync[0] && sda_sync[1]);
   wire stop_bit = (scl_high && sda_sync[0] && !sda_sync[1]);

   reg [2:0] state, next_state; // state variable
   reg [3:0] bit_count; // bit count - how many bits have been received so far
   reg [7:0] shift_reg; // shift register - stores the data by shifting the bits as more are received to form a full byte
   reg [7:0] reg_addr; // states which Internal register the master want to access: duty_cycle or prescaler

   // Internal Registers
   reg [7:0] duty_cycle;
   reg [7:0] prescaler;

   // States
   localparam IDLE = 0, ADDR = 1, GET_REG = 2, WRITE_VAL = 3, ACK = 4;


   always @(posedge clk or negedge rst_n) begin
      if (!rst_n) begin
         state      <= IDLE;
         duty_cycle <= 8'h80;
         prescaler  <= 8'h00;
         sda_out    <= 1'b1;
         bit_count  <= 0;
         shift_reg  <= 0;
         reg_addr   <= 0;
         next_state <= IDLE;

      end else begin
         // Default: release SDA unless ACKing
         sda_out <= 1'b1;

         case (state)

           IDLE: begin
              bit_count <= 0;
              if (start_bit) begin
                 state     <= ADDR;
                 shift_reg <= 0;
              end
           end

           ADDR: begin
              if (scl_rise) begin
                 shift_reg <= {shift_reg[6:0], sda_sync[1]};

                 if (bit_count == 7) begin
                    bit_count <= 0;

                    if ({shift_reg[6:0], sda_sync[1]}[7:1] == 7'h3C &&
                        {shift_reg[6:0], sda_sync[1]}[0]   == 1'b0) begin
                       next_state <= GET_REG;
                       state      <= ACK;
                    end else begin
                       state <= IDLE;
                    end
                 end else begin
                    bit_count <= bit_count + 1;
                 end
              end
           end

           GET_REG: begin
              if (scl_rise) begin
                 shift_reg <= {shift_reg[6:0], sda_sync[1]};

                 if (bit_count == 7) begin
                    reg_addr   <= {shift_reg[6:0], sda_sync[1]};
                    bit_count  <= 0;
                    next_state <= WRITE_VAL;
                    state      <= ACK;
                 end else begin
                    bit_count <= bit_count + 1;
                 end
              end
           end

           WRITE_VAL: begin
              if (scl_rise) begin
                 shift_reg <= {shift_reg[6:0], sda_sync[1]};

                 if (bit_count == 7) begin
                    bit_count <= 0;

                    if (reg_addr == 8'h00)
                      duty_cycle <= {shift_reg[6:0], sda_sync[1]};
                    else if (reg_addr == 8'h01)
                      prescaler <= {shift_reg[6:0], sda_sync[1]};

                    next_state <= IDLE;
                    state      <= ACK;
                 end else begin
                    bit_count <= bit_count + 1;
                 end
              end
           end

           ACK: begin
              sda_out <= 1'b0;

              if (scl_fall) begin
                 sda_out <= 1'b1;
                 state   <= next_state;
              end
           end

         endcase
      end
   end

   // PWM Engine with Prescalar
   reg [7:0] p_cnt;
   reg [7:0] pwm_cnt;

   always @(posedge clk or negedge rst_n) begin
      if (!rst_n) begin
         p_cnt <= 0;
         pwm_cnt <= 0;
      end else begin
         if (p_cnt >= prescaler) begin
            p_cnt <= 0;
            pwm_cnt <= pwm_cnt + 1;
         end else begin
            p_cnt <= p_cnt + 1;
         end
      end // else: !if(!rst_n)
   end // always @ (posedge clk or negedge rst_n)

   assign uo_out[0] = (pwm_cnt < duty_cycle);

endmodule
