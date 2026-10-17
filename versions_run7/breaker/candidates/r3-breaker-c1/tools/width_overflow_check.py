import re
from typing import List, Dict, Any

def run(spec: str, verilog: str, ports: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Detect shift or index expressions that could exceed the width of an input port.
    Returns {"fired": bool, "findings": [str]}.
    """
    # Map port name -> width (default 1 if not specified)
    port_widths = {}
    for p in ports:
        name = p.get("name")
        width = p.get("width")
        if width is None:
            width = 1
        else:
            # support expressions like "[7:0]" -> width = 8
            if isinstance(width, str):
                m = re.match(r'\$?\s*(\d+)\s*:\s*(\d+)\s*\$?', width)
                if m:
                    hi, lo = int(m.group(1)), int(m.group(2))
                    width = hi - lo + 1
                else:
                    try:
                        width = int(width)
                    except:
                        width = 1
        port_widths[name] = width

    # Patterns to catch: <<, >>, +, -, [ ... ] indexing
    # We'll look for expressions like (sel << 2) or (index + offset) used as an index.
    # Simple heuristic: find all occurrences of <identifier> << <num> or >> <num>
    # and check if shift amount could make result exceed any port width.
    findings = []

    # Find all identifiers (potential port names)
    id_pattern = re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b')
    for match in id_pattern.finditer(verilog):
        identifier = match.group(1)
        if identifier not in port_widths:
            continue
        width = port_widths[identifier]
        # Look left and right for shift operators within a small window
        start, end = match.span()
        window = verilog[max(0, start-20):min(len(verilog), end+20)]
        # Check for left shift
        ls_shift = re.search(r'<<\s*(\d+)', window)
        if ls_shift:
            shift_amt = int(ls_shift.group(1))
            if shift_amt >= width:  # shifting left by >= width can overflow
                findings.append(
                    f"Potential width overflow: '{identifier}' << {shift_amt} may exceed width {width}."
                )
        # Check for right shift (less likely to overflow but flag large shifts)
        rs_shift = re.search(r'>>\s*(\d+)', window)
        if rs_shift:
            shift_amt = int(rs_shift.group(1))
            if shift_amt >= width:
                findings.append(
                    f"Potential excessive right shift: '{identifier}' >> {shift_amt} (width {width})."
                )
        # Check for addition/subtraction with constants that could exceed width
        add_sub = re.search(r'[+\-]\s*(\d+)', window)
        if add_sub:
            const = int(add_sub.group(1))
            # If identifier already at max width, adding positive constant may overflow
            if const > 0:
                findings.append(
                    f"Potential overflow: '{identifier}' {add_sub.group(0)} {const} may exceed width {width}."
                )

    fired = len(findings) > 0
    # Deduplicate findings
    findings = list(dict.fromkeys(findings))
    return {"fired": fired, "findings": findings}
