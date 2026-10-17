import re

def run(spec: str, verilog: str, ports: list[dict]) -> dict:
    """
    Detects whether each reset-like input appears in the sensitivity list
    of any always_ff or always @(posedge clk) block.
    Returns {"fired": bool, "findings": [str]}.
    """
    # Identify reset-like ports (case-insensitive match on reset, rst, areset, resetn)
    reset_ports = {p["name"].lower() for p in ports if re.search(r'reset|rst', p["name"], re.I)}
    if not reset_ports:
        return {"fired": False, "findings": []}

    # Find all always blocks that are edge-sensitive to clk
    # Pattern matches always @(posedge clk) ... or always @(posedge clk or ...)
    always_blocks = re.findall(
        r'always\s*@\s*\(\s*([^)]*?posedge\s+clk[^)]*?\)\s*(.*?)(?=always|\Z)',
        verilog,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Also capture always_ff @(posedge clk)
    always_ff_blocks = re.findall(
        r'always_ff\s*@\s*\(\s*([^)]*?posedge\s+clk[^)]*?\)\s*(.*?)(?=always|\Z)',
        verilog,
        flags=re.DOTALL | re.IGNORECASE,
    )
    blocks = always_blocks + always_ff_blocks

    missing = []
    for sens, body in blocks:
        sens_lower = sens.lower()
        # Determine which reset signals are present in sensitivity list
        present = {rp for rp in reset_ports if rp in sens_lower}
        # For each reset not present, check if it is used asynchronously in the body
        for rp in reset_ports - present:
            # Simple heuristic: if reset appears in body as an if condition without being in sens list
            if re.search(rf'\b{rp}\b', body, re.I):
                missing.append(f"Reset '{rp}' used in always block but missing from sensitivity list")
    fired = bool(missing)
    return {"fired": fired, "findings": missing}
