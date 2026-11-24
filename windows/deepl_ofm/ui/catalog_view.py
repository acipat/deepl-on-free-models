"""Model catalogue dialog.

Port of ``Sources/HyMT/Views/ModelCatalogView.swift``: one card per curated
model with its badges, identifier, provider, note and install command, plus
provider/search/free filters, a "Fetch from server" probe and single-click
apply actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.catalog import CatalogEntry, ModelCatalog
from ..core.providers import Provider
from ..i18n import t
from . import icons
from .components import (
    Card,
    Divider,
    EmptyState,
    IconButton,
    LinkButton,
    Pill,
    SearchField,
    SecondaryButton,
    ToggleRow,
)
from .theme import Theme

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..controller import AppController


class _RoleLabel(QLabel):
    """QLabel tinted with a palette role and refreshed on theme changes."""

    def __init__(
        self,
        text: str = "",
        role: str = "text",
        size: int = 12,
        weight: int = 400,
        parent: QWidget | None = None,
        *,
        mono: bool = False,
    ) -> None:
        super().__init__(text, parent)
        self._role = role
        self.setFont(Theme.font(size, weight, mono=mono))
        Theme.changed.connect(self._sync_colour)
        self._sync_colour()

    def set_role(self, role: str) -> None:
        self._role = str(role)
        self._sync_colour()

    def _sync_colour(self, *_args: object) -> None:
        colour = getattr(Theme.palette(), self._role, Theme.palette().text)
        self.setStyleSheet(f"color: {colour};")


class _FlowLayout(QLayout):
    """Left-to-right layout that wraps its items onto extra rows."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 7) -> None:
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(int(spacing))
        self._items: list[QLayoutItem] = []

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802 - Qt API
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 - Qt API
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 - Qt API
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientations:  # noqa: N802 - Qt API
        return Qt.Orientations()

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt API
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt API
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - Qt API
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 - Qt API
        size = QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        spacing = self.spacing()
        x = area.x()
        lines: list[tuple[list[QLayoutItem], int]] = []
        line: list[QLayoutItem] = []
        line_height = 0

        def place_line(items: list[QLayoutItem], top: int, height: int) -> None:
            cursor = area.x()
            for item in items:
                hint = item.sizeHint()
                offset = max(0, (height - hint.height()) // 2)
                if not test_only:
                    item.setGeometry(QRect(QPoint(cursor, top + offset), hint))
                cursor += hint.width() + spacing

        for item in self._items:
            if item.isEmpty():
                continue
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > area.right() + 1 and line:
                lines.append((line, line_height))
                line = []
                line_height = 0
                x = area.x()
                next_x = x + hint.width() + spacing
            line.append(item)
            x = next_x
            line_height = max(line_height, hint.height())
        if line:
            lines.append((line, line_height))
        if not lines:
            return 0

        content_height = sum(height for _, height in lines)
        content_height += spacing * (len(lines) - 1)
        top = area.y()
        if not test_only and area.height() > content_height:
            top += (area.height() - content_height) // 2
        for items, height in lines:
            place_line(items, top, height)
            top += height + spacing
        return content_height + margins.top() + margins.bottom()


class _CommandBox(QWidget):
    """Rounded, selectable install command with a copy button."""

    def __init__(self, command: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 5, 5)
        layout.setSpacing(6)

        self.command_label = _RoleLabel(command, "muted", 10, parent=self, mono=True)
        self.command_label.setWordWrap(True)
        self.command_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.command_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.command_label, 1)

        self.copy_button = IconButton(
            "copy", t("Copy install command"), self, size=26, icon_size=13
        )
        layout.addWidget(self.copy_button, 0, Qt.AlignmentFlag.AlignTop)

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            painter.setBrush(QColor(palette.card_hover))
            painter.setPen(QColor(palette.border))
            painter.drawRoundedRect(rect, 7.0, 7.0)
        finally:
            painter.end()


class _CatalogCard(Card):
    """One curated model, rendered as a calm rounded surface."""

    useRequested = Signal(object)
    copyRequested = Signal(object)

    def __init__(self, entry: CatalogEntry, parent: QWidget | None = None) -> None:
        super().__init__("", parent=parent, padding=14, spacing=8)
        self.entry = entry
        self.setObjectName("catalogCard")

        header_row = QWidget(self)
        top = QHBoxLayout(header_row)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)

        title_host = QWidget(header_row)
        self._title_flow = _FlowLayout(title_host, spacing=7)

        self.name_label = _RoleLabel(entry.name, "text", 14, 600, title_host)
        self.name_label.setMinimumHeight(22)
        self._title_flow.addWidget(self.name_label)

        self.provider_label = Pill(t(entry.provider.title), "muted", title_host)
        self._title_flow.addWidget(self.provider_label)

        self._badge_keys: tuple[str, ...] = tuple(entry.badges)
        self.badge_pills: list[Pill] = []
        for badge in self._badge_keys:
            pill = Pill(t(badge), "muted", title_host)
            pill.setObjectName("catalogBadge")
            self.badge_pills.append(pill)
            self._title_flow.addWidget(pill)

        top.addWidget(title_host, 1)

        self.use_button = SecondaryButton(t("Use this model"), header_row)
        self.use_button.setObjectName("useModelButton")
        self.use_button.setAccessibleName(t("Use this model"))
        self.use_button.clicked.connect(lambda: self.useRequested.emit(entry))
        top.addWidget(self.use_button, 0, Qt.AlignmentFlag.AlignTop)
        self.add(header_row)

        self.model_label = _RoleLabel(entry.model_id, "faint", 11, parent=self, mono=True)
        self.model_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.add(self.model_label)

        self.note_label = _RoleLabel(t(entry.note), "muted", 12, parent=self)
        self.note_label.setWordWrap(True)
        self.add(self.note_label)

        self.command_box: _CommandBox | None = None
        self.copy_button: IconButton | None = None
        self.command_label: QLabel | None = None
        if entry.install_command:
            self.command_box = _CommandBox(entry.install_command, self)
            self.copy_button = self.command_box.copy_button
            self.command_label = self.command_box.command_label
            self.command_box.copy_button.clicked.connect(
                lambda: self.copyRequested.emit(entry)
            )
            self.add(self.command_box)

    # -- feedback -----------------------------------------------------------
    def show_copied(self) -> None:
        if self.command_box is None:
            return
        self.command_box.copy_button.set_icon_name("check")
        QTimer.singleShot(1200, self._reset_copy_icon)

    def _reset_copy_icon(self) -> None:
        try:
            if self.command_box is not None:
                self.command_box.copy_button.set_icon_name("copy")
        except RuntimeError:  # the dialog closed in the meantime
            pass

    def retranslate_ui(self) -> None:
        self.provider_label.setText(t(self.entry.provider.title))
        for pill, badge in zip(self.badge_pills, self._badge_keys):
            pill.setText(t(badge))
        self.note_label.setText(t(self.entry.note))
        self.use_button.setText(t("Use this model"))
        self.use_button.setAccessibleName(t("Use this model"))
        if self.command_box is not None:
            self.command_box.copy_button.set_tooltip(t("Copy install command"))


class _Section(QWidget):
    """A small uppercase caption followed by its rows."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self.header = _RoleLabel(title.upper(), "faint", 10, 600, self)
        self.header.setObjectName("catalogSectionHeader")
        outer.addWidget(self.header)

        host = QWidget(self)
        self.body = QVBoxLayout(host)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(10)
        outer.addWidget(host)

    def set_title(self, title: str) -> None:
        self.header.setText(title.upper())


class _ServerRow(Card):
    """One model discovered on the server, with a "Choose" link."""

    chooseRequested = Signal(str)

    def __init__(self, model: str, parent: QWidget | None = None) -> None:
        super().__init__("", parent=parent, padding=10, spacing=0)
        self.model = model
        self.setObjectName("catalogServerRow")

        host = QWidget(self)
        row = QHBoxLayout(host)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(10)

        self.model_label = _RoleLabel(model, "text", 11, parent=host, mono=True)
        self.model_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        row.addWidget(self.model_label, 1)

        self.choose_button = LinkButton(t("Choose"), host)
        self.choose_button.setObjectName("chooseServerModelButton")
        self.choose_button.clicked.connect(
            lambda: self.chooseRequested.emit(self.model)
        )
        row.addWidget(self.choose_button)
        self.add(host)

    def retranslate_ui(self) -> None:
        self.choose_button.setText(t("Choose"))


class CatalogView(QDialog):
    """A searchable, provider-filtered gallery of ready-to-use translators."""

    def __init__(self, controller: "AppController", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.cards: list[_CatalogCard] = []
        self.server_rows: list[_ServerRow] = []
        self._server_error = str(getattr(controller, "models_error", "") or "")
        self._loading = bool(getattr(controller, "models_loading", False))
        self.setWindowTitle(t("Model catalog"))
        self.setWindowIcon(icons.icon("translate", size=64))
        self.setObjectName("catalogView")
        self.setMinimumSize(720, 480)
        self.resize(760, 620)
        self.setSizeGripEnabled(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(Divider("horizontal", self))
        root.addWidget(self._build_controls())
        root.addWidget(Divider("horizontal", self))
        root.addWidget(self._build_content(), 1)
        root.addWidget(Divider("horizontal", self))
        root.addWidget(self._build_footer())

        self._populate_cards()
        self._rebuild_server_rows()
        self._apply_filters()
        self.retranslate_ui()
        Theme.changed.connect(self._apply_theme)
        self._connect_controller(controller)

    def _connect_controller(self, controller: "AppController") -> None:
        """Follow the controller's model-probe state when it exposes it."""
        for signal_name, handler in (
            ("modelsChanged", self._on_models_changed),
            ("modelsLoadingChanged", self._on_models_loading),
            ("modelsErrorChanged", self._on_models_error),
        ):
            signal = getattr(controller, signal_name, None)
            if signal is not None:
                signal.connect(handler)

    # -- construction -------------------------------------------------------
    def _build_header(self) -> QWidget:
        self.header = QWidget(self)
        self.header.setObjectName("catalogHeader")
        layout = QHBoxLayout(self.header)
        layout.setContentsMargins(22, 16, 22, 15)
        layout.setSpacing(12)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(3)
        self.title_label = _RoleLabel(t("Model catalog"), "text", 18, 600, self.header)
        column.addWidget(self.title_label)
        self.subtitle_label = _RoleLabel(
            t("Ready translators for local use and cloud options with free tiers."),
            "muted",
            12,
            parent=self.header,
        )
        self.subtitle_label.setWordWrap(True)
        column.addWidget(self.subtitle_label)
        layout.addLayout(column, 1)

        self.count_label = _RoleLabel("0", "faint", 12, parent=self.header, mono=True)
        layout.addWidget(self.count_label, 0, Qt.AlignmentFlag.AlignTop)
        return self.header

    def _build_controls(self) -> QWidget:
        controls = QWidget(self)
        controls.setObjectName("catalogControls")
        outer = QVBoxLayout(controls)
        outer.setContentsMargins(22, 12, 22, 12)
        outer.setSpacing(7)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        self.provider_filter = QComboBox(controls)
        self.provider_filter.setObjectName("catalogProviderFilter")
        self.provider_filter.setMinimumHeight(34)
        self.provider_filter.setMinimumWidth(150)
        self.provider_filter.setMaximumWidth(200)
        self.provider_filter.setAccessibleName(t("Provider"))
        row.addWidget(self.provider_filter, 0, Qt.AlignmentFlag.AlignVCenter)

        self.free_toggle = ToggleRow(t("Free only"), False, controls)
        self.free_toggle.setObjectName("catalogFreeOnlyToggle")
        self.free_toggle.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.free_toggle.toggled.connect(self._apply_filters)
        row.addWidget(self.free_toggle, 0, Qt.AlignmentFlag.AlignVCenter)

        self.search = SearchField(t("Search model"), controls)
        self.search.setObjectName("catalogSearch")
        self.search.textChanged.connect(self._apply_filters)
        row.addWidget(self.search, 1)

        self.busy_label = _RoleLabel("", "muted", 11, parent=controls)
        self.busy_label.setObjectName("catalogFetchStatus")
        self.busy_label.setVisible(False)

        self.fetch_button = SecondaryButton(t("Fetch from server"), controls)
        self.fetch_button.setObjectName("catalogFetchButton")
        self.fetch_button.setAccessibleName(t("Fetch from server"))
        self.fetch_button.clicked.connect(self._fetch_from_server)
        row.addWidget(self.fetch_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.provider_filter.currentIndexChanged.connect(self._apply_filters)
        outer.addLayout(row)
        outer.addWidget(self.busy_label)

        self.error_label = _RoleLabel("", "danger", 11, parent=controls)
        self.error_label.setObjectName("catalogServerError")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        outer.addWidget(self.error_label)
        return controls

    def _build_content(self) -> QWidget:
        self.stack = QStackedWidget(self)
        self.stack.setObjectName("catalogStack")
        self.scroll = QScrollArea(self.stack)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._cards_host = QWidget(self.scroll)
        self._cards_layout = QVBoxLayout(self._cards_host)
        self._cards_layout.setContentsMargins(20, 16, 20, 18)
        self._cards_layout.setSpacing(10)
        self._cards_layout.addStretch(1)
        self.scroll.setWidget(self._cards_host)
        self.stack.addWidget(self.scroll)

        self.empty_state = EmptyState(
            "search",
            t("Nothing found"),
            t("Try another query."),
            self.stack,
        )
        self.stack.addWidget(self.empty_state)
        return self.stack

    def _build_footer(self) -> QWidget:
        self.footer = QWidget(self)
        self.footer.setObjectName("catalogFooter")
        layout = QHBoxLayout(self.footer)
        layout.setContentsMargins(22, 10, 16, 10)
        layout.setSpacing(8)

        self.footer_icon = QLabel(self.footer)
        self.footer_icon.setFixedSize(15, 18)
        layout.addWidget(self.footer_icon, 0, Qt.AlignmentFlag.AlignTop)

        self.footer_label = _RoleLabel(
            t(
                "Need another model? Type its ID into the Model field — any model "
                "your server supports will work."
            ),
            "faint",
            11,
            parent=self.footer,
        )
        self.footer_label.setWordWrap(True)
        layout.addWidget(self.footer_label, 1)

        self.close_button = SecondaryButton(t("Close"), self.footer)
        self.close_button.setObjectName("closeCatalogButton")
        self.close_button.clicked.connect(self.reject)
        layout.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignBottom)
        return self.footer

    def _populate_cards(self) -> None:
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.cards = []
        self._recommended_cards: list[_CatalogCard] = []
        self._model_cards: list[_CatalogCard] = []
        self.server_rows = []

        providers: list[Provider] = []
        for entry in ModelCatalog.ENTRIES:
            if entry.provider not in providers:
                providers.append(entry.provider)
        self._providers = providers

        self.server_section = _Section(t("Found on the server"), self._cards_host)
        self.recommended_section = _Section(t("Recommended"), self._cards_host)
        self.models_section = _Section(t("Models"), self._cards_host)
        self._cards_layout.addWidget(self.server_section)
        self._cards_layout.addWidget(self.recommended_section)
        self._cards_layout.addWidget(self.models_section)

        for entry in ModelCatalog.ENTRIES:
            card = _CatalogCard(entry, self._cards_host)
            card.useRequested.connect(self._use_entry)
            card.copyRequested.connect(self._copy_command)
            if "recommended" in entry.badges:
                self.recommended_section.body.addWidget(card)
                self._recommended_cards.append(card)
            else:
                self.models_section.body.addWidget(card)
                self._model_cards.append(card)
            self.cards.append(card)
        self._cards_layout.addStretch(1)
        self._rebuild_provider_filter()

    def _rebuild_provider_filter(self) -> None:
        previous = self.provider_filter.currentData() if self.provider_filter.count() else ""
        blocked = self.provider_filter.blockSignals(True)
        try:
            self.provider_filter.clear()
            self.provider_filter.addItem(t("All providers"), "")
            for provider in self._providers:
                self.provider_filter.addItem(t(provider.title), provider.value)
            index = self.provider_filter.findData(previous)
            self.provider_filter.setCurrentIndex(max(0, index))
        finally:
            self.provider_filter.blockSignals(blocked)

    def _rebuild_server_rows(self) -> None:
        for row in self.server_rows:
            row.setParent(None)
            row.deleteLater()
        self.server_rows = []

        curated = {entry.model_id for entry in ModelCatalog.ENTRIES}
        models = [
            str(model)
            for model in (getattr(self.controller, "provider_models", None) or [])
        ]
        for model in sorted(set(models), key=str.casefold):
            if not model or model in curated:
                continue
            row = _ServerRow(model, self.server_section)
            row.chooseRequested.connect(self._choose_server_model)
            self.server_section.body.addWidget(row)
            self.server_rows.append(row)

    # -- filtering ----------------------------------------------------------
    def _matches(
        self,
        card: _CatalogCard,
        needle: str,
        provider: str,
        free_only: bool = False,
    ) -> bool:
        entry = card.entry
        if provider and entry.provider.value != provider:
            return False
        if free_only and not entry.is_free:
            return False
        if not needle:
            return True
        haystack = " ".join(
            (
                entry.name,
                entry.model_id,
                entry.provider.title,
                entry.size,
                entry.languages,
                t(entry.note),
                *(t(badge) for badge in entry.badges),
            )
        ).casefold()
        return needle in haystack

    def _apply_filters(self, *_args: object) -> None:
        needle = (self.search.text() or "").strip().casefold()
        provider = str(self.provider_filter.currentData() or "")
        free_only = self.free_toggle.is_checked()
        visible = 0
        for card in self.cards:
            match = self._matches(card, needle, provider, free_only)
            card.setVisible(match)
            if match:
                visible += 1

        self.recommended_section.setVisible(
            any(not card.isHidden() for card in self._recommended_cards)
        )
        self.models_section.setVisible(
            any(not card.isHidden() for card in self._model_cards)
        )

        visible_server = 0
        for row in self.server_rows:
            match = not needle or needle in row.model.casefold()
            row.setVisible(match)
            if match:
                visible_server += 1
        self.server_section.setVisible(visible_server > 0)

        total = len(self.cards)
        filtered = bool(needle or provider or free_only)
        self.count_label.setText(f"{visible} / {total}" if filtered else str(total))
        if visible or visible_server:
            self.stack.setCurrentWidget(self.scroll)
        else:
            self.stack.setCurrentWidget(self.empty_state)
            self.empty_state.set_title(t("Nothing found"))
            self.empty_state.set_subtitle(t("Try another query."))
            self.empty_state.retranslate_ui()

    def visible_cards(self) -> list[_CatalogCard]:
        return [card for card in self.cards if not card.isHidden()]

    # -- actions ------------------------------------------------------------
    def _copy_command(self, entry: object) -> None:
        if not entry.install_command:
            return
        QGuiApplication.clipboard().setText(entry.install_command)
        for card in self.cards:
            if card.entry is entry:
                card.show_copied()
                break

    def _use_entry(self, entry: object) -> None:
        self.controller.apply_catalog_entry(entry)
        self.accept()

    def _fetch_from_server(self) -> None:
        if self._loading:
            return
        loader = getattr(self.controller, "connect_and_load_models", None)
        if loader is None:
            return
        self._server_error = ""
        self._refresh_fetch_state()
        loader()
        self._loading = bool(getattr(self.controller, "models_loading", False))
        self._server_error = str(getattr(self.controller, "models_error", "") or "")
        self._rebuild_server_rows()
        self._apply_filters()
        self._refresh_fetch_state()

    def _choose_server_model(self, model: str) -> None:
        self.controller.settings.model = model
        self.controller.save_settings()
        self.accept()

    def _on_models_changed(self, _models: object) -> None:
        self._rebuild_server_rows()
        self._apply_filters()

    def _on_models_loading(self, loading: bool) -> None:
        self._loading = bool(loading)
        self._refresh_fetch_state()

    def _on_models_error(self, message: str) -> None:
        self._server_error = str(message or "")
        self._refresh_fetch_state()

    def _refresh_fetch_state(self) -> None:
        self.fetch_button.setEnabled(not self._loading)
        self.busy_label.setText(t("Connecting…") if self._loading else "")
        self.busy_label.setVisible(self._loading)
        message = "" if self._loading else self._server_error
        self.error_label.setText(message)
        self.error_label.setVisible(bool(message))

    # -- theme / i18n -------------------------------------------------------
    def _apply_theme(self) -> None:
        palette = Theme.palette()
        self.header.setStyleSheet(
            f"QWidget#catalogHeader {{ background: {palette.panel}; }}"
        )
        self.footer.setStyleSheet(
            f"QWidget#catalogFooter {{ background: {palette.panel}; }}"
        )
        self.footer_icon.setPixmap(icons.pixmap("info", palette.faint, 13))
        self.setStyleSheet(
            f"QDialog#catalogView {{ background: {palette.bg}; }}"
        )

    def retranslate_ui(self) -> None:
        self.setWindowTitle(t("Model catalog"))
        self.title_label.setText(t("Model catalog"))
        self.subtitle_label.setText(
            t("Ready translators for local use and cloud options with free tiers.")
        )
        self.search.set_placeholder(t("Search model"))
        self.provider_filter.setAccessibleName(t("Provider"))
        self.free_toggle.set_label(t("Free only"))
        self.fetch_button.setText(t("Fetch from server"))
        self.busy_label.setText(t("Connecting…") if self._loading else "")
        self.recommended_section.set_title(t("Recommended"))
        self.models_section.set_title(t("Models"))
        self.server_section.set_title(t("Found on the server"))
        for row in self.server_rows:
            row.retranslate_ui()
        self.footer_label.setText(
            t(
                "Need another model? Type its ID into the Model field — any model "
                "your server supports will work."
            )
        )
        self.close_button.setText(t("Close"))
        for card in self.cards:
            card.retranslate_ui()
        self._rebuild_provider_filter()
        self._apply_filters()
        self._refresh_fetch_state()
        self._apply_theme()

    def showEvent(self, event: object) -> None:  # noqa: N802
        self._apply_theme()
        super().showEvent(event)
