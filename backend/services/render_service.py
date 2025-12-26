from fastapi import Request
from app.core.templates import templates

def render_html(request: Request, content: dict):
    template_name = content.get("template", "template1.html")
    return templates.TemplateResponse(template_name, {"request": request, **content})

