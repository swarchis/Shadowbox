import re

def run(spec: str, verilog: str, ports: list[dict]) -> dict:
    """
    Detects outputs that are assigned inside an always block but are not declared as logic or reg.
    Returns a dict with fired=True and a list of findings if such a mismatch is found.
    """
    # Parse port directions and types from the module header
    # Simple regex to capture port list (assuming well-formed header)
    header_match = re.search(r'module\s+TopModule\s*\(([^)]*)\)', verilog, re.DOTALL | re.IGNORECASE)
    if not header_match:
        return {"fired": False, "findings": []}
    port_list = header_match.group(1)
    # Extract port names (ignore direction and type for simplicity)
    # This regex captures identifiers that appear as port names (ignoring vectors)
    port_names = re.findall(r'\b(input|output|inout)\s*(?:[^,]*)\b(\w+)', port_list)
    output_ports = {name for dir_, name in port_names if dir_.lower() == 'output'}

    # Find all always blocks (including always @(*), always @(posedge ...), etc.)
    always_blocks = re.findall(r'always\s*@\s*\([^)]*\)\s*[^{]*\{[^}]*\}', verilog, re.DOTALL | re.IGNORECASE)
    # Also capture always @(*) without braces? We'll assume braces present as in samples.
    # For each always block, look for assignments to output ports
    problematic_outputs = set()
    for block in always_blocks:
        # Find all blocking/nonblocking assignments inside the block
        assignments = re.findall(r'(\w+(?:\[[^\]]+\])?)\s*[<=]=', block)
        for lhs in assignments:
            # Strip possible array index to get base name
            base = lhs.split('[')[0]
            if base in output_ports:
                problematic_outputs.add(base)

    # Determine which outputs are declared as logic or reg
    # Look for declarations like: output logic [..] name; or output reg name;
    logic_decls = re.findall(r'output\s+(?:logic|reg)\s*[^;]*;', verilog, re.IGNORECASE)
    logic_outputs = set()
    for decl in logic_decls:
        # Extract the last identifier before semicolon (ignore dimensions)
        names = re.findall(r'\b(\w+)\s*(?:\[|;)', decl)
        if names:
            logic_outputs.add(names[-1])

    # Outputs that are assigned in always blocks but not declared as logic/reg
    to_fix = problematic_outputs - logic_outputs
    if to_fix:
        findings = [f"Output '{out}' assigned in always block but not declared as logic or reg." for out in to_fix]
        return {"fired": True, "findings": findings}
    return {"fired": False, "findings": []}
