import re
from typing import List, Dict

def run(spec: str, verilog: str, ports: List[Dict]) -> Dict:
    """
    Detect combinational always blocks (@(*) or always_comb) that do not assign
    every output signal in all branches.
    Returns {"fired": True, "findings": [msg]} if a problem is found.
    """
    # Normalize: remove comments and string literals to avoid false matches
    def remove_comments_and_strings(text: str) -> str:
        # Remove /* ... */ comments
        text = re.sub(r'/\\*.*?\\*/', '', text, flags=re.S)
        # Remove // comments
        text = re.sub(r'//.*', '', text)
        # Remove string literals
        text = re.sub(r'\"[^\"]*\"', '', text)
        return text

    code = remove_comments_and_strings(verilog)

    # Find all always blocks that are combinational
    # Pattern: always @(*) ... or always_comb ...
    comb_block_pattern = r'always\s*@\s*\(\s*\*\s*\)|always_comb'
    # We'll split the code by 'always' and examine each block
    # Simple approach: find each occurrence and capture until next 'always' or end of module
    matches = list(re.finditer(r'always\s*', code, flags=re.I))
    fired = False
    findings = []

    for idx, match in enumerate(matches):
        start = match.end()
        # Determine if this always is combinational
        preceding = code[max(0, start-20):start]
        if not (re.search(r'always\s*@\s*\(\s*\*\s*\)', preceding, re.I) or
                re.search(r'always_comb', preceding, re.I)):
            continue  # not combinational

        # Find the end of this block: look for the next 'always' or 'endmodule'
        next_always = code.find('always', start)
        next_endmodule = code.find('endmodule', start)
        end = len(code)
        if next_always != -1:
            end = min(end, next_always)
        if next_endmodule != -1:
            end = min(end, next_endmodule)
        block = code[start:end]

        # Extract all assignments (blocking or non-blocking) to outputs
        # Output ports are those with direction output or inout
        output_names = {p['name'] for p in ports if p.get('direction') in ('output', 'inout')}
        if not output_names:
            continue

        # Find assignments: variable = ... ; or variable <= ... ;
        assign_pattern = r'([a-zA-Z_][a-zA-Z0-9_]*)\s*(=|<=)'
        assigned_vars = set()
        for m in re.finditer(assign_pattern, block):
            var = m.group(1)
            if var in output_names:
                assigned_vars.add(var)

        # If any output not assigned, flag
        missing = output_names - assigned_vars
        if missing:
            fired = True
            findings.append(f"Combinational always block missing assignments for outputs: {', '.join(sorted(missing))}")

    return {"fired": fired, "findings": findings}
