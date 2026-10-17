# Verilog reference (Shadowbox skill)

Written for this project. A compact guide to the mistakes that most often make a design compile but behave wrongly.

## Read the specification like a test
- List every input and output with its width before writing logic. The module name is TopModule and the ports must match exactly.
- If the spec gives a truth table, a Karnaugh map or a waveform, it IS the test. After writing the logic, check every listed row against your expression, one row at a time. Don't guess a pattern (e.g. "it looks like XOR") without checking all rows.
- Karnaugh maps: mind the Gray-code order of the row and column labels (00, 01, 11, 10), and which variables label rows vs columns. "d" or "x" entries are don't-cares; use them only if they simplify.
- "The output is set the cycle after X happens" means a registered output (it changes on the clock edge after X).

## Combinational logic
- `assign` for simple expressions. `always @(*)` / `always_comb` for if/case logic.
- In combinational always blocks, use blocking `=` and give every output a value on every path (a default first) so no latch is inferred.
- Every `case` gets a `default`.
- Vector operations work bit by bit: `a & b` on 8-bit vectors gives 8 bits; reduction `&a` gives 1 bit.
- Width rules: concatenation `{a, b}` widths add up; assigning a wide value to a narrow signal truncates the high bits.

## Clocked logic
- In `always @(posedge clk)` use non-blocking `<=` only.
- Synchronous reset (checked only on the clock edge):
  `always @(posedge clk) if (reset) q <= 0; else q <= d;`
- Asynchronous reset (takes effect immediately): put it in the sensitivity list.
  Active-high: `always @(posedge clk, posedge areset) if (areset) ...`
  Active-low (name ends in n): `always @(posedge clk, negedge aresetn) if (!aresetn) ...`
- Negative-edge flip-flops use `negedge clk` only when the spec says so.

## Common patterns
- Rising-edge detect (0 then 1): keep `prev <= in;` and output `~prev & in`. Falling edge: `prev & ~in`. "Any edge": `prev ^ in`.
  If the output must appear the cycle after the edge, register the detection: `pedge <= ~prev & in;` in the clocked block.
- Counter with enable and wrap: `if (reset) q <= 0; else if (ena) q <= (q == MAX) ? 0 : q + 1;`
- Shift register, data in at the MSB: `q <= {data, q[N-1:1]};` At the LSB: `q <= {q[N-2:0], data};`
- Dual-edge behavior cannot use a single always block on both edges; combine a posedge and a negedge register with a mux on `clk`, or with XOR tricks.

## Finite state machines
- Two blocks: a clocked block for `state <= next;` (with reset to the specified initial state), and a combinational block computing `next` (and Moore outputs) from `state` and inputs.
- Moore outputs depend only on the state; Mealy outputs also depend on the current inputs. Follow the spec's description exactly.
- Use the state encoding the spec gives (e.g. one-hot) when it asks for it.

## Before answering
- Re-check: reset polarity and sync vs async, edge direction, bit order, every truth-table row, every case branch has an output.
