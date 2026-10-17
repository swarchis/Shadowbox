// Tiny syntax highlighter for Verilog and Python. No dependencies: a single
// regex scanner that classifies comments, strings, numbers and keywords.

export type Lang = 'verilog' | 'python'

export interface Token {
  text: string
  cls?: string
}

const VERILOG_KW = new Set(
  'module endmodule always always_ff always_comb always_latch assign begin end if else case casez casex endcase default posedge negedge or and not for while repeat forever generate endgenerate initial function endfunction task endtask return automatic unique priority'.split(
    ' ',
  ),
)
const VERILOG_TYPES = new Set('input output inout reg wire logic integer parameter localparam genvar signed unsigned bit byte int'.split(' '))

const PY_KW = new Set(
  'def return import from for in if elif else not and or is with as class lambda try except finally raise while yield pass break continue global nonlocal assert del async await'.split(
    ' ',
  ),
)
const PY_CONST = new Set(['True', 'False', 'None'])
const PY_BUILTIN = new Set('len range set dict list tuple enumerate bool str int float print min max sum any all sorted zip map filter isinstance open super'.split(' '))

const VERILOG_RE =
  /(\/\/[^\n]*)|(\/\*[\s\S]*?\*\/)|("(?:\\.|[^"\\\n])*")|(\d*'[sS]?[bBoOdDhH][0-9a-fA-FxXzZ_?]+|\b\d+(?:\.\d+)?\b)|(\$[A-Za-z_]\w*)|(`[A-Za-z_]\w*)|([A-Za-z_]\w*)|(<=|>=|==|!=|&&|\|\||[{}()[\];,:@#=<>!&|^~?+\-*/%])/g

const PY_RE =
  /(#[^\n]*)|([rRfFbB]{0,2}"""[\s\S]*?"""|[rRfFbB]{0,2}'''[\s\S]*?'''|[rRfFbB]{0,2}"(?:\\.|[^"\\\n])*"|[rRfFbB]{0,2}'(?:\\.|[^'\\\n])*')|(\b0[xX][0-9a-fA-F]+\b|\b\d+(?:\.\d+)?\b)|(@[A-Za-z_]\w*)|([A-Za-z_]\w*)(?=\s*\()|([A-Za-z_]\w*)|([{}()[\];,:=<>!&|^~+\-*/%.])/g

function classifyVerilog(m: RegExpExecArray): string | undefined {
  if (m[1] || m[2]) return 'tok-com'
  if (m[3]) return 'tok-str'
  if (m[4]) return 'tok-num'
  if (m[5] || m[6]) return 'tok-sys'
  if (m[7]) {
    if (VERILOG_KW.has(m[7])) return 'tok-kw'
    if (VERILOG_TYPES.has(m[7])) return 'tok-type'
    return undefined
  }
  if (m[8]) return 'tok-op'
  return undefined
}

function classifyPython(m: RegExpExecArray): string | undefined {
  if (m[1]) return 'tok-com'
  if (m[2]) return 'tok-str'
  if (m[3]) return 'tok-num'
  if (m[4]) return 'tok-sys'
  if (m[5]) return PY_KW.has(m[5]) ? 'tok-kw' : 'tok-fn'
  if (m[6]) {
    if (PY_KW.has(m[6])) return 'tok-kw'
    if (PY_CONST.has(m[6])) return 'tok-num'
    if (PY_BUILTIN.has(m[6])) return 'tok-fn'
    return undefined
  }
  if (m[7]) return 'tok-op'
  return undefined
}

/** Tokenize code and split into lines (tokens never span a newline). */
export function highlightLines(code: string, lang: Lang = 'verilog'): Token[][] {
  const re = new RegExp(lang === 'python' ? PY_RE.source : VERILOG_RE.source, 'g')
  const classify = lang === 'python' ? classifyPython : classifyVerilog
  const tokens: Token[] = []
  let last = 0
  let m: RegExpExecArray | null
  const src = code.replace(/\t/g, '  ')
  while ((m = re.exec(src))) {
    if (m.index > last) tokens.push({ text: src.slice(last, m.index) })
    tokens.push({ text: m[0], cls: classify(m) })
    last = m.index + m[0].length
    if (m[0].length === 0) re.lastIndex++
  }
  if (last < src.length) tokens.push({ text: src.slice(last) })

  const lines: Token[][] = [[]]
  for (const tok of tokens) {
    const parts = tok.text.split('\n')
    parts.forEach((p, i) => {
      if (i > 0) lines.push([])
      if (p) lines[lines.length - 1].push({ text: p, cls: tok.cls })
    })
  }
  if (lines.length > 1 && lines[lines.length - 1].length === 0) lines.pop()
  return lines
}

/** Line-level LCS diff. Returns the indexes of lines unique to each side. */
export function lineDiff(a: string, b: string): { removed: Set<number>; added: Set<number> } {
  const A = a.replace(/\s+$/, '').split('\n')
  const B = b.replace(/\s+$/, '').split('\n')
  const norm = (s: string) => s.trim().replace(/\s+/g, ' ')
  const n = A.length
  const m = B.length
  if (n * m > 250000) return { removed: new Set(), added: new Set() }
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--) dp[i][j] = norm(A[i]) === norm(B[j]) ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
  const removed = new Set<number>()
  const added = new Set<number>()
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (norm(A[i]) === norm(B[j])) {
      i++
      j++
    } else if (dp[i + 1][j] >= dp[i][j + 1]) removed.add(i++)
    else added.add(j++)
  }
  while (i < n) removed.add(i++)
  while (j < m) added.add(j++)
  // blank lines are noise
  A.forEach((l, k) => !l.trim() && removed.delete(k))
  B.forEach((l, k) => !l.trim() && added.delete(k))
  return { removed, added }
}
