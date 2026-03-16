import pathlib, re
missing=[]
for path in pathlib.Path('.').rglob('*.xml'):
    if '.venv' in str(path) or 'doc' in str(path.parts):
        continue
    text = path.read_text(errors='ignore')
    ids={m.group(1) for m in re.finditer(r'id="([^"]+)"',text)}
    for_attr=[m.group(1) for m in re.finditer(r'for="([^"]+)"',text)]
    for f in for_attr:
        if f not in ids:
            missing.append((str(path), f))
print(len(missing))
print(missing[:10])
