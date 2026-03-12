module ATE(clk,reset,pix_data,type,bin,threshold);
input clk;
input reset;
input [7:0] pix_data;
input type;
output bin;
output [7:0] threshold;
reg [7:0] threshold;
reg bin;

// ================= IDENTIFIER =================
reg [6:0] col; //column
reg [5:0] Counter; //internal counter
reg [12:0]block_count; //block counter
reg en, state;
reg [1:0]cs,ns;
wire _en, _bin, z, _delay;
wire [6:0] _col, c_bound;
wire [5:0] _Counter;
wire [7:0] _threshold, Thres, Max, Min;
wire [7:0] pix_out;

// ================= Counter / State =================
assign _Counter = Counter + 1'b1;
assign cnt63    = &Counter;  // Counter == 63
assign _state   = (en) ? 1'b1 : state;

// ================= Column control =================
assign c_bound  = (type) ? 7'd65 : 7'd5;
assign _col     = (en && state) ? ((col == c_bound) ? 7'd0 : col + 1'b1) : col;

// ================= Boundary detect =================
assign z        = (col == c_bound) || (~|col);

// ================= Output generation =================
assign _bin       = (z) ? 1'b0 : (pix_out >= Thres);
assign _threshold = (z) ? 8'd0 : Thres;

// ================= SEQUENTIAL =================
always @(posedge clk or posedge reset) begin
    if (reset) begin
        Counter   <= 6'd0;
        state     <= 1'b0;
        en        <= 1'b0;
        col       <= 7'd0;
        threshold <= 8'd0;
        bin       <= 1'b0;
    end
    else begin
        Counter   <= _Counter;
        state     <= _state;
        en        <= cnt63;
        col       <= _col;
        threshold <= _threshold;
        bin       <= _bin;
    end
end
// ================= SUBMODULES =================
FIFO_64 F1(.clk(clk),.pix_data(pix_data),.Addr(Counter),.pix_out(pix_out));
MAX_MIN  mm0(pix_data, clk, reset, Counter, Max, Min);
THRES_GEN th0(Max, Min, clk, reset, en, Thres);
endmodule

/*=================MAX_MIN=================*/
module MAX_MIN (
    input [7:0] pix_data,
    input clk,
    input reset,
    input [5:0] cnt,      
    output reg [7:0] Max,
    output reg [7:0] Min
);

always @(posedge clk or posedge reset) begin
    if (reset) begin
        Max <= 8'd0;
        Min <= 8'd0; 
        
    end
    else begin

        if (cnt == 6'd0) begin
            Max <= pix_data;
            Min <= pix_data;
        end
      
        else begin
 
            if (pix_data > Max) 
                Max <= pix_data;
            
        
            if (pix_data < Min) 
                Min <= pix_data;
        end
    end
end

endmodule

/*=================FIFO_64=================*/
module FIFO_64(pix_data, clk, Addr ,pix_out);

parameter data_width = 7;
parameter fifo_depth = 63;

input [data_width:0]pix_data;
input clk;
input [5:0] Addr;
output reg[data_width:0]pix_out;


reg [data_width:0]fifo[fifo_depth:0];//8bits*64

always @(posedge clk) begin
	fifo[Addr] <= pix_data;
	pix_out <= fifo[Addr];
end

endmodule

/*=================THRES_GEN (RCA)=================*/
module THRES_GEN (Max, Min, clk, reset, en, Thres);

input	[7:0]	Max, Min;
input clk , reset, en;
output reg [7:0]	Thres;

wire Cin, C_out;
wire [6:0] Cm;
wire [7:0] sum;

assign Cin = Max[0] ^ Min[0]; //小數點進位

FA f0(Max[0], Min[0], Cin  , sum[0], Cm[0]);
FA f1(Max[1], Min[1], Cm[0], sum[1], Cm[1]);
FA f2(Max[2], Min[2], Cm[1], sum[2], Cm[2]);
FA f3(Max[3], Min[3], Cm[2], sum[3], Cm[3]);
FA f4(Max[4], Min[4], Cm[3], sum[4], Cm[4]);
FA f5(Max[5], Min[5], Cm[4], sum[5], Cm[5]);
FA f6(Max[6], Min[6], Cm[5], sum[6], Cm[6]);
FA f7(Max[7], Min[7], Cm[6], sum[7], C_out);

always @(posedge clk or posedge reset) begin
	if(reset)
		Thres <= 8'd0;
	else
		Thres <= (en) ? {C_out, sum[7:1]} : Thres; //0.5 * (Max + Min)
end
endmodule

module FA(a, b, cin, s, cout);
input a, b, cin;
output s, cout;
wire s0, c0, c1;
	HA u0(a, b, s0, c0);
	HA u1(s0, cin, s, c1);
	or g0(cout, c0, c1);
endmodule

module HA(a, b, s, cout);
input a, b;
output s, cout;
	and g0(cout,a,b);
	xor g1(s, a, b);
endmodule