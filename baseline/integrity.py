"""Conservative lexical trust guard plus Lynette's Verus AST comparison."""
from collections import Counter
import re

from .verifier import execute

FORBIDDEN = {"assume", "admit", "axiom", "external", "external_body", "unsafe",
             "assume_specification", "assume_specification_for", "assume_new", "unimplemented",
             "todo", "macro_rules", "global_size_of", "assume_termination", "assume_false"}

POLICY = "proof-triggers-v4"


def is_trigger_attribute(item):
    """Only the trigger annotations needed by the experiments; not verifier::*.

    Real Verus still parses/checks the unchanged candidate, and Lynette checks
    the complete AST. This exemption alone never accepts a candidate.
    """
    if item in (("#", "[", "trigger", "]"), ("#", "!", "[", "auto", "]")):
        return True
    return (len(item) == 7 and item[:4] == ("#", "[", "trigger", "(")
            and item[4].isdigit() and item[5:] == (")", "]"))


def tokens(code):
    """Skip nested comments; keep string/character literals atomic."""
    out, i = [], 0
    while i < len(code):
        if code[i].isspace():
            i += 1
        elif code.startswith("//", i):
            end = code.find("\n", i)
            i = len(code) if end < 0 else end + 1
        elif code.startswith("/*", i):
            depth, i = 1, i + 2
            while i < len(code) and depth:
                if code.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif code.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
            if depth:
                raise ValueError("Unclosed comment")
        else:
            raw = re.match(r'(?:br|r)(#*)"', code[i:])
            if raw:
                ending = '"' + raw[1]
                end = code.find(ending, i + len(raw[0]))
                if end < 0:
                    raise ValueError("Unclosed raw string")
                end += len(ending)
                out.append(code[i:end])
                i = end
                continue
            match = re.match(r'''(?:b?"(?:\\.|[^"\\])*"|b?'(?:\\.|[^'\\])'|(?:r\#)?[A-Za-z_][A-Za-z_0-9]*|[0-9]+|.)''', code[i:], re.S)
            if not match:
                raise ValueError("Unsupported source token")
            out.append(match[0])
            i += len(match[0])
    return out


def group_end(ts, start):
    pairs = {"[": "]", "(": ")", "{": "}"}
    stack = []
    for i in range(start, len(ts)):
        if ts[i] in pairs:
            stack.append(pairs[ts[i]])
        elif ts[i] in pairs.values():
            if not stack or ts[i] != stack.pop():
                raise ValueError("Unbalanced delimiters")
            if not stack:
                return i + 1
    raise ValueError("Unclosed delimiter")


def protected(ts):
    attrs, macros, imports = [], [], []
    for i, token in enumerate(ts):
        if token == "#":
            start = i + 2 if ts[i + 1:i + 2] == ["!"] else i + 1
            if ts[start:start + 1] == ["["]:
                attrs.append(tuple(ts[i:group_end(ts, start)]))
        if token == "use":
            end = ts.index(";", i)
            imports.append(tuple(ts[i:end + 1]))
        if (token == "!" and i and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", ts[i - 1])
                and ts[i - 1] != "verus" and ts[i + 1:i + 2] in (["("], ["["], ["{"])):
            macros.append(tuple(ts[i - 1:group_end(ts, i + 1)]))
    return tuple(Counter(x) for x in (attrs, macros, imports))


def lexical_check(original, candidate):
    ts = tokens(candidate)
    banned = sorted({t.removeprefix("r#") for t in ts} & FORBIDDEN)
    if banned:
        return False, "Forbidden trusted/bypass construct: " + ", ".join(banned)
    labels = ("attributes", "non-Verus macros", "imports")
    for label, before, after in zip(labels, protected(tokens(original)), protected(ts)):
        if label == "attributes":
            # Existing original attributes must remain. Only additional trigger
            # annotations are exempt; contracts/exec are still compared by AST.
            after = after.copy()
            for item, count in (after - before).items():
                if is_trigger_attribute(item):
                    after[item] -= count
        if before != after:
            removed = [" ".join(item) for item in (before - after)]
            added = [" ".join(item) for item in (after - before)]
            return False, (f"Changed {label} (conservative policy). "
                           f"Restore removed original items: {removed}. Remove added items: {added}.")
    return True, ""


class IntegrityValidator:
    def __init__(self, executable, timeout=30):
        self.executable = executable
        self.timeout = timeout

    def validate(self, original, candidate):
        try:
            valid, reason = lexical_check(original.read_text(encoding="utf-8"),
                                          candidate.read_text(encoding="utf-8"))
        except (ValueError, IndexError) as error:
            return {"valid": False, "status": "unparseable", "reason": str(error), "seconds": 0}
        if not valid:
            return {"valid": False, "status": "invalid", "reason": reason, "seconds": 0}
        result = execute([self.executable, "additions", str(original.resolve()),
                          str(candidate.resolve())], self.timeout)
        result["valid"] = result["returncode"] == 0 and not result["timed_out"]
        result["reason"] = result["stdout"] + result["stderr"]
        if result["valid"]:
            status = "valid"
        elif result["timed_out"] or "panicked" in result["reason"]:
            status = "checker_error"
        elif "Unable to parse" in result["reason"]:
            status = "unparseable"
        elif "Disallowed" in result["reason"] or "Unsafe change" in result["reason"]:
            status = "invalid"
        else:
            status = "checker_error"
        result["status"] = status
        return result
