import pathlib
for path in pathlib.Path('custom_addons/event_application').rglob('*.xml'):
    text=path.read_text()
    if 'name="badge_image"' in text:
        for i,line in enumerate(text.splitlines(),1):
            if 'name="badge_image"' in line:
                print(path, i, line.strip())
