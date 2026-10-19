# Minimal JSON5 → Python for Chromium's runtime_enabled_features.json5 (comments, unquoted keys, trailing commas)
import json, re, sys

def to_json(src):
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == '"' or c == "'":
            q = c; j = i + 1
            while src[j] != q:
                j += 2 if src[j] == '\\' else 1
            s = src[i + 1:j]
            out.append(json.dumps(s.encode().decode('unicode_escape') if '\\' in s else s)); i = j + 1
        elif src.startswith('//', i):
            j = src.find('\n', i); i = n if j < 0 else j
        elif src.startswith('/*', i):
            i = src.find('*/', i) + 2
        elif c.isalpha() or c == '_':
            m = re.match(r'[A-Za-z_][A-Za-z0-9_]*', src[i:]); w = m.group(0); i += len(w)
            k = i
            while k < n and src[k] in ' \t\r\n': k += 1
            if k < n and src[k] == ':': out.append(json.dumps(w))
            else: out.append(w)  # true/false/null
        else:
            out.append(c); i += 1
    s = ''.join(out)
    s = re.sub(r',(\s*[\]}])', r'\1', s)
    return s

def load(path):
    return json.loads(to_json(open(path, encoding='utf-8').read()))

if __name__ == '__main__':
    d = load(sys.argv[1]); print(len(d['data']))
