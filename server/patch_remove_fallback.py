from pathlib import Path
f=Path(r'custom_addons/event_application/views/event_website_templates.xml')
text=f.read_text()
old="""                        <t t-else="">
                            <div class="carousel-item active">
                                <img src="data:image/jpg;base64,/9j/"""  # start of huge base64

idx=text.find(old)
if idx==-1:
    raise SystemExit('fallback start not found')
end=text.find('</div>\n                        </t>', idx)
if end==-1:
    raise SystemExit('end not found')
# replace chunk from old start to end+len
new="""                        <t t-else="">
                            <div class=\"carousel-item active\">\n                                <img src=\"/web/static/img/placeholder.png\" class=\"d-block w-100\" style=\"max-height:420px;object-fit:cover;\" alt=\"Event image\"/>\n                            </div>\n                        </t>"""
text=text[:idx]+new+text[end+len('</div>\n                        </t>'):]
f.write_text(text)
