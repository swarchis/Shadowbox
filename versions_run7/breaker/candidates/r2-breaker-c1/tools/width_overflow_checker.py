import re
from typing import List, Dict, Any

def run(spec: str, verilog: str, ports: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Detect shift or index expressions that could exceed the width of an input port.
    Returns {"fired": bool, "findings": [str]}.
    """
    findings = []
    # Map port name -> width
    width_map = {}
    for p in ports:
        name = p.get("name")
        w = p.get("width")
        if isinstance(w, int) and w > 0:
            width_map[name] = w

    # Simple regex to find expressions like <signal> << <const> or <signal> + <const>
    # We look for patterns where a port is shifted left or added with a constant.
    # This is a lightweight check; false positives are acceptable.
    shift_pattern = re.compile(r'(\b\w+\b)\s*<<\s*(\d+)')
    add_pattern   = re.compile(r'(\b\w+\b)\s*\+\s*(\d+)')

    for match in shift_pattern.finditer(verilog):
        signal, shift_str = match.groups()
        shift = int(shift_str)
        if signal in width_map:
            w = width_map[signal]
            # If shift >= width, the shifted value could exceed the port width
            if shift >= w:
                findings.append(
                    f"Potential width overflow: '{signal}' shifted left by {shift} bits "
                    f"while its width is {w} bits."
                )

    for match in add_pattern.finditer(verilog):
        signal, const_str = match.groups()
        const = int(const_str)
        if signal in width_map:
            w = width_map[signal]
            # If constant added could push index beyond width-1
            if const >= w:
                findings.append(
                    f"Potential width overflow: '{signal}' added with {const} "
                    f"while its width is {w} bits."
                )

    return {"fired": bool(findings), "findings": findings}
