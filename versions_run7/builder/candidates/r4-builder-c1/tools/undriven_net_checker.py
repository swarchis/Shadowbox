import re

def run(spec: str, verilog: str, ports: list[dict]) -> dict:
    """
    Detects any wire or reg (excluding module ports) that is declared but never assigned.
    Returns {'fired': True, 'findings': [...]} if such nets are found.
    """
    # Extract module port names
    port_names = {p['name'] for p in ports}

    # Simple regex to find wire/reg declarations (ignoring dimensions for simplicity)
    decl_pattern = re.compile(
        r'\\b(wire|reg)\\s+(?:[^;]*)\\s+([a-zA-Z_][a-zA-Z0-9_]*)\\s*(?:\\[[^\\]]*\\])*\\s*[;,]', 
        re.IGNORECASE
    )
    declared = set()
    for match in decl_pattern.finditer(verilog):
        net = match.group(2)
        if net not in port_names:
            declared.add(net)

    # Find all assignments (blocking, non-blocking, continuous assign)
    assign_pattern = re.compile(
        r'(?:assign\\s+|\\<=|\\=)\\s*([a-zA-Z_][a-zA-Z0-9_]*)', 
        re.IGNORECASE
    )
    assigned = set()
    for match in assign_pattern.finditer(verilog):
        assigned.add(match.group(1))

    undriven = declared - assigned
    if undriven:
        findings = [f"Undriven net: {net}" for net in sorted(undriven)]
        return {"fired": True, "findings": findings}
    return {"fired": False, "findings": []}
