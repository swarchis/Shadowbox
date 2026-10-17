def run(spec: str, verilog: str, ports: list[dict]) -> dict:
    """
    Simple heuristic: look for assignments of the form
        assign out = in[ (sel << k) +: w ];
    and flag if (sel_width * k + w) > in_width.
    Returns findings if any such pattern appears.
    """
    import re
    findings = []
    # Extract port widths
    width_map = {}
    for p in ports:
        name = p.get("name")
        w = p.get("width")
        if isinstance(w, int):
            width_map[name] = w
        elif isinstance(w, str) and w.isdigit():
            width_map[name] = int(w)
    # Pattern: assign out = in[ (sel << shift) +: width ];
    pattern = re.compile(
        r'assign\s+\w+\s*=\s*(\w+)\s*\[\s*\(\s*(\w+)\s*<<\s*(\d+)\s*\)\s*\+\:\s*(\d+)\s*\]',
        re.IGNORECASE,
    )
    for m in pattern.finditer(verilog):
        in_name, sel_name, shift_str, width_str = m.groups()
        shift = int(shift_str)
        w = int(width_str)
        in_w = width_map.get(in_name, 0)
        sel_w = width_map.get(sel_name, 0)
        if in_w and sel_w:
            max_index = ( (1 << sel_w) - 1 ) << shift
            if max_index + w > in_w:
                findings.append(
                    f"Potential out-of-bounds select: {in_name}[({sel_name} << {shift}) +: {w}] "
                    f"may exceed width {in_w} (max index {max_index})."
                )
    return {"fired": bool(findings), "findings": findings}
