from pathlib import Path

from jinja2 import (
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    TemplateNotFound,
    select_autoescape,
)

from backend.core.profile import Profile


class TemplateRenderer:
    def __init__(self, templates_dir: Path, fallback_dir: Path | None = None):
        """fallback_dir: the repo templates — a user-customized templates_dir
        (data_dir/templates) predating a release would otherwise 500 on every
        template added since they copied it."""
        loader: FileSystemLoader | ChoiceLoader = FileSystemLoader(str(templates_dir))
        if fallback_dir is not None and fallback_dir != templates_dir:
            loader = ChoiceLoader([loader, FileSystemLoader(str(fallback_dir))])
        self._env = Environment(
            loader=loader,
            autoescape=select_autoescape(["html", "xml"]),
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
        except TemplateNotFound:
            template = self._env.get_template(f"{template_name}.txt.j2")
        return template.render(profile=profile, **kwargs)
