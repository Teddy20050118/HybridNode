// 自動產生的 Testbench
// 產生時間：由 HybridNode AutoTestbenchGenerator 自動生成
// 頂層模組：

`timescale 1ns / 1ps

module auto_generated_tb;

    // 訊號宣告
    reg clk;
    reg reset;


    // 測資記憶體
    integer i;  // 迴圈計數器

    // 時脈產生器
    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;  // 週期 10 ns
    end


    // 頂層模組例現化
     uut (
        .clk(clk),
        .reset(reset)
    );

    // 測資載入與模擬控制
    initial begin
        $dumpfile("_auto_sim.vcd");
        $dumpvars(0, auto_generated_tb);

        // 載入測資檔案

        // 重置序列
        reset = 1'b1;
        #20;
        reset = 1'b0;
        #10;

        // 餵入測資
        for (i = 0; i < 4096; i = i + 1) begin
            @(posedge clk);

            // 顯示進度
            if (i % 512 == 0) begin
                $display("進度：%0d / 4096 筆資料已送出 (%0t)", i, $time);
            end
        end

        // 等待穩定
        #100;

        // 模擬完成
        $display("模擬完成：共 4096 筆資料 (%0t)", $time);
        $finish;
    end

endmodule
