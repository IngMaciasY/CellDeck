"""Modelos de ``config.json``: apariencia, páginas, botones y widgets.

Las acciones de los botones se validan delegando en el :class:`PluginRegistry`, que se
pasa en el contexto de validación::

    Config.model_validate(data, context={"registry": registry})
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
    ValidationInfo,
    field_validator,
    model_validator,
)

from phonedeck.plugins.base import ActionParams, validate_action_value

ID_PATTERN = r"^[A-Za-z0-9_-]{1,40}$"
HEX_COLOR = r"^#[0-9A-Fa-f]{6}$"
ICON_PATTERN = r"^[a-z0-9-]{1,40}$"

WidgetKind = Literal["clock", "stats", "now_playing", "volume", "mixer", "pomodoro", "obs"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ButtonItem(_Model):
    """Botón que ejecuta una acción."""

    kind: Literal["button"]
    id: str = Field(pattern=ID_PATTERN)
    label: str = Field(default="", max_length=40)
    icon: str | None = Field(default=None, pattern=ICON_PATTERN)
    color: str | None = Field(default=None, pattern=HEX_COLOR)
    w: int = Field(default=1, ge=1, le=4)
    h: int = Field(default=1, ge=1, le=4)
    confirm: bool = False
    action: SerializeAsAny[ActionParams]

    @field_validator("action", mode="before")
    @classmethod
    def _validate_action(cls, value: Any, info: ValidationInfo) -> ActionParams:
        return validate_action_value(value, info)


class WidgetItem(_Model):
    """Widget en vivo (reloj, CPU/RAM, ahora suena, volumen, mezclador, Pomodoro, OBS)."""

    kind: Literal["widget"]
    id: str = Field(pattern=ID_PATTERN)
    widget: WidgetKind
    label: str = Field(default="", max_length=40)
    color: str | None = Field(default=None, pattern=HEX_COLOR)
    w: int = Field(default=1, ge=1, le=6)
    h: int = Field(default=1, ge=1, le=4)
    options: dict[str, str | int | float | bool] = Field(default_factory=dict, max_length=20)


Item = Annotated[ButtonItem | WidgetItem, Field(discriminator="kind")]


class Page(_Model):
    """Página (pestaña) con su grid de elementos."""

    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=30)
    icon: str | None = Field(default=None, pattern=ICON_PATTERN)
    items: list[Item] = Field(default_factory=list, max_length=60)

    @model_validator(mode="after")
    def _unique_item_ids(self) -> Self:
        seen: set[str] = set()
        for item in self.items:
            if item.id in seen:
                raise ValueError(f"ID de elemento repetido en la página '{self.id}': '{item.id}'")
            seen.add(item.id)
        return self


class Appearance(_Model):
    theme: Literal["dark", "light", "oled"] = "dark"
    accent: str = Field(default="#4f8cff", pattern=HEX_COLOR)
    # "auto": columnas calculadas con el ancho de cada pantalla y ``button_size``
    #         (sirve igual para un celular viejo, uno nuevo o una tablet).
    # "fixed": columnas fijas ``columns_portrait`` / ``columns_landscape``.
    layout: Literal["auto", "fixed"] = "auto"
    button_size: int = Field(default=104, ge=64, le=220, description="Tamaño ideal en px CSS")
    columns_portrait: int = Field(default=3, ge=2, le=8)
    columns_landscape: int = Field(default=6, ge=3, le=12)
    show_labels: bool = True


class Config(_Model):
    """Raíz de ``config.json``."""

    version: Literal[1] = 1
    appearance: Appearance = Field(default_factory=Appearance)
    pages: list[Page] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def _unique_page_ids(self) -> Self:
        seen: set[str] = set()
        for page in self.pages:
            if page.id in seen:
                raise ValueError(f"ID de página repetido: '{page.id}'")
            seen.add(page.id)
        return self

    def has_widget(self, widget: str) -> bool:
        """``True`` si algún widget de ese tipo existe en alguna página."""
        return any(
            isinstance(item, WidgetItem) and item.widget == widget
            for page in self.pages
            for item in page.items
        )

    def find_page(self, page_id: str) -> Page | None:
        return next((p for p in self.pages if p.id == page_id), None)

    def find_item(self, page_id: str, item_id: str) -> ButtonItem | WidgetItem | None:
        page = self.find_page(page_id)
        if page is None:
            return None
        return next((i for i in page.items if i.id == item_id), None)

    def to_json_dict(self) -> dict[str, Any]:
        """Representación JSON (la que se guarda y se envía al celular)."""
        return self.model_dump(mode="json", exclude_none=True)
