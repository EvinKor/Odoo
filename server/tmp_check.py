import re, pathlib
p=pathlib.Path('custom_addons/event_application/views/event_application_views.xml').read_text()
labels=re.findall(r'<label[^>]*for="([^"]+)"', p)
ids=set(re.findall(r'id="([^"]+)"', p))
missing=[f for f in labels if f not in ids]
print('labels', len(labels), 'missing', len(missing))
print(sorted(set(missing))[:50])
