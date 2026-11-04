"""
Design tokens e gerenciamento de tema (Light / Dark).

Fonte única de verdade para cores, dimensões, espaçamentos e tipografia.
O styles.qss usa marcadores {{token}} que são preenchidos aqui; nenhum outro
arquivo define cor ou tamanho "na mão".
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from . import icons

ORGANIZACAO = "TCM"
APLICACAO = "MesclarPDFs"
QSS_PATH = Path(__file__).with_name("styles.qss")

# ---------------------------------------------------------------------------
# Cores de identidade: iguais nos dois temas.
# ---------------------------------------------------------------------------
BRAND = {
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "primary_pressed": "#1E40AF",
    "on_primary": "#FFFFFF",
    "danger": "#DC2626",
    "danger_hover": "#B91C1C",
    "danger_pressed": "#991B1B",
    "success": "#16A34A",
    "warning": "#D97706",  # status "aviso" (gerado, mas requer conferência)
}

# ---------------------------------------------------------------------------
# Cores neutras: as únicas que mudam entre os temas.
#   bg_app   -> área de conteúdo        surface -> sidebar, header, modais
#   card     -> cards                   *_subtle -> fundos de badges/seleção
# ---------------------------------------------------------------------------
NEUTRALS = {
    "light": {
        "bg": "#FFFFFF",
        "bg_secondary": "#F9FAFB",
        "bg_app": "#F9FAFB",
        "surface": "#FFFFFF",
        "card": "#FFFFFF",
        "text": "#111827",
        "text_muted": "#6B7280",
        "text_disabled": "#9CA3AF",
        "placeholder": "#9CA3AF",
        "border": "#E5E7EB",
        "border_strong": "#D1D5DB",
        "hover": "#F3F4F6",
        "pressed": "#E5E7EB",
        "input_bg": "#FFFFFF",
        "disabled_bg": "#F3F4F6",
        "focus_ring": "#93C5FD",
        "scrollbar": "#D1D5DB",
        "primary_subtle": "#EFF6FF",
        "success_subtle": "#F0FDF4",
        "warning_subtle": "#FFFBEB",
        "danger_subtle": "#FEF2F2",
    },
    "dark": {
        "bg": "#111827",
        "bg_secondary": "#1F2937",
        "bg_app": "#111827",
        "surface": "#1F2937",
        "card": "#1F2937",
        "text": "#F9FAFB",
        "text_muted": "#9CA3AF",
        "text_disabled": "#6B7280",
        "placeholder": "#6B7280",
        "border": "#374151",
        "border_strong": "#4B5563",
        "hover": "#374151",
        "pressed": "#4B5563",
        "input_bg": "#111827",
        "disabled_bg": "#1F2937",
        "focus_ring": "#1D4ED8",
        "scrollbar": "#4B5563",
        "primary_subtle": "#203357",
        "success_subtle": "#1D3F3A",
        "warning_subtle": "#40372E",
        "danger_subtle": "#412834",
    },
}

# ---------------------------------------------------------------------------
# Dimensões (px)
# ---------------------------------------------------------------------------
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}

SIZE = {
    "button_sm": 32,
    "button_md": 40,
    "button_lg": 48,
    "input": 42,
    "textarea_min": 100,
    "checkbox": 18,
    "sidebar": 240,
    "header": 64,
    "modal": 480,
    "card_padding": 20,
    "table_row": 44,
    "icon_sm": 18,
    "icon_md": 20,
    "badge": 22,
    "progress": 8,
}

RADIUS = {"control": 8, "card": 12, "small": 6, "badge": 11, "progress": 4}

FONT = {
    "base": 13,
    "label": 12,
    "small": 11,
    "section": 15,
    "header": 20,
    "title": 24,
    "stat": 28,
}

FONT_CANDIDATES = ("Inter", "Segoe UI", "SF Pro Text", ".AppleSystemUIFont", "Helvetica Neue", "Arial")

_TOKEN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def font_family() -> str:
    disponiveis = set(QFontDatabase.families())
    for familia in FONT_CANDIDATES:
        if familia in disponiveis:
            return familia
    return QApplication.font().family()


class ThemeManager(QObject):
    """Aplica o tema na aplicação inteira e avisa os componentes quando ele muda."""

    changed = Signal(str)

    def __init__(self):
        super().__init__()
        self._settings = QSettings(ORGANIZACAO, APLICACAO)
        tema = self._settings.value("aparencia/tema", "light")
        self._theme = tema if tema in NEUTRALS else "light"

    # -- leitura ----------------------------------------------------------
    @property
    def theme(self) -> str:
        return self._theme

    @property
    def is_dark(self) -> bool:
        return self._theme == "dark"

    def colors(self) -> dict[str, str]:
        return {**NEUTRALS[self._theme], **BRAND}

    def color(self, token: str) -> str:
        return self.colors()[token]

    def tokens(self) -> dict[str, str]:
        t = dict(self.colors())
        t.update({f"space_{k}": f"{v}px" for k, v in SPACE.items()})
        t.update({f"size_{k}": f"{v}px" for k, v in SIZE.items()})
        t.update({f"radius_{k}": f"{v}px" for k, v in RADIUS.items()})
        t.update({f"font_{k}": f"{v}px" for k, v in FONT.items()})
        t["font_family"] = font_family()
        t["icon_check"] = icons.svg_file("check", BRAND["on_primary"], 14)
        t["icon_chevron"] = icons.svg_file("chevron-down", t["text_muted"], 16)
        t["icon_chevron_disabled"] = icons.svg_file("chevron-down", t["text_disabled"], 16)
        return t

    def stylesheet(self) -> str:
        tokens = self.tokens()

        def trocar(m: re.Match) -> str:
            nome = m.group(1)
            if nome not in tokens:
                raise KeyError(f"Token desconhecido no styles.qss: {{{{{nome}}}}}")
            return tokens[nome]

        return _TOKEN.sub(trocar, QSS_PATH.read_text(encoding="utf-8"))

    def palette(self) -> QPalette:
        c = {k: QColor(v) for k, v in self.colors().items()}
        p = QPalette()
        p.setColor(QPalette.ColorRole.Window, c["bg_app"])
        p.setColor(QPalette.ColorRole.WindowText, c["text"])
        p.setColor(QPalette.ColorRole.Base, c["input_bg"])
        p.setColor(QPalette.ColorRole.AlternateBase, c["hover"])
        p.setColor(QPalette.ColorRole.Text, c["text"])
        p.setColor(QPalette.ColorRole.Button, c["card"])
        p.setColor(QPalette.ColorRole.ButtonText, c["text"])
        p.setColor(QPalette.ColorRole.PlaceholderText, c["placeholder"])
        p.setColor(QPalette.ColorRole.Highlight, c["primary"])
        p.setColor(QPalette.ColorRole.HighlightedText, c["on_primary"])
        p.setColor(QPalette.ColorRole.ToolTipBase, c["text"])
        p.setColor(QPalette.ColorRole.ToolTipText, c["bg"])
        p.setColor(QPalette.ColorRole.Link, c["primary"])
        for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
            p.setColor(QPalette.ColorGroup.Disabled, role, c["text_disabled"])
        return p

    # -- escrita ----------------------------------------------------------
    def apply(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        if app.style().name().lower() != "fusion":
            app.setStyle("Fusion")  # base idêntica no Windows e no macOS
        fonte = QFont(font_family())
        fonte.setPixelSize(FONT["base"])
        app.setFont(fonte)
        app.setPalette(self.palette())
        app.setStyleSheet(self.stylesheet())

    def set_theme(self, theme: str) -> None:
        if theme not in NEUTRALS or theme == self._theme:
            return
        self._theme = theme
        self._settings.setValue("aparencia/tema", theme)
        self.apply()
        self.changed.emit(theme)

    def toggle(self) -> None:
        self.set_theme("light" if self.is_dark else "dark")


theme_manager = ThemeManager()
