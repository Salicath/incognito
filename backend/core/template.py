from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from backend.core.profile import Profile


class TemplateRenderer:
    def __init__(self, templates_dir: Path):
        self._env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape([]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, template_name: str, *, profile: Profile, **kwargs) -> str:
        template = self._env.get_template(f"{template_name}.txt.j2")
        return template.render(profile=profile, **kwargs)

    def render_localized(
        self, template_name: str, language: str, *, profile: Profile, **kwargs
    ) -> str:
        try:
            template = self._env.get_template(f"locales/{language}/{template_name}.txt.j2")
        except Exception:
            template = self._env.get_template(f"{template_name}.txt.j2")
        return template.render(profile=profile, **kwargs)
