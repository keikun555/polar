#!/usr/bin/env python3
"""Translate pWhileDt programs (ProbContLogic's paper.tex / Lean surface syntax) into Polar's
.prob input language (extension_ost branch).

Scope of this first version: programs whose loop guard is a deterministic clock condition
(`t < T`), i.e. every example in the paper whose iteration count n = T/dt is not itself random.
The guard is emitted literally; run polar.py on the result with `--solve_deterministic_guards`
(added in this fork specifically to support this) so it solves the guard for its exact crossing
iteration count instead of rejecting it. With `T`/`dt` left symbolic (the common case, to get a
general-in-T/dt result), Polar still produces the closed form in terms of its own iteration
counter and simply doesn't auto-evaluate it at a concrete n; substitute n = T/dt by hand in that
case. (Loops with a genuinely random exit time, e.g. the controlled-diffusion / sticky-point
escape examples, need the --ost machinery instead; this translator does not attempt that case yet
-- see TODO at the bottom.)

Key semantic facts this translator encodes (confirmed against lean/ProbContLogic/Semantics.lean):
  - `x += f*dt`  (drift)   is the deterministic update   x := x + f*dt
  - `x += f*db`  (diffuse) is the two-point mixture       x := x + f*sqrt(dt)  w.p. 1/2
                                                           x := x - f*sqrt(dt)  w.p. 1/2
  - `x := flip(p)` (sample, Disc only) is Bernoulli:      x := 1 w.p. p, x := 0 w.p. 1-p
  - `x := clamp(e,a,b)` has no Polar builtin; expanded into an if/elif/else cascade.

Polar-side gotchas this translator works around:
  - Polar's own lexer uses a leading-uppercase-letter convention for distribution/type names
    (DIST_NAME, TYPE_NAME); a pWhileDt variable like `X`, `V`, `Omega`, `M` would otherwise be
    lexed as one of those instead of a plain variable, so every identifier is lowercased.
  - sympy's default sympify() namespace shadows a handful of lowercase names users of this paper
    actually use as parameters (`gamma`, `beta`, `zeta`, `pi`, `bernoulli`, ...), resolving them to
    sympy FunctionClass/constant objects instead of free symbols and crashing downstream. Any
    identifier that doesn't survive a `sympify(name) is a Symbol` round trip is mangled.
  - `dt**(1/2)` for sqrt needs *no* new Polar feature: Polar's `arithm` grammar already has `**`
    and `/`, and sympy evaluates `Pow(dt, Rational(1,2))` as the real sqrt natively. Verified end
    to end: translating a bare diffuse step and asking Polar for `E(x**2)` at n=5 gives the exact
    closed form `5*dt*sigma**2`, matching the paper's own `db`-driven variance-dt bookkeeping.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union

try:
    import sympy
except ImportError:  # pragma: no cover - sympy ships with the polar venv
    sympy = None


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

TOKEN_SPEC = [
    ("NUMBER", r"\d+(\.\d+)?"),
    ("ASSIGN", r":="),
    ("PLUSEQ", r"\+="),
    ("MINUSEQ", r"-="),
    ("AND", r"&&"),
    ("OR", r"\|\|"),
    ("EQ", r"=="),
    ("NEQ", r"!="),
    ("LEQ", r"<="),
    ("GEQ", r">="),
    ("LT", r"<"),
    ("GT", r">"),
    ("NOT", r"!"),
    ("PLUS", r"\+"),
    ("MINUS", r"-"),
    ("STAR", r"\*"),
    ("SLASH", r"/"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("LBRACE", r"\{"),
    ("RBRACE", r"\}"),
    ("LBRACK", r"\["),
    ("RBRACK", r"\]"),
    ("COMMA", r","),
    ("COLON", r":"),
    ("SEMI", r";"),
    ("NAME", r"[A-Za-z_][A-Za-z0-9_]*"),
    ("SKIP", r"[ \t\r\n]+"),
    ("COMMENT", r"//[^\n]*"),
]
TOKEN_RE = re.compile("|".join(f"(?P<{n}>{p})" for n, p in TOKEN_SPEC))

KEYWORDS = {"cont", "cmpct", "disc", "while", "if", "else", "skip", "clamp", "flip"}


@dataclass
class Token:
    kind: str
    value: str


def tokenize(src: str) -> List[Token]:
    tokens = []
    pos = 0
    while pos < len(src):
        m = TOKEN_RE.match(src, pos)
        if not m:
            raise SyntaxError(f"Unexpected character {src[pos]!r} at {pos}")
        kind = m.lastgroup
        value = m.group()
        pos = m.end()
        if kind in ("SKIP", "COMMENT"):
            continue
        if kind == "NAME" and value in KEYWORDS:
            kind = value.upper()
        tokens.append(Token(kind, value))
    tokens.append(Token("EOF", ""))
    return tokens


# ---------------------------------------------------------------------------
# AST
# ---------------------------------------------------------------------------

# Expressions are represented as nested tuples:
#   ('num', literal_text)
#   ('var', name)
#   ('neg', expr)
#   ('bin', op, lhs, rhs)        op in {'+','-','*','/'}
#   ('call', fname, [args])      fname in {'clamp', 'flip'}
# Conditions:
#   ('cmp', op, lhs, rhs)        op in {'==','!=','<','<=','>','>='}
#   ('and', c1, c2) / ('or', c1, c2) / ('not', c)
#   ('true',)

Expr = tuple
Cond = tuple


@dataclass
class Decl:
    cls: str  # 'cont' | 'cmpct' | 'disc'
    names: List[str]


@dataclass
class MultiAssign:
    lhs: List[str]
    rhs: List[Expr]


@dataclass
class Incr:
    var: str
    expr: Expr


@dataclass
class While:
    cond: Cond
    body: List["Stmt"]


@dataclass
class If:
    cond: Cond
    then: List["Stmt"]
    orelse: List["Stmt"]


@dataclass
class Skip:
    pass


Stmt = Union[MultiAssign, Incr, While, If, Skip]


@dataclass
class Program:
    decls: List[Decl]
    body: List[Stmt]


# ---------------------------------------------------------------------------
# Parser (recursive descent)
# ---------------------------------------------------------------------------


class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.i = 0

    def peek(self) -> Token:
        return self.tokens[self.i]

    def advance(self) -> Token:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def expect(self, kind: str) -> Token:
        tok = self.peek()
        if tok.kind != kind:
            raise SyntaxError(f"Expected {kind}, got {tok.kind} ({tok.value!r}) at token {self.i}")
        return self.advance()

    def at(self, kind: str) -> bool:
        return self.peek().kind == kind

    # ---- top level -------------------------------------------------
    def parse_program(self) -> Program:
        decls = []
        while self.peek().kind in ("CONT", "CMPCT", "DISC"):
            decls.append(self.parse_decl())
        body = self.parse_stmts(stop_kinds={"EOF"})
        return Program(decls, body)

    def parse_decl(self) -> Decl:
        cls = self.advance().kind.lower()
        names = [self.parse_var_spec()]
        while self.at("COMMA"):
            self.advance()
            names.append(self.parse_var_spec())
        self.expect("SEMI")
        return Decl(cls, names)

    def parse_var_spec(self) -> str:
        name = self.expect("NAME").value
        if self.at("COLON"):
            self.advance()
            if self.at("LBRACK"):
                self.advance()
                self.parse_expr()
                self.expect("COMMA")
                self.parse_expr()
                self.expect("RBRACK")
            elif self.at("LPAREN"):
                self.advance()
                self.expect("NAME")
                while self.at("COMMA"):
                    self.advance()
                    self.expect("NAME")
                self.expect("RPAREN")
            else:
                raise SyntaxError(f"Expected range or enum after ':' for {name}")
        return name

    # ---- statements --------------------------------------------------
    def parse_stmts(self, stop_kinds) -> List[Stmt]:
        stmts = []
        while self.peek().kind not in stop_kinds:
            stmts.append(self.parse_stmt())
        return stmts

    def parse_stmt(self) -> Stmt:
        if self.at("WHILE"):
            return self.parse_while()
        if self.at("IF"):
            return self.parse_if()
        if self.at("SKIP"):
            self.advance()
            self.expect("SEMI")
            return Skip()
        return self.parse_simple_stmt()

    def parse_while(self) -> While:
        self.expect("WHILE")
        self.expect("LPAREN")
        cond = self.parse_cond()
        self.expect("RPAREN")
        self.expect("LBRACE")
        body = self.parse_stmts(stop_kinds={"RBRACE"})
        self.expect("RBRACE")
        return While(cond, body)

    def parse_if(self) -> If:
        self.expect("IF")
        self.expect("LPAREN")
        cond = self.parse_cond()
        self.expect("RPAREN")
        self.expect("LBRACE")
        then = self.parse_stmts(stop_kinds={"RBRACE"})
        self.expect("RBRACE")
        orelse: List[Stmt] = []
        if self.at("ELSE"):
            self.advance()
            self.expect("LBRACE")
            orelse = self.parse_stmts(stop_kinds={"RBRACE"})
            self.expect("RBRACE")
        return If(cond, then, orelse)

    def parse_simple_stmt(self) -> Stmt:
        first = self.expect("NAME").value
        names = [first]
        while self.at("COMMA"):
            self.advance()
            names.append(self.expect("NAME").value)
        if self.at("ASSIGN"):
            self.advance()
            rhs = [self.parse_expr()]
            while self.at("COMMA"):
                self.advance()
                rhs.append(self.parse_expr())
            self.expect("SEMI")
            return MultiAssign(names, rhs)
        if len(names) != 1:
            raise SyntaxError(f"Unexpected comma-list before '+='/'-=' at token {self.i}")
        if self.at("PLUSEQ"):
            self.advance()
            e = self.parse_expr()
            self.expect("SEMI")
            return Incr(names[0], e)
        if self.at("MINUSEQ"):
            self.advance()
            e = self.parse_expr()
            self.expect("SEMI")
            return Incr(names[0], ("neg", e))
        raise SyntaxError(f"Expected ':=', '+=' or '-=' after {names} at token {self.i}")

    # ---- conditions ----------------------------------------------------
    def parse_cond(self) -> Cond:
        left = self.parse_cond_and()
        while self.at("OR"):
            self.advance()
            right = self.parse_cond_and()
            left = ("or", left, right)
        return left

    def parse_cond_and(self) -> Cond:
        left = self.parse_cond_atom()
        while self.at("AND"):
            self.advance()
            right = self.parse_cond_atom()
            left = ("and", left, right)
        return left

    def parse_cond_atom(self) -> Cond:
        if self.at("NOT"):
            self.advance()
            self.expect("LPAREN")
            c = self.parse_cond()
            self.expect("RPAREN")
            return ("not", c)
        if self.at("LPAREN"):
            # could be a parenthesized condition OR a parenthesized arithmetic expr
            # followed by a comparison; try condition first by lookahead copy.
            save = self.i
            self.advance()
            try:
                c = self.parse_cond()
                self.expect("RPAREN")
                return c
            except SyntaxError:
                self.i = save
        lhs = self.parse_expr()
        op_tok = self.advance()
        op_map = {
            "EQ": "==",
            "NEQ": "!=",
            "LT": "<",
            "GT": ">",
            "LEQ": "<=",
            "GEQ": ">=",
        }
        if op_tok.kind not in op_map:
            raise SyntaxError(f"Expected comparison operator, got {op_tok.kind} at token {self.i}")
        rhs = self.parse_expr()
        return ("cmp", op_map[op_tok.kind], lhs, rhs)

    # ---- arithmetic expressions -----------------------------------------
    def parse_expr(self) -> Expr:
        return self.parse_add()

    def parse_add(self) -> Expr:
        left = self.parse_mul()
        while self.at("PLUS") or self.at("MINUS"):
            op = self.advance().kind
            right = self.parse_mul()
            left = ("bin", "+" if op == "PLUS" else "-", left, right)
        return left

    def parse_mul(self) -> Expr:
        left = self.parse_unary()
        while self.at("STAR") or self.at("SLASH"):
            op = self.advance().kind
            right = self.parse_unary()
            left = ("bin", "*" if op == "STAR" else "/", left, right)
        return left

    def parse_unary(self) -> Expr:
        if self.at("MINUS"):
            self.advance()
            return ("neg", self.parse_unary())
        if self.at("PLUS"):
            self.advance()
            return self.parse_unary()
        return self.parse_atom()

    def parse_atom(self) -> Expr:
        tok = self.peek()
        if tok.kind == "NUMBER":
            self.advance()
            return ("num", tok.value)
        if tok.kind == "LPAREN":
            self.advance()
            e = self.parse_expr()
            self.expect("RPAREN")
            return e
        if tok.kind in ("CLAMP", "FLIP"):
            fname = self.advance().kind.lower()
            self.expect("LPAREN")
            args = [self.parse_expr()]
            while self.at("COMMA"):
                self.advance()
                args.append(self.parse_expr())
            self.expect("RPAREN")
            return ("call", fname, args)
        if tok.kind == "NAME":
            self.advance()
            return ("var", tok.value)
        raise SyntaxError(f"Unexpected token {tok.kind} ({tok.value!r}) in expression at {self.i}")


def parse_pwhiledt(src: str) -> Program:
    return Parser(tokenize(src)).parse_program()


# ---------------------------------------------------------------------------
# Identifier mangling
# ---------------------------------------------------------------------------

# Reserved regardless of sympify: Polar's distribution/type names (always start with an
# uppercase letter so a *lowercase* clash isn't possible there), Polar's builtin FUNC_NAMEs, and
# its default iteration-counter variable (`k`, see cli/argument_parser.py).
POLAR_RESERVED_LOWER = {"sin", "cos", "exp", "k"}


def _is_safe_identifier(name: str) -> bool:
    if not name.islower():
        return False
    if name in POLAR_RESERVED_LOWER:
        return False
    if sympy is None:
        return True
    try:
        val = sympy.sympify(name)
    except Exception:
        return False
    return isinstance(val, sympy.Symbol)


class NameMangler:
    """Maps every pWhileDt identifier to a Polar-safe lowercase identifier, renaming only the
    ones that actually need it (collide with Polar's lexer conventions or sympy's default
    namespace) so the emitted .prob file stays readable."""

    def __init__(self):
        self._map: dict[str, str] = {}
        self._used: set[str] = set()

    def get(self, name: str) -> str:
        if name in self._map:
            return self._map[name]
        candidate = name.lower()
        if _is_safe_identifier(candidate) and candidate not in self._used:
            safe = candidate
        else:
            safe = f"v_{candidate}"
            n = 2
            while not _is_safe_identifier(safe) or safe in self._used:
                safe = f"v_{candidate}_{n}"
                n += 1
        self._map[name] = safe
        self._used.add(safe)
        return safe

    def table(self) -> List[Tuple[str, str]]:
        return sorted(self._map.items())


# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------


class TranslationError(Exception):
    pass


def _contains_db(e: Expr) -> bool:
    if e[0] == "var":
        return e[1] == "db"
    if e[0] == "neg":
        return _contains_db(e[1])
    if e[0] == "bin":
        return _contains_db(e[2]) or _contains_db(e[3])
    if e[0] == "call":
        return any(_contains_db(a) for a in e[2])
    return False


def _strip_db(e: Expr) -> Expr:
    """Replace the `db` leaf with the constant 1, extracting a diffuse atom's coefficient."""
    if e[0] == "var" and e[1] == "db":
        return ("num", "1")
    if e[0] == "neg":
        return ("neg", _strip_db(e[1]))
    if e[0] == "bin":
        return ("bin", e[1], _strip_db(e[2]), _strip_db(e[3]))
    if e[0] == "call":
        return ("call", e[1], [_strip_db(a) for a in e[2]])
    return e


class CodeGen:
    def __init__(self, mangler: NameMangler):
        self.m = mangler

    def render_expr(self, e: Expr) -> str:
        if e[0] == "num":
            return e[1]
        if e[0] == "var":
            return self.m.get(e[1])
        if e[0] == "neg":
            return f"(-{self.render_expr(e[1])})"
        if e[0] == "bin":
            return f"({self.render_expr(e[2])}{e[1]}{self.render_expr(e[3])})"
        if e[0] == "call":
            raise TranslationError(
                f"'{e[1]}' may only appear directly on the right of a single-variable "
                f"assignment (`x := {e[1]}(...);`), not nested inside a larger expression"
            )
        raise TranslationError(f"Unhandled expression node {e!r}")

    def render_cond(self, c: Cond) -> str:
        if c[0] == "cmp":
            op = "/=" if c[1] == "!=" else c[1]
            return f"{self.render_expr(c[2])} {op} {self.render_expr(c[3])}"
        if c[0] == "and":
            return f"({self.render_cond(c[1])}) && ({self.render_cond(c[2])})"
        if c[0] == "or":
            return f"({self.render_cond(c[1])}) || ({self.render_cond(c[2])})"
        if c[0] == "not":
            return f"!({self.render_cond(c[1])})"
        raise TranslationError(f"Unhandled condition node {c!r}")

    # ---- statements -----------------------------------------------------
    def gen_stmts(self, stmts: List[Stmt], indent: int) -> List[str]:
        lines: List[str] = []
        for s in stmts:
            lines.extend(self.gen_stmt(s, indent))
        return lines

    def gen_stmt(self, s: Stmt, indent: int) -> List[str]:
        pad = "    " * indent
        if isinstance(s, Skip):
            return []
        if isinstance(s, MultiAssign):
            return self._gen_assign(s, pad)
        if isinstance(s, Incr):
            return self._gen_incr(s, pad)
        if isinstance(s, If):
            return self._gen_if(s, indent)
        if isinstance(s, While):
            raise TranslationError("Nested while loops are not supported by this translator")
        raise TranslationError(f"Unhandled statement {s!r}")

    def _gen_assign(self, s: MultiAssign, pad: str) -> List[str]:
        # clamp(...) / flip(...) must be the sole RHS of a single-variable assignment.
        if len(s.lhs) == 1 and len(s.rhs) == 1 and s.rhs[0][0] == "call":
            return self._gen_call_assign(s.lhs[0], s.rhs[0], pad)
        for r in s.rhs:
            if r[0] == "call":
                raise TranslationError(f"Unsupported call {r[1]} inside a multi-assign")
        lhs = [self.m.get(v) for v in s.lhs]
        if len(s.rhs) == 1 and len(s.lhs) > 1:
            rhs_txt = self.render_expr(s.rhs[0])
            return [f"{pad}{', '.join(lhs)} = {', '.join([rhs_txt] * len(lhs))}"]
        if len(s.rhs) != len(s.lhs):
            raise TranslationError(f"Assignment arity mismatch: {s.lhs} := {s.rhs}")
        rhs = [self.render_expr(r) for r in s.rhs]
        return [f"{pad}{', '.join(lhs)} = {', '.join(rhs)}"]

    def _gen_call_assign(self, var: str, call: Expr, pad: str) -> List[str]:
        _, fname, args = call
        v = self.m.get(var)
        if fname == "flip":
            if len(args) != 1:
                raise TranslationError("flip(p) expects exactly one argument")
            p = self.render_expr(args[0])
            return [f"{pad}{v} = 1 {{{p}}} 0"]
        if fname == "clamp":
            if len(args) != 3:
                raise TranslationError("clamp(e,a,b) expects exactly three arguments")
            e, a, b = (self.render_expr(a) for a in args)
            return [
                f"{pad}if {e} > {b}:",
                f"{pad}    {v} = {b}",
                f"{pad}elif {e} < {a}:",
                f"{pad}    {v} = {a}",
                f"{pad}else:",
                f"{pad}    {v} = {e}",
                f"{pad}end",
            ]
        raise TranslationError(f"Unsupported call {fname}")

    def _gen_incr(self, s: Incr, pad: str) -> List[str]:
        v = self.m.get(s.var)
        if _contains_db(s.expr):
            coeff = self.render_expr(_strip_db(s.expr))
            return [
                f"{pad}{v} = {v} + {coeff}*dt**(1/2) {{1/2}} {v} - {coeff}*dt**(1/2)"
            ]
        e = self.render_expr(s.expr)
        return [f"{pad}{v} = {v} + {e}"]

    def _gen_if(self, s: If, indent: int) -> List[str]:
        pad = "    " * indent
        lines = [f"{pad}if {self.render_cond(s.cond)}:"]
        lines.extend(self.gen_stmts(s.then, indent + 1))
        if s.orelse:
            lines.append(f"{pad}else:")
            lines.extend(self.gen_stmts(s.orelse, indent + 1))
        lines.append(f"{pad}end")
        return lines


def translate(src: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Translate pWhileDt source text to a Polar .prob program.

    Returns (prob_source, mangling_table). The loop's clock guard (`t < T`) is emitted literally
    (see module docstring: Polar's `ost-extension` branch can now solve a purely deterministic
    guard like this for its exact crossing iteration count -- pass `--solve_deterministic_guards`
    when running polar.py on the result). `T`/`dt` can be left symbolic, in which case Polar still
    produces the general closed form in terms of its own iteration counter and the guard solve is
    simply not applied to a concrete `n`; substitute `n = T/dt` by hand in that case, same as
    before.
    """
    program = parse_pwhiledt(src)
    # Reject anything but a single top-level while loop (every example in this paper's addendum
    # has exactly one: an `initial` block of plain assignments, then one `while (t<T) {...}`).
    while_stmts = [s for s in program.body if isinstance(s, While)]
    if len(while_stmts) != 1 or program.body[-1] is not while_stmts[0]:
        raise TranslationError(
            "Expected exactly one top-level `while` as the program's final statement"
        )
    initial = program.body[:-1]
    loop = while_stmts[0]

    mangler = NameMangler()
    gen = CodeGen(mangler)

    lines: List[str] = []
    lines.extend(gen.gen_stmts(initial, indent=0))
    lines.append(f"while {gen.render_cond(loop.cond)}:")
    lines.extend(gen.gen_stmts(loop.body, indent=1))
    lines.append("end")
    return "\n".join(lines) + "\n", mangler.table()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="pWhileDt source file")
    ap.add_argument("-o", "--output", help="Polar .prob output path (default: stdout)")
    args = ap.parse_args(argv)

    with open(args.input) as f:
        src = f.read()

    try:
        prob_src, table = translate(src)
    except (SyntaxError, TranslationError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.output:
        with open(args.output, "w") as f:
            f.write(prob_src)
    else:
        sys.stdout.write(prob_src)

    renamed = [(a, b) for a, b in table if a.lower() != b]
    if renamed:
        print("# renamed to avoid Polar/sympy identifier clashes:", file=sys.stderr)
        for a, b in renamed:
            print(f"#   {a} -> {b}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# TODO: examples with a genuinely random exit guard (a threshold on a diffusing/absorbing
# variable, e.g. the controlled-diffusion or sticky-point escape examples) are out of scope for
# this translator today -- they'd need Polar's --ost machinery, not --solve_deterministic_guards,
# and more fundamentally hit the unrelated state-dependent-branching limitation documented in
# README.md before that. Not attempted here.
