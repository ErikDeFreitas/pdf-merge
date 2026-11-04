"""
Componentes reutilizáveis do Design System.

Regras:
- Nenhum estilo inline: a aparência vem do styles.qss, selecionada por
  propriedades dinâmicas (variant, size, role, tone, card, error...).
- Alturas e espaçamentos vêm de themes.SIZE / themes.SPACE.
- Componentes com ícone se recolorem sozinhos quando o tema muda.
"""
from __future__ import annotations

from typing import Iterable, Union

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QLineEdit,
    QListView,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .themes import SIZE, SPACE, theme_manager


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------
def repolish(widget: QWidget) -> None:
    """Reaplica o QSS depois de mudar uma propriedade dinâmica."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def set_prop(widget: QWidget, name: str, value) -> None:
    widget.setProperty(name, value)
    repolish(widget)


def themed_icon(name: str, color: str, size: int = SIZE["icon_sm"],
                checked_color: str | None = None) -> QIcon:
    """QIcon com estados normal, desabilitado e (opcional) marcado."""
    ic = QIcon()
    ic.addPixmap(icons.pixmap(name, theme_manager.color(color), size), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(icons.pixmap(name, theme_manager.color("text_disabled"), size), QIcon.Mode.Disabled, QIcon.State.Off)
    if checked_color:
        ic.addPixmap(icons.pixmap(name, theme_manager.color(checked_color), size), QIcon.Mode.Normal, QIcon.State.On)
    return ic


Item = Union[QWidget, QLayout, int, None]


def _fill(layout: QHBoxLayout | QVBoxLayout, items: Iterable[Item]) -> None:
    """None = espaço elástico, int = espaçamento fixo, widget/layout = item."""
    for item in items:
        if item is None:
            layout.addStretch(1)
        elif isinstance(item, int):
            layout.addSpacing(item)
        elif isinstance(item, QLayout):
            layout.addLayout(item)
        else:
            layout.addWidget(item)


def hbox(*items: Item, spacing: int = SPACE["md"], margins: int = 0) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(spacing)
    layout.setContentsMargins(margins, margins, margins, margins)
    _fill(layout, items)
    return layout


def vbox(*items: Item, spacing: int = SPACE["md"], margins: int = 0) -> QVBoxLayout:
    layout = QVBoxLayout()
    layout.setSpacing(spacing)
    layout.setContentsMargins(margins, margins, margins, margins)
    _fill(layout, items)
    return layout


# ---------------------------------------------------------------------------
# Tipografia e ícones
# ---------------------------------------------------------------------------
class Label(QLabel):
    """role: body | title | header_title | section | brand | muted | label | hint | overline | stat"""

    def __init__(self, text: str = "", role: str = "body", wrap: bool = False, parent=None):
        super().__init__(text, parent)
        self.setProperty("role", role)
        self.setWordWrap(wrap)


class Icon(QLabel):
    """Ícone SVG colorido por um token do tema (ex.: 'primary', 'text_muted')."""

    def __init__(self, name: str, color: str = "text_muted", size: int = SIZE["icon_md"], parent=None):
        super().__init__(parent)
        self._name, self._color, self._size = name, color, size
        self.setFixedSize(size, size)
        theme_manager.changed.connect(self._refresh)
        self._refresh()

    def set_icon(self, name: str | None = None, color: str | None = None) -> None:
        self._name = name or self._name
        self._color = color or self._color
        self._refresh()

    def _refresh(self, *_):
        self.setPixmap(icons.pixmap(self._name, theme_manager.color(self._color), self._size))


class Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("divider", True)
        self.setFixedHeight(1)


# ---------------------------------------------------------------------------
# Botões
# ---------------------------------------------------------------------------
class Button(QPushButton):
    """variant: primary | secondary | danger | ghost — size: sm | md | lg"""

    _ICON_COLOR = {"primary": "on_primary", "danger": "on_primary", "secondary": "text", "ghost": "text_muted"}

    def __init__(self, text: str = "", variant: str = "primary", size: str = "md",
                 icon: str | None = None, parent=None):
        super().__init__(parent)
        self._icon_name = icon
        self._text = text
        self.setProperty("variant", variant)
        self.setProperty("size", size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(SIZE[f"button_{size}"])
        icon_size = SIZE["icon_md"] if size == "lg" else SIZE["icon_sm"]
        self.setIconSize(QSize(icon_size, icon_size))
        self.setText(text)
        theme_manager.changed.connect(self._refresh_icon)
        self._refresh_icon()

    def setText(self, text: str) -> None:  # noqa: N802 (API Qt)
        self._text = text
        # Espaço entre ícone e texto (o QSS não tem propriedade para isso).
        super().setText(f" {text}" if self._icon_name and text else text)

    def text(self) -> str:  # noqa: N802
        return self._text

    def set_variant(self, variant: str) -> None:
        set_prop(self, "variant", variant)
        self._refresh_icon()

    def set_icon_name(self, name: str | None) -> None:
        self._icon_name = name
        self.setText(self._text)
        self._refresh_icon()

    def _refresh_icon(self, *_):
        if not self._icon_name:
            self.setIcon(QIcon())
            return
        color = self._ICON_COLOR.get(self.property("variant"), "text")
        self.setIcon(themed_icon(self._icon_name, color, self.iconSize().width()))


class IconButton(Button):
    """Botão quadrado só com ícone (exige tooltip para acessibilidade)."""

    def __init__(self, icon: str, tooltip: str, variant: str = "secondary", size: str = "md", parent=None):
        super().__init__("", variant, size, icon, parent)
        self.setProperty("icon_only", True)
        altura = SIZE[f"button_{size}"]
        self.setFixedSize(altura, altura)
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)


class ThemeToggle(IconButton):
    """Alterna entre Light e Dark; o ícone mostra o tema de destino."""

    def __init__(self, parent=None):
        super().__init__("moon", "Alternar tema", "secondary", "md", parent)
        self.clicked.connect(theme_manager.toggle)
        self._refresh_icon()

    def _refresh_icon(self, *_):
        escuro = theme_manager.is_dark
        self._icon_name = "sun" if escuro else "moon"
        self.setToolTip("Mudar para o tema claro" if escuro else "Mudar para o tema escuro")
        super()._refresh_icon()


class NavButton(QPushButton):
    def __init__(self, text: str, icon: str, parent=None):
        super().__init__(f"  {text}", parent)
        self._icon_name = icon
        self.setProperty("nav", True)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(SIZE["button_md"])
        self.setIconSize(QSize(SIZE["icon_sm"], SIZE["icon_sm"]))
        theme_manager.changed.connect(self._refresh_icon)
        self._refresh_icon()

    def _refresh_icon(self, *_):
        self.setIcon(themed_icon(self._icon_name, "text_muted", SIZE["icon_sm"], checked_color="primary"))


# ---------------------------------------------------------------------------
# Campos de formulário
# ---------------------------------------------------------------------------
class Input(QLineEdit):
    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(SIZE["input"])


class SearchInput(Input):
    def __init__(self, placeholder: str = "Buscar", parent=None):
        super().__init__(placeholder, parent)
        self.setClearButtonEnabled(True)
        self._acao = QAction(self)
        self.addAction(self._acao, QLineEdit.ActionPosition.LeadingPosition)
        theme_manager.changed.connect(self._refresh_icon)
        self._refresh_icon()

    def _refresh_icon(self, *_):
        self._acao.setIcon(themed_icon("search", "text_muted", SIZE["icon_sm"]))


class Select(QComboBox):
    def __init__(self, items: Iterable[str] = (), parent=None):
        super().__init__(parent)
        self.setView(QListView())  # permite estilizar os itens da lista pelo QSS
        self.setFixedHeight(SIZE["input"])
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.addItems(list(items))


class TextArea(QPlainTextEdit):
    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(SIZE["textarea_min"])


class Checkbox(QCheckBox):
    def __init__(self, text: str = "", checked: bool = False, parent=None):
        super().__init__(text, parent)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class FormField(QWidget):
    """Rótulo + campo + dica/erro. `target` é o widget que fica vermelho no erro."""

    def __init__(self, label: str, field: QWidget | QLayout, hint: str = "",
                 target: QWidget | None = None, parent=None):
        super().__init__(parent)
        self._hint_padrao = hint
        self._target = target or (field if isinstance(field, QWidget) else None)
        self.label = Label(label, "label")
        self.hint = Label(hint, "hint", wrap=True)
        self.hint.setVisible(bool(hint))
        layout = vbox(self.label, field, self.hint, None, spacing=SPACE["sm"])  # alinhado ao topo
        self.setLayout(layout)

    def set_error(self, mensagem: str | None) -> None:
        erro = bool(mensagem)
        if self._target is not None:
            set_prop(self._target, "error", erro)
        set_prop(self.hint, "error", erro)
        self.hint.setText(mensagem if erro else self._hint_padrao)
        self.hint.setVisible(bool(self.hint.text()))


# ---------------------------------------------------------------------------
# Exibição
# ---------------------------------------------------------------------------
class Badge(QLabel):
    """tone: neutral | primary | success | warning | danger"""

    def __init__(self, text: str = "", tone: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setProperty("badge", True)
        self.setProperty("tone", tone)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(SIZE["badge"])
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def set_tone(self, text: str, tone: str) -> None:
        self.setText(text)
        set_prop(self, "tone", tone)


class ProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextVisible(False)
        self.setFixedHeight(SIZE["progress"])


class Card(QFrame):
    def __init__(self, title: str | None = None, description: str | None = None, parent=None):
        super().__init__(parent)
        self.setProperty("card", True)
        pad = SIZE["card_padding"]
        self.body = vbox(spacing=SPACE["lg"], margins=pad)
        self.setLayout(self.body)
        self.header_row: QHBoxLayout | None = None
        if title or description:
            textos = vbox(spacing=SPACE["xs"])
            if title:
                textos.addWidget(Label(title, "section"))
            if description:
                textos.addWidget(Label(description, "muted", wrap=True))
            self.header_row = hbox(textos, spacing=SPACE["sm"])
            self.header_row.setStretch(0, 1)
            self.body.addLayout(self.header_row)

    def add(self, *items: Item) -> "Card":
        _fill(self.body, items)
        return self

    def add_header_action(self, widget: QWidget) -> None:
        if self.header_row is None:
            self.header_row = hbox(None, spacing=SPACE["sm"])
            self.body.insertLayout(0, self.header_row)
        self.header_row.addWidget(widget, 0, Qt.AlignmentFlag.AlignTop)


class StatCard(Card):
    def __init__(self, label: str, value: str = "—", icon: str | None = None,
                 tone: str = "primary", parent=None):
        super().__init__(parent=parent)
        self.body.setSpacing(SPACE["sm"])
        topo = hbox(Label(label, "muted"), None, Icon(icon, tone) if icon else None)
        self.value = Label(value, "stat")
        self.add(topo, self.value)

    def set_value(self, value) -> None:
        self.value.setText(str(value))


class DataTable(QTableWidget):
    """Tabela padrão: linhas de 44px, seleção por linha, sem edição."""

    def __init__(self, headers: list[str], parent=None):
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
        vh = self.verticalHeader()
        vh.setVisible(False)
        vh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        vh.setDefaultSectionSize(SIZE["table_row"])
        hh = self.horizontalHeader()
        hh.setFixedHeight(SIZE["table_row"])
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hh.setHighlightSections(False)
        hh.setStretchLastSection(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setMouseTracking(True)

    def set_column_widths(self, widths: dict[int, int]) -> None:
        for coluna, largura in widths.items():
            self.horizontalHeader().setSectionResizeMode(coluna, QHeaderView.ResizeMode.Interactive)
            self.setColumnWidth(coluna, largura)

    def add_row(self, values: list, data=None) -> int:
        linha = self.rowCount()
        self.insertRow(linha)
        for coluna, valor in enumerate(values):
            if isinstance(valor, QWidget):
                self.setItem(linha, coluna, QTableWidgetItem())
                celula = QWidget()
                celula.setLayout(hbox(valor, None, margins=0))
                celula.layout().setContentsMargins(SPACE["md"], 0, SPACE["md"], 0)
                self.setCellWidget(linha, coluna, celula)
            else:
                texto = "" if valor is None else str(valor)
                item = QTableWidgetItem(texto)
                item.setToolTip(texto)
                self.setItem(linha, coluna, item)
        if data is not None:
            self.item(linha, 0).setData(Qt.ItemDataRole.UserRole, data)
        return linha

    def row_data(self, linha: int):
        item = self.item(linha, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def clear_rows(self) -> None:
        self.setRowCount(0)


# ---------------------------------------------------------------------------
# Estrutura da janela
# ---------------------------------------------------------------------------
class Sidebar(QFrame):
    selected = Signal(int)

    def __init__(self, brand: str, icon: str = "layers", parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(SIZE["sidebar"])

        marca = QFrame()
        marca.setObjectName("SidebarBrand")
        marca.setFixedHeight(SIZE["header"])
        marca.setLayout(hbox(Icon(icon, "primary", SIZE["icon_md"]), Label(brand, "brand"), None,
                             spacing=SPACE["sm"]))
        marca.layout().setContentsMargins(SPACE["xl"], 0, SPACE["lg"], 0)

        self._nav = vbox(Label("MENU", "overline"), SPACE["xs"], spacing=SPACE["xs"])
        self.footer = vbox(spacing=SPACE["sm"])
        conteudo = vbox(self._nav, None, self.footer, spacing=0, margins=SPACE["lg"])

        self.setLayout(vbox(marca, conteudo, spacing=0))
        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)
        self._grupo.idClicked.connect(self.selected.emit)

    def add_item(self, text: str, icon: str) -> int:
        indice = len(self._grupo.buttons())
        botao = NavButton(text, icon)
        self._grupo.addButton(botao, indice)
        self._nav.addWidget(botao)
        if indice == 0:
            botao.setChecked(True)
        return indice

    def set_current(self, indice: int) -> None:
        botao = self._grupo.button(indice)
        if botao:
            botao.setChecked(True)


class Header(QFrame):
    def __init__(self, title: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Header")
        self.setFixedHeight(SIZE["header"])
        self.title = Label(title, "header_title")
        self.subtitle = Label(subtitle, "muted")
        self.actions = hbox(spacing=SPACE["sm"])
        textos = vbox(None, self.title, self.subtitle, None, spacing=0)
        layout = hbox(textos, None, self.actions, spacing=SPACE["md"])
        layout.setContentsMargins(SPACE["xl"], 0, SPACE["xl"], 0)
        self.setLayout(layout)

    def set_title(self, title: str, subtitle: str = "") -> None:
        self.title.setText(title)
        self.subtitle.setText(subtitle)
        self.subtitle.setVisible(bool(subtitle))

    def add_action(self, widget: QWidget) -> None:
        self.actions.addWidget(widget)


class Page(QScrollArea):
    """Área de conteúdo rolável, com margens e espaçamento padrão."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        conteudo = QWidget()
        conteudo.setObjectName("PageContent")
        conteudo.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.body = vbox(spacing=SPACE["xl"], margins=SPACE["xl"])
        conteudo.setLayout(self.body)
        self.setWidget(conteudo)

    def add(self, *items: Item, stretch_last: bool = False) -> None:
        _fill(self.body, items)
        if stretch_last and items and isinstance(items[-1], QWidget):
            self.body.setStretchFactor(items[-1], 1)


class Modal(QDialog):
    """Modal padrão (480px): título, mensagem/corpo e rodapé com botões à direita."""

    def __init__(self, title: str, message: str = "", icon: str | None = None,
                 tone: str = "primary", parent=None):
        super().__init__(parent)
        self.setObjectName("Modal")
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedWidth(SIZE["modal"])

        cabecalho = hbox(spacing=SPACE["md"])
        if icon:
            cabecalho.addWidget(Icon(icon, tone, SIZE["icon_md"]))
        cabecalho.addWidget(Label(title, "section"), 1)

        self.body = vbox(spacing=SPACE["md"])
        if message:
            self.body.addWidget(Label(message, "muted", wrap=True))

        self.footer = hbox(None, spacing=SPACE["sm"])
        self.setLayout(vbox(cabecalho, self.body, SPACE["sm"], self.footer,
                            spacing=SPACE["lg"], margins=SPACE["xl"]))

    def add_button(self, text: str, variant: str = "secondary", accept: bool = False) -> Button:
        botao = Button(text, variant)
        botao.clicked.connect(self.accept if accept else self.reject)
        self.footer.addWidget(botao)
        if accept:
            botao.setDefault(True)
        return botao

    @classmethod
    def confirm(cls, parent, title: str, message: str, confirm_text: str = "Confirmar",
                cancel_text: str = "Cancelar", destructive: bool = False) -> bool:
        modal = cls(title, message, "alert-triangle" if destructive else "info",
                    "danger" if destructive else "primary", parent)
        modal.add_button(cancel_text, "secondary")
        modal.add_button(confirm_text, "danger" if destructive else "primary", accept=True)
        return modal.exec() == QDialog.DialogCode.Accepted

    @classmethod
    def alert(cls, parent, title: str, message: str, tone: str = "primary") -> None:
        icone = {"danger": "x-circle", "success": "check-circle", "warning": "alert-triangle"}.get(tone, "info")
        modal = cls(title, message, icone, tone, parent)
        modal.add_button("Entendi", "primary", accept=True)
        modal.exec()
