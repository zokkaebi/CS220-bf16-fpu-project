`timescale 1ns / 100ps

// Throughput regression: launch all independent BF16 oracle vectors on
// consecutive cycles, rather than holding each input for several cycles.
// Checks the complete four-edge pipeline with no bubbles between requests.
// Run from the repository root so the golden-vector path resolves.
module test_bf16_streaming_golden;
    reg clk = 0;
    // PERIOD can be overridden for gate-level runs; +VCD=<file> dumps the DUT for PrimeTime.
    parameter real PERIOD = 10.0;
    always #(PERIOD/2.0) clk = ~clk;
    reg [8*256-1:0] vcdfile;
    initial if ($value$plusargs("VCD=%s", vcdfile)) begin
        $dumpfile(vcdfile);
        $dumpvars(0, test_bf16_streaming_golden.dut);
    end

    reg [1:0] rmode = 0;
    reg [2:0] fpu_op = 0;
    reg [15:0] opa = 0, opb = 0;
    wire [15:0] out;
    wire inf, snan, qnan, ine, overflow, underflow, zero, div_by_zero;

    fpu_bf16_wrapper dut (
        .clk(clk), .rmode(rmode), .fpu_op(fpu_op),
        .opa(opa), .opb(opb), .out(out),
        .inf(inf), .snan(snan), .qnan(qnan), .ine(ine),
        .overflow(overflow), .underflow(underflow),
        .zero(zero), .div_by_zero(div_by_zero)
    );

    reg input_valid = 0;
    reg [15:0] input_expected = 0;
    reg [3:0] valid_pipe = 0;
    reg [15:0] expected_pipe [0:3];
    integer fd, scanned, op_num, mode_num;
    integer sent = 0, checked = 0, errors = 0;
    integer i, j;
    reg [15:0] a, b, expected;
    reg same;

    function is_nan;
        input [15:0] bits;
        begin
            is_nan = (&bits[14:7]) && (|bits[6:0]);
        end
    endfunction

    initial begin
        for (i = 0; i < 4; i = i + 1)
            expected_pipe[i] = 0;
    end

    // The expected result travels with the transaction through four stages.
    always @(posedge clk) begin
        valid_pipe <= {valid_pipe[2:0], input_valid};
        expected_pipe[0] <= input_expected;
        for (j = 1; j < 4; j = j + 1)
            expected_pipe[j] <= expected_pipe[j-1];

        // Allow the legacy source core's #1 output-register delay to settle.
        #2;
        if (valid_pipe[3]) begin
            checked = checked + 1;
            if (is_nan(expected_pipe[3]))
                same = (is_nan(out) === 1'b1);
            else
                same = (out === expected_pipe[3]);
            if (same !== 1'b1) begin
                errors = errors + 1;
                if (errors <= 30)
                    $display("STREAM MISMATCH case=%0d expected=%h got=%h",
                             checked, expected_pipe[3], out);
            end
        end
    end

    initial begin
        fd = $fopen("test_vectors/bf16_golden.hex", "r");
        if (fd == 0)
            $fatal(1, "Missing test_vectors/bf16_golden.hex");

        while (!$feof(fd)) begin
            scanned = $fscanf(fd, "%h %h %d %d %h\n",
                              a, b, op_num, mode_num, expected);
            if (scanned == 5) begin
                @(negedge clk);
                opa = a;
                opb = b;
                fpu_op = op_num[2:0];
                rmode = mode_num[1:0];
                input_expected = expected;
                input_valid = 1;
                sent = sent + 1;
            end
        end
        $fclose(fd);

        @(negedge clk);
        input_valid = 0;
        opa = 0;
        opb = 0;
        fpu_op = 0;
        rmode = 0;
        repeat (6) @(posedge clk);
        #3;
        $display("BF16 STREAMING GOLDEN: sent=%0d checked=%0d mismatches=%0d",
                 sent, checked, errors);
        if (sent == 0 || sent != checked || errors != 0)
            $fatal(1, "BF16_STREAMING_GOLDEN_FAILED");
        $display("BF16_STREAMING_GOLDEN_PASSED");
        $finish;
    end
endmodule
