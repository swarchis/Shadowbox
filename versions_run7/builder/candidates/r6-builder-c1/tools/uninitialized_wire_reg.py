def run(spec: str, verilog: str, ports: list[dict]) -> dict:
    """
    Returns {'fired': True, 'findings': [...]} if any wire or reg (excluding ports)
    never gets a assignment in the verilog.
    """
    import re

    # Extract port names
    port_names = {p['name'] for p in ports}

    # Remove comments and string literals to avoid false matches
    def strip_comments(text: str) -> str:
        # remove /* ... */ comments
        text = re.sub(r'/\\*.*?\\*/', '', text, flags=re.DOTALL)
        # remove // comments
        text = re.sub(r'//.*', '', text)
        return text

    code = strip_comments(verilog)

    # Find all net/variable declarations (wire, reg, logic, etc.)
    # Simple pattern: \b(wire|reg|logic)\s+[^;]+;
    decl_pattern = re.compile(r'\b(wire|reg|logic)\s+([^;]+);', re.IGNORECASE)
    declared = set()
    for _, decl in decl_pattern.findall(code):
        # Split by commas, handle arrays like foo [3:0] bar;
        # We'll just take identifiers ignoring brackets
        parts = re.split(r'[,\s]+', decl.strip())
        for p in parts:
            if not p:
                continue
            # Remove array ranges like foo[3:0] -> foo
            p = re.sub(r'\s*\[[^]]*\]', '', p)
            if p:
                declared.add(p)

    # Find all left-hand side assignments (blocking =, nonblocking <=, and also assign)
    # Patterns: assign lhs = ;  or lhs = ;  or lhs <= ;
    assign_pattern = re.compile(
        r'(?:assign\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:[<=])\s*',
        re.IGNORECASE
    )
    assigned = set()
    for lhs in assign_pattern.findall(code):
        # Strip array indices
        lhs_base = re.sub(r'\s*\[[^]]*\]', '', lhs)
        assigned.add(lhs_base)

    # Also consider port outputs as assigned (they are driven by assign/always)
    # but we already excluded them from declared check.

    # Determine uninitialized declared items (excluding ports)
    uninit = declared - assigned - port_names
    if uninit:
        findings = [f"Signal '{sig}' declared but never assigned" for sig in sorted(uninit)]
        return {"fired": True, "findings": findings}
    return {"fired": False, "findings": []}
