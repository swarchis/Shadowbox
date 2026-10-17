import re

def run(spec: str, verilog: str, ports: list[dict]):
    """
    Returns {'fired': True, 'findings': [...]} if any output port
    has no assignment (neither blocking/nonblocking nor continuous assign)
    in the Verilog module.
    """
    # Extract output port names
    output_names = {p['name'] for p in ports if p.get('direction') == 'output'}
    if not output_names:
        return {"fired": False, "findings": []}

    # Remove comments to avoid false positives
    code = re.sub(r'//.*', '', verilog)
    code = re.sub(r'/\\*.*?\\*/', '', code, flags=re.DOTALL)

    # Find all left-hand sides of assignments
    # Continuous assign: assign <lhs> = ...
    # Procedural assignments: <lhs> = ... ; or <lhs> <= ... ;
    lhs_pattern = r'\b(assign\s+)?([\w\[\]]+)\s*[=<=]'
    assigned = set()
    for m in re.finditer(lhs_pattern, code):
        # m.group(2) is the lhs token (may include indices like sum[4])
        lhs = m.group(2)
        # Strip any array indices to get base name
        base = lhs.split('[')[0]
        assigned.add(base)

    undriven = output_names - assigned
    if undriven:
        findings = [f"Output port '{name}' never assigned" for name in sorted(undriven)]
        return {"fired": True, "findings": findings}
    return {"fired": False, "findings": []}
